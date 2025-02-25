from typing import Optional

import click
from pathlib import Path
import os


def eval_main(weights_path: Path, num_episodes: int, num_envs: int, seed: int, wandb_mode: str, benchmark: Optional[str] = None):
    cmd = f'python src/main.py'
    if benchmark is not None:
        cmd += f' benchmark={benchmark}'
    cmd += f' outputs_dir_path=eval_outputs'
    cmd += ' training.should=False'
    cmd += ' evaluation.should=True'
    cmd += ' common.epochs=0'
    cmd += f' common.seed={seed}'
    cmd += ' common.metrics_only_mode=True'

    cmd += f' wandb.mode={wandb_mode}'
    cmd += f' wandb.group=eval-{benchmark}'

    cmd += f' initialization.agent.path_to_checkpoint={str(weights_path.absolute())}'
    cmd += ' initialization.agent.load_tokenizer=True'
    cmd += ' initialization.agent.load_world_model=True'
    cmd += ' initialization.agent.load_actor_critic=True'

    cmd += f' collection.test.num_envs={num_envs}'
    cmd += f' collection.test.config.num_episodes_end={num_episodes}'

    res = os.system(cmd)
    if res != 0:
        raise RuntimeError(f'Failed to run command: {cmd}\nTerminating...')


@click.command()
@click.option('-p', '--weights-path', type=click.Path(exists=True), default='checkpoints/last.pt')
@click.option('-n', '--num-episodes', type=int, default=100)
@click.option('-e', '--num-envs', type=int, default=20)
@click.option('-s', '--seed', type=int, default=0)
@click.option('-b', '--benchmark', default=None, type=click.Choice(['atari', 'dmc', 'craftax']))
@click.option('-w', '--wandb-mode', default='online', type=click.Choice(['online', 'offline', 'disabled']))
def main(weights_path, num_episodes, num_envs, seed, benchmark, wandb_mode):
    should_override_benchmark = Path('config/benchmark').exists()
    if not should_override_benchmark:
        assert benchmark is None
    else:
        assert benchmark is not None

    eval_main(Path(weights_path), num_episodes, num_envs, seed, wandb_mode, benchmark)


if __name__ == '__main__':
    main()
