
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

import pyqtgraph as pg


class FancyAxis(pg.AxisItem):
  def __init__(self, *args, first=True, backgroundColor="#EAEAF2", tickColor="white", tickWidth=2, **kwargs):
    super(FancyAxis, self).__init__(*args, **kwargs)
    self.backgroundColor = backgroundColor
    self.tickColor = tickColor
    self.tickWidth = tickWidth

  def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
    p.setRenderHint(p.Antialiasing, False)
    p.setRenderHint(p.TextAntialiasing, True)
    
    # draw background rect
    if self.backgroundColor:
      linkedView = self.linkedView()
      if linkedView is None or self.grid is False:
        rect = bounds
      else:
        rect = linkedView.mapRectToItem(self, linkedView.boundingRect())
      p.fillRect(rect, QtGui.QColor(self.backgroundColor))

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


def create_plot_widget(title):
  # create our special axis. only one of them draws the background.
  axis = {'left': FancyAxis('left', backgroundColor=None), 'bottom': FancyAxis('bottom')}
  font = QtGui.QFont()
  font.setPixelSize(14)
  for ax in axis.values():
    ax.tickFont = font
    ax.setStyle(tickTextOffset=10)  # , tickTextWidth=30, tickTextHeight=18  # last ones seem to have no effect

  # create plot widget and activate grid
  plot_widget = pg.PlotWidget(axisItems=axis)
  plot_widget.showGrid(x=True, y=True, alpha=255)

  return plot_widget


