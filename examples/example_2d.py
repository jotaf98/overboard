
"""
Example 2D visualizations on OverBoard, using PyQtGraph (faster than MatPlotLib)
"""

from overboard_logger import Logger

import pyqtgraph as pg
from pyqtgraph.Qt import QtGui
import numpy as np
import time, sys



def plot_example(name, means, stds):
  # create a plot canvas
  item = pg.PlotItem()

  # sample some normal-distributed data clusters
  data = np.random.normal(size=(20, 4), loc=means, scale=stds).T

  # add scatter plots on top. symbolBrush is used to cycle through colors.
  for i in range(4):
    xvals = pg.pseudoScatter(data[i], spacing=0.4, bidir=True) * 0.2
    item.plot(x=xvals + i, y=data[i], pen=None, symbol='o',
      symbolBrush=pg.intColor(i, 6, maxValue=128))

  # show some error bars
  err = pg.ErrorBarItem(x=np.arange(4), y=data.mean(axis=1),
    height=data.std(axis=1), beam=0.5, pen={'width': 2, 'color': 'k'})
  item.addItem(err)

  # important: return the PlotItem (or a list of them), instead of showing it
  return item


if __name__ == '__main__':  # important to avoid running when just loading the module
  if sys.argv[-1] != 'debug':  # a command-line option
    
    print("Open OverBoard in another terminal: python3 -m overboard ./logs/example-3d")

    # open file for logging
    with Logger('./logs/example-2d/') as logger:
      for iteration in range(100):  # simulate a training run
        # this is where we would append some statistics to the log
        logger.append(dict(random=np.random.rand()))

        # store a visualization once every 10 seconds
        if logger.rate_limit(10):
          # create a different set of data clusters each time
          means = np.random.randint(low=0, high=10, size=(4,))
          stds = np.random.randint(low=1, high=5, size=(4,))

          logger.visualize(plot_example, '2D example', means, stds)

        print(f"Iteration {iteration}")
        time.sleep(1)  # wait 1 second

  else:
    # if passing the 'debug' command-line argument, this shows the plot in a
    # stand-alone window, instead of logging on OverBoard (useful for debugging)
    app = QtGui.QApplication([])
    pg.setConfigOption('background', 'w')
    pg.setConfigOption('foreground', 'k')
    window = pg.GraphicsLayoutWidget(title='2D example', show=True)
    window.addItem(plot_example('2D example', (2, 5, 3, 7), (1, 2, 4, 2)))
    QtGui.QApplication.instance().exec_()  # start Qt event loop
