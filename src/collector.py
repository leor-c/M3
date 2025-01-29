import json
import random
import sys
from collections import defaultdict
from typing import List, Optional, Union

import gymnasium.spaces
from einops import rearrange
import numpy as np
import torch
from loguru import logger
from tqdm import tqdm
import wandb
from gymnasium.spaces import Box

from agent import Agent
from dataset import EpisodesDataset, EpisodeDirManager
from envs import SingleProcessEnv, MultiProcessEnv
from episode import Episode
from utils import (
    RandomHeuristic, DiscreteRandomHeuristic, ContinuousRandomHeuristic, ObsModality
)
from utils.preprocessing import get_obs_processor


class Collector:
    def __init__(
            self, env: Union[SingleProcessEnv, MultiProcessEnv], dataset: EpisodesDataset,
            episode_dir_manager: EpisodeDirManager
    ) -> None:
        self.env = env
        self.dataset = dataset
        self.episode_dir_manager = episode_dir_manager
        self.obs, self.info = self.env.reset()
        self.episode_ids = [None] * self.env.num_envs
        action_space = self.env.action_space
        self.heuristic = (ContinuousRandomHeuristic(action_space)
                          if isinstance(action_space, Box) else DiscreteRandomHeuristic(action_space))
        self.obs_processors = {m: get_obs_processor(m) for m in env.modalities}

    def reset(self):
        self.episode_ids = [None] * self.env.num_envs
        self.obs, _ = self.env.reset()

    def obs_to_torch(self, agent, obs: dict[str, np.ndarray]):
        assert agent.tokenizer is not None
        assert isinstance(obs, dict)
        assert set(obs.keys()) == set([m.name for m in self.env.modalities]), f"{set(obs.keys())} != {self.env.modalities}"
        torch_obs = {m: self.obs_processors[m].to_torch(obs[m.name], device=agent.device) for m in self.env.modalities}
        processed_obs = {m: self.obs_processors[m](v) for m, v in torch_obs.items()}

        return processed_obs

    @torch.no_grad()
    def collect(self, agent: Agent, epoch: int, epsilon: float, should_sample: bool, temperature: float, burn_in: int, *, num_steps: Optional[int] = None, num_episodes: Optional[int] = None):
        # assert self.env.num_actions == agent.world_model.act_vocab_size
        assert 0 <= epsilon <= 1

        assert (num_steps is None) != (num_episodes is None)
        should_stop = lambda steps_, episodes_: steps_ >= num_steps if num_steps is not None else episodes_ >= num_episodes

        to_log = []
        steps, episodes = 0, 0
        returns = []
        observations, actions, rewards, dones = [], [], [], []
        info_avg = defaultdict(list)

        burnin_obs_rec, mask_padding, burnin_obs, burning_actions = None, None, None, None
        if set(self.episode_ids) != {None} and burn_in > 0:
            current_episodes = [self.dataset.get_episode(episode_id) for episode_id in self.episode_ids]
            segmented_episodes = [episode.segment(start=len(episode) - burn_in, stop=len(episode), should_pad=True) for episode in current_episodes]
            mask_padding = torch.stack([episode.mask_padding for episode in segmented_episodes], dim=0).to(agent.device)
            assert agent.tokenizer is not None
            burnin_obs = {
                k: torch.stack([episode.observations[k] for episode in segmented_episodes],
                               dim=0).float().to(agent.device)
                for k in segmented_episodes[0].observations.keys()
            }
            if ObsModality.image in agent.tokenizer.modalities:
                assert ObsModality.image in burnin_obs
                burnin_obs[ObsModality.image] = burnin_obs[ObsModality.image].div(255)
            if ObsModality.token in agent.tokenizer.modalities:
                burnin_obs[ObsModality.token] = burnin_obs[ObsModality.token].long()
            if ObsModality.token_2d in agent.tokenizer.modalities:
                burnin_obs[ObsModality.token_2d] = burnin_obs[ObsModality.token_2d].long()
            burning_actions = torch.stack([episode.actions for episode in segmented_episodes], dim=0).to(agent.device)
            # burnin_obs_rec = torch.clamp(agent.tokenizer.encode_decode(burnin_obs, should_preprocess=True, should_postprocess=True), 0, 1)

        agent.reset_actor_critic(
            n=self.env.num_envs,
            burnin_observations=burnin_obs,
            mask_padding=mask_padding,
            actions=burning_actions
        )
        pbar = tqdm(total=num_steps if num_steps is not None else num_episodes, desc=f'Experience collection ({self.dataset.name})', file=sys.stdout)

        while not should_stop(steps, episodes):

            observations.append(self.obs)
            obs = self.obs_to_torch(agent, self.obs)
            act = agent.act(obs, should_sample=should_sample, temperature=temperature).cpu().numpy()

            if random.random() < epsilon:
                act = self.heuristic.act(obs).cpu().numpy()

            self.obs, reward, terminated, truncated, self.info = self.env.step(act)

            actions.append(act)
            rewards.append(reward)
            dones.append(terminated)

            new_steps = len(self.env.mask_new_dones)
            steps += new_steps
            pbar.update(new_steps if num_steps is not None else 0)

            # Warning: with EpisodicLifeEnv + MultiProcessEnv, reset is ignored if not a real done.
            # Thus, segments of experience following a life loss and preceding a general done are discarded.
            # Not a problem with a SingleProcessEnv.

            if self.env.should_reset():
                observations.append(self.obs)
                actions.append(np.zeros_like(act))  # for uniform length, will be ignored
                rewards.append(np.zeros_like(reward))  # for uniform length, will be ignored
                dones.append(np.zeros_like(terminated))  # for uniform length, will be ignored
                infos = self.info if self.env.num_envs > 1 else [self.info]
                self.add_experience_to_dataset(observations, actions, rewards, dones, infos)

                new_episodes = self.env.num_envs
                episodes += new_episodes
                pbar.update(new_episodes if num_episodes is not None else 0)

                infos = defaultdict(list)
                for episode_id in self.episode_ids:
                    episode = self.dataset.get_episode(episode_id)
                    self.episode_dir_manager.save(episode, episode_id, epoch)
                    episode_metrics = episode.compute_metrics()
                    metrics_episode = {k: v for k, v in episode_metrics.__dict__.items()}
                    metrics_episode['episode_num'] = episode_id
                    if isinstance(self.heuristic, DiscreteRandomHeuristic) and isinstance(self.heuristic.action_space, gymnasium.spaces.Discrete):
                        np_hist = np.histogram(episode.actions.numpy(),
                                               bins=np.arange(0, self.env.num_actions + 1) - 0.5,
                                               density=True)
                        metrics_episode['action_histogram'] = wandb.Histogram(np_histogram=np_hist)
                        to_log.append({f'{self.dataset.name}/action_dist': np_hist[0]})
                    metrics_episode['rewards_per_step'] = episode_metrics.rewards_per_step
                    returns.append(metrics_episode['episode_return'])
                    metrics_episode = {f'{self.dataset.name}/{k}': v for k, v in metrics_episode.items()}
                    # episode_info = {f'{self.dataset.name}/{k}': v for k, v in episode.last_info.items()}
                    for k, v in episode.last_info.items():
                        info_avg[k].append(v)
                    to_log.append({**metrics_episode})

                self.obs, _ = self.env.reset()
                self.episode_ids = [None] * self.env.num_envs
                agent.actor_critic.reset(n=self.env.num_envs)
                observations, actions, rewards, dones = [], [], [], []

        # Add incomplete episodes to dataset, and complete them later.
        if len(observations) > 0:
            infos = self.info if self.env.num_envs > 1 else [self.info]
            self.add_experience_to_dataset(observations, actions, rewards, dones, infos)

        agent.actor_critic.clear()

        if len(info_avg) > 0:
            episode_info = {f'{self.dataset.name}/{k}': np.mean(v) for k, v in info_avg.items()}
            to_log.append(episode_info)

        metrics_collect = {
            '#episodes': len(self.dataset),
            '#steps': sum(map(len, self.dataset.episodes)),
        }
        if len(returns) > 0:
            metrics_collect['return'] = np.mean(returns)
        metrics_collect = {f'{self.dataset.name}/{k}': v for k, v in metrics_collect.items()}
        to_log.append(metrics_collect)

        return to_log

    def add_experience_to_dataset(
            self,
            observations: List[dict[str, np.ndarray]],
            actions: List[np.ndarray],
            rewards: List[np.ndarray],
            dones: List[np.ndarray],
            infos: List[dict]
    ) -> None:
        assert len(observations) == len(actions) == len(rewards) == len(dones)
        observations = {ObsModality[k]: np.swapaxes([o[k] for o in observations], 0, 1) for k in observations[0].keys()}
        actions, rewards, dones = map(lambda arr: np.swapaxes(arr, 0, 1), [actions, rewards, dones])
        for i, (a, r, d) in enumerate(zip(*(actions, rewards, dones))):  # Make everything (N, T, ...) instead of (T, N, ...)
            obs = {m: self.obs_processors[m].to_torch(observations[m][i]) for m in self.obs_processors.keys()}

            episode = Episode(
                observations=obs,  # channel-first
                actions=torch.from_numpy(a),
                rewards=torch.from_numpy(r).float(),
                ends=torch.LongTensor(d),
                mask_padding=torch.ones(d.shape[0], dtype=torch.bool),
                last_info=infos[i]
            )
            if self.episode_ids[i] is None:
                self.episode_ids[i] = self.dataset.add_episode(episode)
            else:
                self.dataset.update_episode(self.episode_ids[i], episode)
