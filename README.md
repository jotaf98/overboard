# OverBoard
Pure Python dashboard for monitoring deep learning experiments (a.k.a. TensorBoard clone for PyTorch)

## Installation

The main OverBoard GUI uses Python 3; however, experiments can be logged from both Python 2 and 3 scripts.

The main dependencies are PyQt 5 and PyQtGraph. These can be installed as follows:

- With Conda: `conda install pyqt pyqtgraph -c anaconda`

- With pip: `pip install pyqt5 pyqtgraph`

Finally, OverBoard itself can be installed with `pip install overboard`.

## Usage

- Main interface: `python3 -m overboard <logs-directory>`.

- Logging experiments is simple:
```
from overboard import Logger

with Logger('./logs', ['loss', 'error]) as logger:
  for iteration in range(100):
    logger.append({'loss': 0, 'error': 0})
```

See the `examples` directory for more details.

- `examples/synthetic.py`: Generate some test logs.
- `examples/mnist.py`: The mandatory MNIST example.

## Author

[Joao Henriques](http://www.robots.ox.ac.uk/~joao/)

