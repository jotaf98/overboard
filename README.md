# OverBoard
Pure Python dashboard for monitoring deep learning experiments (like TensorBoard for PyTorch/MXNet/etc, without a browser)

## Features

- Automatically discovers new experiments in a directory tree, and updates plots in real-time

- Fully responsive native app, no fiddly Python-Javascript bridge or browsers involved

- Visualize tensors (activations, filters) interactively with the mouse (zoom/pan)

- Fully customizable plots using MatPlotLib. See what your network is really up to!

- Fast logging and out-of-process drawing. Don't slow your training down to have fancy graphs

- Easy remote monitoring of experiments (e.g. in a cluster over SSH)

## Installation

The main OverBoard GUI uses Python 3; however, experiments can be logged from both Python 2 and 3 scripts.

The main dependencies are PyQt 5 and PyQtGraph. These can be installed as follows:

- With Conda: `conda install pyqt pyqtgraph -c anaconda`

- With pip: `pip install pyqt5 pyqtgraph`

Finally, OverBoard itself can be installed with: `pip install overboard`

## Usage

- Main interface: `python3 -m overboard <logs-directory>`

- Logging experiments is simple:
```
from overboard import Logger

with Logger('./logs') as logger:
  for iteration in range(100):
    logger.append({'loss': 0, 'error': 0})
```

See the `examples` directory for more details.

- `examples/synthetic.py`: Generate some test logs.
- `examples/mnist.py`: The mandatory MNIST example. Also includes custom MatPlotLib plots.

## Remote experiments

The easiest way to monitor remote experiments is to mount their directory over SFTP, and point OverBoard to it.

Tested with: [SSHFS](https://github.com/libfuse/sshfs) (Linux, available in most distros), [FUSE](https://osxfuse.github.io/) (Mac), [SFTP NetDrive](https://www.nsoftware.com/sftp/netdrive/) (Windows).

Since most of these don't allow OverBoard to monitor log files with the default light-weight method, the plots may not update automatically; in that case use the command-line argument `--force-reopen-files`.

## Author

[João Henriques](http://www.robots.ox.ac.uk/~joao/), [Visual Geometry Group (VGG)](http://www.robots.ox.ac.uk/~vgg/), University of Oxford

