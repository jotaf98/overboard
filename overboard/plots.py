
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from itertools import product, cycle, count
from functools import partial
import heapq, logging
from datetime import datetime
import numpy as np

import pyqtgraph as pg

from .plotwidget import create_plot_widget
from .pg_time_axis import timestamp, DateAxisItem

# define lists of styles to cycle
palette = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]
dashes = [QtCore.Qt.SolidLine, QtCore.Qt.DashLine, QtCore.Qt.DotLine, QtCore.Qt.DashDotLine, QtCore.Qt.DashDotDotLine]
dashes_by_name = dict(zip(['-', '--', ':', '-.', '-..'], dashes))
widths = [2, 1, 3]  # line widths


class Plots():
  def __init__(self, window):
    self.window = window
    window.plots = self  # back-reference

    self.panels = {}  # widgets containing plots, indexed by name (usually the plot title at the top)
    self.unused_styles = []  # reuse styles from hidden experiments. this is a heap so early styles have priority.
    self.next_style_index = 0

    pg.setConfigOptions(antialias=True, background='w', foreground='k')  # black on white

  def get_style(self):
    # reuse a previous style if possible, in order
    if len(self.unused_styles) > 0:
      return heapq.heappop(self.unused_styles)
    
    # otherwise, get a new one. start by varying color, then dashes, then line width.
    idx = self.next_style_index
    color = palette[idx % len(palette)]
    dash = dashes[(idx // len(palette)) % len(dashes)]
    width = widths[(idx // (len(palette) * len(dashes))) % len(widths)]

    self.next_style_index = idx + 1

    return (idx, {'color': color, 'style': dash, 'width': width})
  
  def drop_style(self, style_order, style):
    # return a style to the set of available ones
    heapq.heappush(self.unused_styles, (style_order, style))

  def get_plot_info(self, exp):
    x_name = exp.names[0]
    return [{
      'panel': (x_name, y_name),
      'line': exp.name,
      'x': x_name,
      'y': y_name,
      'width': 4 if exp.is_selected else 2
    } for y_name in exp.names[1:]]

  def add(self, exp):
    plots = self.get_plot_info(exp)
    plotsize = None
    for plot in plots:
      # get data points
      (xs, ys) = (exp.data[exp.names.index(plot['x'])], exp.data[exp.names.index(plot['y'])])

      # check if panel exists. there's a different panel for each x coordinate (e.g. iterations, time)
      if plot['panel'] not in self.panels:
        # create new panel to contain plot.
        # if title not defined, use the panel ID (e.g. stat name)
        title = str(plot.get('title', plot['panel'][1]))
        plot_widget = create_plot_widget(title)
        panel = self.window.add_panel(plot_widget, title)

        panel.plots_dict = {}
        
        # set up mouse move event
        plot_widget.mouseMoveEvent = partial(mouse_move, panel=panel)
        plot_widget.leaveEvent = partial(mouse_leave, panel=panel)

        # mouse cursor (vertical line)
        vline = pg.InfiniteLine(angle=90, pen="#B0B0B0")
        vline.setVisible(False)
        plot_widget.getPlotItem().addItem(vline, ignoreBounds=True)  # ensure it doesn't mess autorange
        panel.cursor_vline = vline

        # mouse cursor text
        label = pg.LabelItem(justify='left')
        label.setParentItem(plot_widget.getPlotItem().getViewBox())
        label.anchor(itemPos=(0, 0), parentPos=(0, 0))
        panel.cursor_label = label

        self.panels[plot['panel']] = panel

        # create time axes if needed
        if len(xs) > 0 and isinstance(xs[0], datetime):
          axis = DateAxisItem(orientation='bottom')
          axis.attachToPlotItem(plot_widget.getPlotItem())

        if len(ys) > 0 and isinstance(ys[0], datetime):
          axis = DateAxisItem(orientation='left')
          axis.attachToPlotItem(plot_widget.getPlotItem())

      else:
        panel = self.panels[plot['panel']]  # reuse existing panel
      
      # convert timedates to numeric values if needed
      if len(xs) > 0 and isinstance(xs[0], datetime):
        xs = [timestamp(x) for x in xs]
      if len(ys) > 0 and isinstance(ys[0], datetime):
        ys = [timestamp(y) for y in ys]

      # allow overriding the style
      style = exp.style
      if 'color' in plot:
        style['color'] = plot['color']
      if 'width' in plot:
        style['width'] = plot['width']
      if 'dash' in plot and plot['dash'] in dashes_by_name:
        style['style'] = dashes_by_name[plot['dash']]
      
      try:
        pen = pg.mkPen(style)
      except:  # if the style is malformed, use the default style
        pen = pg.mkPen(exp.style)
      
      # check if plot line already exists
      if plot['line'] not in panel.plots_dict:
        # create new line
        line = panel.plot_widget.getPlotItem().plot(xs, ys, pen=pen)
        
        line.curve.setClickable(True, 8)  # size of hover region
        line.mouse_over = False
        
        panel.plots_dict[plot['line']] = line
      else:
        # update existing one
        line = panel.plots_dict[plot['line']]
        line.setData(xs, ys)
        line.setPen(pen)
  
  def remove(self, exp):
    plots = self.get_plot_info(exp)
    for plot in plots:
      # find panel
      if plot['panel'] in self.panels:
        panel = self.panels[plot['panel']]

        # find plot line
        line_id = plot['line']
        if line_id in panel.plots_dict:
          # remove it
          plot_item = panel.plot_widget.getPlotItem()
          plot_item.removeItem(panel.plots_dict[line_id])
          del panel.plots_dict[line_id]
        
        # if the last line was deleted, delete the panel too
        if len(panel.plots_dict) == 0:
          panel.setParent(None)
          panel.deleteLater()
          del self.panels[plot['panel']]


def mouse_move(event, panel):
  # select curves when hovering them, and update mouse cursor
  viewbox = panel.plot_widget.getPlotItem().vb
  point = viewbox.mapSceneToView(event.pos())
  
  selected = None
  for line in panel.plots_dict.values():
    # only the first one gets selected
    inside = (not selected and line.curve.mouseShape().contains(point))

    if inside:
      selected = line
      if not line.mouse_over:
        # change line style to thicker
        line.original_pen = line.opts['pen']
        pen = pg.mkPen(line.original_pen)
        pen.setWidthF(line.original_pen.widthF() + 2)
        line.setPen(pen)

        # bring it to the front
        line.setZValue(1)

        line.mouse_over = True
    else:
      if line.mouse_over:
        # restore line style and z-order
        line.setPen(line.original_pen)
        line.setZValue(0)
        line.mouse_over = False

  # show cursor (vertical line)
  panel.cursor_vline.setVisible(True)
  x = point.x()

  if selected:
    # snap vertical line to nearest point (by x coordinate)
    data = selected.getData()
    index = np.argmin(np.abs(data[0] - x))
    (x, y) = (data[0][index], data[1][index])

    # show data coordinates
    names = [name for (name, line) in panel.plots_dict.items() if line is selected]  # ideally should return only 1
    names = ' '.join(names)
    # this trick prints floats with 3 significant digits and no sci notation (e.g. 1e-4). also consider integers.
    if x % 1 == 0: x = str(int(x))
    else: x = float('%.3g' % x)
    if y % 1 == 0: y = str(int(y))
    else: y = float('%.3g' % y)
    text = "%s<br/>(%s, %s)" % (names, x, y)
  else:
    text = ""

  panel.cursor_label.setText(text)  #, size='10pt'
  panel.cursor_vline.setValue(x)


def mouse_leave(event, panel):
  # hide cursor when the mouse leaves
  panel.cursor_vline.setVisible(False)



class Smoother():
  def __init__(self, bandwidth, half_window=None):
    if bandwidth == 0:
      self.kernel = None
    else:
      if half_window is None:
        half_window = int(np.ceil(bandwidth * 2))
      self.kernel = np.exp(-np.arange(-half_window, half_window + 1)**2 / bandwidth**2)
    self.changed = True

  def do(self, x):
    if not isinstance(x, np.ndarray):
      x = np.array(x)
    if self.kernel is None or len(x) == 0:
      return x
    # dividing by the convolution of the kernel with a signal of all-ones handles correctly the lack of points at the edges (without biasing to a particular value)
    y = np.convolve(x, self.kernel, mode='same') / np.convolve(np.ones_like(x), self.kernel, mode='same')
    if len(self.kernel) > len(x):  # crop if larger (happens when filter is larger than signal, see np.convolve)
      start = len(y) // 2 - len(x) // 2
      y = y[start : start + len(x)]
    return y
