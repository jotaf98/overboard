
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

import pyqtgraph as pg


class FancyAxis(pg.AxisItem):
  """PyQtGraph AxisItem that allows tick colors different from the grid color,
  a grid background color, and no axis lines. Default aspect is inspired by Seaborn.
  Note that only one axis should draw the background (the other's backgroundColor should be None)"""
  def __init__(self, *args, first=True, backgroundColor="#EAEAF2", tickColor="white", tickWidth=2, **kwargs):
    super(FancyAxis, self).__init__(*args, **kwargs)
    self.backgroundColor = backgroundColor
    self.tickColor = tickColor
    self.tickWidth = tickWidth
    self.z_is_set = False
  

  def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
    # if this axis is responsible for drawing the background, ensure
    # that the Z value is such that this does not occlude other axes
    if self.backgroundColor and not self.z_is_set:
      self.setZValue(self.zValue() - 1)
      self.z_is_set = True
    
    p.setRenderHint(p.Antialiasing, False)
    p.setRenderHint(p.TextAntialiasing, True)

    # draw background rect
    if self.backgroundColor:
      #bounds = self.mapRectFromParent(self.geometry())
      linkedView = self.linkedView()
      if linkedView is not None and self.grid is not False:
        bounds = linkedView.mapRectToItem(self, linkedView.boundingRect())
        p.fillRect(bounds, QtGui.QColor(self.backgroundColor))

    # draw ticks/grid
    for pen, p1, p2 in tickSpecs:
      pen.setColor(QtGui.QColor(self.tickColor))
      pen.setWidth(self.tickWidth)
      p.setPen(pen)
      p.drawLine(p1, p2)

    # draw all text
    if self.tickFont is not None:
      p.setFont(self.tickFont)
    p.setPen(self.pen())
    for rect, flags, text in textSpecs:
      p.drawText(rect, flags, text)


def create_plot_widget():
  # create our special axis. only one of them draws the background.
  axis = {'left': FancyAxis('left', backgroundColor=None), 'bottom': FancyAxis('bottom')}
  font = QtGui.QFont()
  font.setPixelSize(14)
  for ax in axis.values():
    ax.tickFont = font
    ax.setStyle(tickTextOffset=10)  # , tickTextWidth=30, tickTextHeight=18  # last ones seem to have no effect

  # create plot widget and activate grid
  plot_widget = pg.PlotWidget(axisItems=axis)
  plot_widget.showGrid(x=True, y=True, alpha=1)

  return plot_widget


