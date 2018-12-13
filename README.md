# OverBoard
Pure Python dashboard for monitoring deep learning experiments (a.k.a. TensorBoard clone for PyTorch)

## Work-in-progress

## Requirements:

- Python 3.6
- PyQt 5
- PyQtGraph 0.10
- NumPy

Note that you can probably log experiments from a Pyton 2 script, since it only has to load the `logger` module.

However, the main OverBoard interface (`overboard.py`) requires Python 3.

## Usage

Run `examples/synthetic.py` to generate some logs.

The command line interface to visualize results is `python3 overboard.py <directory-name>` (pointing it to the main directory where logs are located).

`examples/mnist.py` shows a fully-integrated PyTorch example.

## Author

[João F. Henriques](http://www.robots.ox.ac.uk/~joao/)

