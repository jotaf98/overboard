# OverBoard
Pure Python dashboard for monitoring deep learning experiments (a.k.a. TensorBoard clone for PyTorch)

## Work-in-progress

## Requirements:

- Python 3.6
- PyQt 5
- PyQtGraph 0.10

With Conda, just run: `conda install pyqt pyqtgraph -c anaconda`

Note that you can probably log experiments from a Pyton 2 script, since it only has to load the `logger` module.

However, the main OverBoard interface (`overboard.py`) requires Python 3.

## Usage

All the following commands assume you navigated to the OverBoard directory (`cd <overboard-path>`).

Make the OverBoard package available on the Python path: `pip install -e .`

Generate some test logs (gradually over time): `python3 ./examples/synthetic.py`

On a different console, navigate to the same path and run `python3 overboard.py ./logs`

To show MNIST training instead of synthetic logs, run `python3 ./examples/mnist.py`.

## Author

[João F. Henriques](http://www.robots.ox.ac.uk/~joao/)

