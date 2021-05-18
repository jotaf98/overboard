# OverBoard
OverBoard is a lightweight yet powerful dashboard to monitor your experiments.

<p align="center">
<img align="center" alt="editor" src="https://raw.githubusercontent.com/jotaf98/overboard/master/demo.gif" />
</p>


## Features

- A table of hyper-parameters with Python-syntax filtering

- Multiple views of the same data (i.e. custom X/Y axes)

- Hyper-parameter visualisation (i.e. bubble plots)

- Percentile intervals for multiple runs (i.e. shaded plots)

- Custom visualisations (tensors and any custom plot with familiar MatPlotLib syntax)

- Fast client-side rendering (the training code is kept lightweight)


## Installation

The main OverBoard GUI uses Python 3; however, experiments can be logged from both Python 2 and 3 scripts.

The main dependencies are PyQt 5 and PyQtGraph. These can be installed as follows:

- With Conda: `conda install pyqt pyqtgraph -c anaconda`

- With pip: `pip install pyqt5 pyqtgraph`

Finally, OverBoard itself can be installed with: `pip install overboard`


## Usage

- Main interface: `python3 -m overboard <logs-directory>`

- Logging experiments is simple:
```python
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

