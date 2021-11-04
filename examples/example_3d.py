
"""
Example 3D visualizations on OverBoard. Requires PyOpenGL.
"""

from overboard_logger import Logger

from pyqtgraph.Qt import QtGui
import pyqtgraph.opengl as gl
import numpy as np
import time, sys


def plot_example(name, color):
  # create a widget to hold the 3D plot
  widget = gl.GLViewWidget()
  widget.setCameraPosition(distance=5)

  # show a grid
  grid = gl.GLGridItem()
  grid.scale(0.2, 0.2, 1)
  grid.setDepthValue(10)  # draw grid after surfaces since they may be translucent
  widget.addItem(grid)

  # compute a saddle function for a grid of x and y coordinates
  n = 20
  x = np.linspace(-1, 1, n)
  y = np.linspace(-1, 1, n)
  z = (x.reshape(n, 1) ** 2) - (y.reshape(1, n) ** 2)

  # create a shaded surface with those coordinates
  plot_item = gl.GLSurfacePlotItem(x=x, y=y, z=z, drawFaces=True,
    drawEdges=False, shader='shaded', color=color)
  widget.addItem(plot_item)

  return widget


if __name__ == '__main__':  # important to avoid running when just loading the module
  if sys.argv[-1] != 'debug':  # a command-line option
    
    print("Open OverBoard in another terminal: python3 -m overboard ./logs/example-3d")

    # open file for logging
    with Logger('./logs/example-3d/') as logger:
      for iteration in range(100):  # simulate a training run
        # this is where we would append some statistics to the log
        logger.append(dict(random=np.random.rand()))

        # store a visualization once every 10 seconds
        if logger.rate_limit(10):
          # to show some change, use a different color every time
          color = np.random.rand(4) / 2 + 0.5  # random bright colour (RGBA)
          color[3] = 1.0  # set alpha (opacity) to 1
          logger.visualize(plot_example, '3D example', color)

        print(f"Iteration {iteration}")
        time.sleep(1)  # wait 1 second

  else:
    # if passing the 'debug' command-line argument, this shows the 3D plot in a
    # stand-alone window, instead of logging on OverBoard (useful for debugging)
    app = QtGui.QApplication([])
    plot_example('3D example', (1, 0.5, 0, 0)).show()
    QtGui.QApplication.instance().exec_()  # start Qt event loop
