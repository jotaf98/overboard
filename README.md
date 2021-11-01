# OverBoard
OverBoard is a lightweight yet powerful dashboard to monitor your experiments.

<p align="center">
<img align="center" alt="editor" src="https://raw.githubusercontent.com/jotaf98/overboard/master/demo.gif" />
</p>


## Features

- A table of **hyper-parameters** with Python-syntax filtering.

- Multiple views of the same data (i.e. **custom X/Y axes**).

- Hyper-parameter visualisation (i.e. **bubble plots**).

- Percentile intervals for multiple runs (i.e. **shaded plots**).

- Custom visualisations (tensors and any custom plot with familiar **MatPlotLib** syntax).

- **Fast** client-side rendering (the training code is kept lightweight).



## Installation

You can install the dependencies with:

- With Conda: `conda install pyqt=5.12 pyqtgraph=0.12 -c conda-forge`

- With pip: `pip install pyqt5==5.12 pyqtgraph==0.12`

If you intend to use custom 3D plots with [PyQtGraph](https://pyqtgraph.readthedocs.io/en/latest/3dgraphics.html), add PyOpenGL 3.1 to the lists above.

Finally, OverBoard itself can be installed with: `pip install overboard`


## Installation - logger only

Your scripts can log data without installing the full GUI and its dependencies (so your remote GPU cluster does not need PyQt at all).

Just use: `pip install overboard_logger`

And remember to import `overboard_logger` instead of `overboard` in your scripts.


## Usage

- Main interface: `python3 -m overboard <logs-directory>`

- Logging experiments is simple:
```python
from overboard import Logger

with Logger('./logs') as logger:
  for iteration in range(100):
    logger.append({'loss': 0, 'error': 0})
```

You can also pass in a `meta` keyword argument, which can be a `dict` with hyper-parameters names and values (or other meta-data), to help organize your experiments. These will be displayed in a handy table, which supports sorting and filtering. The `meta` data can also be an `argparse.Namespace`, which is useful if your hyper-parameters are command-line arguments parsed with `argparse`.

By default a unique folder (using the current timestamp) is created for the logs. For full documentation on initialization arguments and other methods, type `pydoc overboard` on the command-line (Python built-in doc viewer).

You can also check the `examples` directory:

- `examples/synthetic.py`: A minimal example. Generates some test logs.
- `examples/mnist.py`: The mandatory MNIST example. Also includes custom MatPlotLib plots.

A note about importing: You can either import the `Logger` class from `overboard` or from `overboard_logger`. If you installed the "logger only" version as described above (no dependencies), then you can only import from `overboard_logger`.


## Remote experiments

The easiest way to monitor remote experiments is to mount their directory over SFTP, and point OverBoard to it.

Tested with: [SSHFS](https://github.com/libfuse/sshfs) (Linux, available in most distros), [FUSE](https://osxfuse.github.io/) (Mac), [SFTP NetDrive](https://www.nsoftware.com/sftp/netdrive/) (Windows).

Since most of these don't allow OverBoard to monitor log files with the default light-weight method, the plots may not update automatically; in that case use the command-line argument `--force-reopen-files`.

Depending on the remote server's configuration (e.g. firewall settings), you might need to use a VPN to tunnel to the server's network, to ensure that the right ports are not blocked to you (i.e. having SSH access does not guarantee SFTP access from an external network).


## Author

[João Henriques](http://www.robots.ox.ac.uk/~joao/), [Visual Geometry Group (VGG)](http://www.robots.ox.ac.uk/~vgg/), University of Oxford

