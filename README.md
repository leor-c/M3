# M3: A Modular World Model over Streams of Tokens

The weights of our trained models are available through this [link]() (Soon!)

## Docker
We provide a Dockerfile for building a docker image and running the code in a docker container.
To use docker with GPUs, make sure to install the `nvidia-container-toolkit` ([link](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)) on the host machine.

To build the docker image and run a container, run the following command from the project root folder:
```bash
docker-compose up -d
```
To access the command line of the container, run
```bash
docker attach m3_c
```
Use the container's command line to run the desired script (detailed below).

### X11 Forwarding
If you would like to render the environment, it is necessary to set up X11 forwarding.

##### On Windows OS:
we used [VcXsrv](https://github.com/marchaesen/vcxsrv) as an X server.
Then, set up the `DISPLAY` environment variable by executing 
```bash
export DISPLAY=<your-host-ip>:0
```
inside the docker container (after attaching).
This can also be set in the Windows command line using `setx DISPLAY=<your-host-ip>:0` or just `set DISPLAY=<your-host-ip>:0` for the current session only.

You can validate the value is correct by executing `echo $DISPLAY` in the Docker container.

##### Linux OS:
If the game window is not appearing, try executing `sudo xhost +` on the host machine (before attaching to the docker container).


##### Headless Mode
To run in headless mode, execute `export MUJOCO_GL='osmesa'` in the Docker container's terminal before launching the training script.

## Setup

- Python 3.10
- Install [PyTorch](https://pytorch.org/get-started/locally/) (torch and torchvision). Code developed with several versions of Pytorch, with the latest being torch==2.4.1, but should work with other recent version.
- Install [other dependencies](requirements.txt): `pip install -r requirements.txt`
- Warning: Atari ROMs will be downloaded with the dependencies, which means that you acknowledge that you have the license to use them.

## Launch a training run

```bash
python src/main.py benchmark=atari env.train.id=BreakoutNoFrameskip-v4 common.device=cuda:0 wandb.mode=online
```

To run other benchmarks use `benchmark=dmc` for DeepMind Control Suite or `benchmark=craftax` for Craftax.
By default, the logs are synced to [weights & biases](https://wandb.ai), set `wandb.mode=disabled` to turn it off 
or `wandb.mode=offline` for offline logging.

## Configuration

- All configuration files are located in `config/`, the main configuration file is `config/base.yaml`.
- Each benchmark overrides the base configuration. Each root benchmark config is located in `config/benchmark`.
- The simplest way to customize the configuration is to edit these files directly.
- Please refer to [Hydra](https://github.com/facebookresearch/hydra) for more details regarding configuration management.

## Run folder

Each new run is located at `outputs/env.id/YYYY-MM-DD/hh-mm-ss/`. This folder is structured as:

```txt
outputs/env.id/YYYY-MM-DD/hh-mm-ss/
│
└─── checkpoints
│   │   last.pt
|   |   optimizer.pt
|   |   ...
│   │
│   └─── dataset
│       │   0.pt
│       │   1.pt
│       │   ...
│
└─── config
│   |   config.yaml
|
└─── media
│   │
│   └─── episodes
│   |   │   ...
│   │
│   └─── reconstructions
│   |   │   ...
│
└─── scripts
|   |   eval.py
│   │   play.sh
│   │   resume.sh
|   |   ...
|
└─── src
|   |   ...
|
└─── wandb
    |   ...
```

- `checkpoints`: contains the last checkpoint of the model, its optimizer and the dataset.
- `media`:
  - `episodes`: contains train / test / imagination episodes for visualization purposes.
  - `reconstructions`: contains original frames alongside their reconstructions with the autoencoder.
- `scripts`: **from the run folder**, you can use the following three scripts.
  - `eval.py`: Launch `python ./scripts/eval.py` to evaluate the run.
  - `resume.sh`: Launch `./scripts/resume.sh` to resume a training that crashed.
  - `play.py`: Tool to visualize the learned controller / world model / representations. 
    - Use `python src/play.py --help` to print usage information. Currently, this tool only supports `atari` and `craftax` options.
    - Launch `python src/play.py <benchmark> -p <path-to-model-weights>` to watch the agent play live in the environment. If you add the flag `-r` (Atari only), the left panel displays the original frame, the center panel displays the same frame downscaled to the input resolution of the discrete autoencoder, and the right panel shows the output of the autoencoder (what the agent actually sees). The `-h` flag shows additional information (Atari only).

[//]: # (    - Launch `./scripts/play.sh -w` to unroll live trajectories with your keyboard inputs &#40;i.e. to play in the world model&#41;. Note that since the world model was trained with segments of $H$ steps where the first $c$ observations serve as a context, the memory of the world model is flushed every $H-c$ frames.)
[//]: # (    - Launch `./scripts/play.sh -a` to watch the agent play live in the world model. World model memory flush applies here as well for the same reasons.)
[//]: # (    - Launch `./scripts/play.sh -e` to visualize the episodes contained in `media/episodes`.)
[//]: # (    - Add the flag `-h` to display a header with additional information.)
[//]: # (    - Press '`,`' to start and stop recording. The corresponding segment is saved in `media/recordings` in mp4 and numpy formats.)
[//]: # (    - Add the flag `-s` to enter 'save mode', where the user is prompted to save trajectories upon completion.)

## Results

The folder `results/data/` contains raw scores (for each game, and for each training run).

## Credits

- [https://github.com/leor-c/REM](https://github.com/leor-c/REM)
- [yet-another-retnet](https://github.com/fkodom/yet-another-retnet)
- [https://github.com/eloialonso/iris](https://github.com/eloialonso/iris)
- [https://github.com/fkodom/yet-another-retnet](https://github.com/fkodom/yet-another-retnet)
- [https://github.com/pytorch/pytorch](https://github.com/pytorch/pytorch)
- [https://github.com/CompVis/taming-transformers](https://github.com/CompVis/taming-transformers)
- [https://github.com/karpathy/minGPT](https://github.com/karpathy/minGPT)
- [https://github.com/google-research/rliable](https://github.com/google-research/rliable)
