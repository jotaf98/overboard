# OverBoard
OverBoard is a lightweight yet powerful dashboard to monitor your experiments.

<br>
<p align="center">
Load <b>remote experiments in real-time</b> through <b>SSH/FTP</b> and <a href="https://www.pyfilesystem.org/page/index-of-filesystems/">others</a>.
</p>
<img align="center" src="https://raw.githubusercontent.com/jotaf98/overboard/master/images/screen1.png" /><br><br>

<p align="center">
Custom visualisations (tensors and any custom plot with familiar <b>MatPlotLib</b> syntax).</p>
<img align="center" src="https://raw.githubusercontent.com/jotaf98/overboard/master/images/screen2.png" /><br><br>

<p align="center">
A sortable table of <b>hyper-parameters</b> with Python-syntax filtering.
</p>
<img align="center" src="https://raw.githubusercontent.com/jotaf98/overboard/master/images/screen8.png" /><br><br>

<p align="center">
<b>Plot percentile intervals (<b>shaded plots</b>), custom X/Y axes</b>, and hyper-parameters (<b>bubble plots</b>).
</p>
<img align="center" src="https://raw.githubusercontent.com/jotaf98/overboard/master/images/screen7.png" /><br>



# Installation

You can install the dependencies with:

- With Conda: `conda install pyqt=5.12 pyqtgraph=0.11 -c conda-forge`

- With pip: `pip install pyqt5==5.12 pyqtgraph==0.11`

Finally, OverBoard itself can be installed with: `pip install fs==2.4 overboard`
(Conda seems to be too strict when installing [PyFileSystem/fs](https://www.pyfilesystem.org), so pip should be preferred.)

Optional:
- `pip install fs.sshfs` to support remote files through SSH.

- PyOpenGL 3.1 (either through conda or pip) if you intend to use custom 3D plots with [PyQtGraph](https://pyqtgraph.readthedocs.io/en/latest/3dgraphics.html).

- MatPlotLib if you intend to use it for custom plots.



## Installation - logger only

Your scripts can log data without installing the full GUI and its dependencies (so your remote GPU cluster does not need PyQt at all).

Just use: `pip install overboard_logger`

And remember to import `overboard_logger` instead of `overboard` in your scripts.


# Usage

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

- [`examples/basic.py`](examples/basic.py): A minimal example. Generates some test logs.
- [`examples/mnist.py`](examples/mnist.py): The mandatory MNIST example. Also shows a custom MatPlotLib plot (a confusion matrix).
- [`examples/example_2d.py`](examples/example_2d.py): Example custom 2D plot, with PyQtGraph (faster than MatPlotLib).
- [`examples/example_3d.py`](examples/example_3d.py): Example custom 3D plot, with PyQtGraph. Requires PyOpenGL.

A note about importing: You can either import the `Logger` class from `overboard` or from `overboard_logger`. If you installed the "logger only" version as described above (no dependencies), then you can only import from `overboard_logger`.


## Remote experiments

It's as simple as:

```
python -m overboard ssh://username:password@hostname/path-to-experiments
```

...replacing your SSH user name, password, host name/server, and the directory where OverBoard should look for experiments. The default port is 22, which you can override with :23 or another port number after the host name.

There are a [number of other settings](https://github.com/althonos/fs.sshfs#constructor), which you can append after the path. For example, append `?keepalive=60&config_path=~/.ssh/config` to set the keepalive packets interval to 60 seconds, and specify an OpenSSH configuration file path.

[Other remote file systems](https://www.pyfilesystem.org/page/index-of-filesystems/) are available by using [appropriate prefixes](https://docs.pyfilesystem.org/en/latest/openers.html) (e.g. `ftp://`).


## Interface tips & tricks

- Click a plot title to hide it (moving it to the bottom) or to show it again.

- Click a plot line to select that experiment in the table, and vice-versa.

- Use the mouse wheel to zoom and drag to pan in a plot or custom visualization.

- Click the "A" button in the bottom-left of a plot to reset the zoom/pan.

- Choose an hyper-parameter as the "X axis" in the sidebar to compare different hyper-parameters graphically (*bubble plot*). Click a bubble to highlight that experiment. If the hyper-parameter is numerical but has wildly different orders of magnitude, check "Treat X as categorical". By default, each bubble's Y coordinate (e.g. accuracy) is taken from the last iteration; in "Scalar display" you can choose the maximum or minimum across iterations.

- If you have multiple runs with different random seeds (stored as hyper-parameter "seed" for example), select "Merge: seed" in the sidebar to merge them into *shaded plots* (you can then select whether to show the mean, median, range or standard deviations).

- You can *split* all experiments into different plots by selected "Panels: One per run" in the sidebar, and selecting a metric to plot in "Y axis". Similarly, they can be split by a hyper-parameter value (e.g. a different algorithm in each panel, but each has multiple plots/runs).


## Author

[João Henriques](http://www.robots.ox.ac.uk/~joao/), [Visual Geometry Group (VGG)](http://www.robots.ox.ac.uk/~vgg/), University of Oxford

