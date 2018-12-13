
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from itertools import product, cycle, count
from functools import partial
import heapq
import numpy as np

import pyqtgraph as pg

import plotwidget

# define lists of styles to cycle
palette = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]
dashes = [QtCore.Qt.SolidLine, QtCore.Qt.DashLine, QtCore.Qt.DotLine, QtCore.Qt.DashDotLine, QtCore.Qt.DashDotDotLine]
dashes_by_name = dict(zip(['-', '--', ':', '-.', '-..'], dashes))
widths = [2, 1, 3]  # line widths


class Plots():
  def __init__(self, window):
    self.window = window
    window.plots = self  # back-reference

    self.panels = {}
    self.unused_styles = []
    self.style_generator = self.style_generator()

    pg.setConfigOptions(antialias=True, background='w', foreground='k')
  
  def style_generator(self):
    # generate combinations of styles
    styles = ({'color': color, 'style': dash, 'width': width}
      for (width, dash, color) in product(widths, dashes, palette))
    
    # cycle if the list is exhausted, and append a count (style_order) to each entry to enable sorting
    styles = zip(count(0), cycle(styles))

    while True:
      # get an unused style if possible, using the lowest-index one
      if len(self.unused_styles) > 0:
        (style_order, style) = heapq.heappop(self.unused_styles)
      else:
        # get another default style
        (style_order, style) = next(styles)
      yield (style_order, style)

  def drop_style(self, style_order, style):
    # return a style to the set of available ones
    heapq.heappush(self.unused_styles, (style_order, style))

  def add(self, plots):
    # e.g.: plots.add(exp.enumerate_plots())
    plotsize = None
    for plot in plots:
      # check if panel exists. there's a different panel for each x coordinate (e.g. iterations, time)
      panel_id = (plot['panel'], plot['x'])
      if panel_id not in self.panels:  # create new panel
        widget = plotwidget.create_plot_widget()

        # set size based on size slider
        if plotsize is None:
          plotsize = self.window.size_slider.value()
        widget.setFixedWidth(plotsize)
        widget.setFixedHeight(plotsize)

        self.window.flow_layout.addWidget(widget)  # add to window's flow layout

        # if title not defined, use the panel ID (e.g. stat name)
        widget.setTitle(str(plot.get('title', plot['panel'])))

        widget.plots_dict = {}
        
        # set up mouse move event
        widget.mouseMoveEvent = partial(mouse_move, widget=widget)
        widget.leaveEvent = partial(mouse_leave, widget=widget)

        # mouse cursor (vertical line)
        vline = pg.InfiniteLine(angle=90, pen="#B0B0B0")
        vline.setVisible(False)
        widget.getPlotItem().addItem(vline, ignoreBounds=True)  # ensure it doesn't mess autorange
        widget.cursor_vline = vline

        # mouse cursor text
        label = pg.LabelItem(justify='left')
        label.setParentItem(widget.getPlotItem().getViewBox())
        label.anchor(itemPos=(0, 0), parentPos=(0, 0))
        widget.cursor_label = label

        self.panels[panel_id] = widget
      else:
        widget = self.panels[panel_id]  # reuse existing panel
      
      # get data points
      exp = plot['exp']
      (xs, ys) = (exp.data[exp.names.index(plot['x'])], exp.data[exp.names.index(plot['y'])])

      # get the plot style associated with this experiment
      if len(exp.style) == 0:
        (exp.style_order, exp.style) = next(self.style_generator)  # get a new style
      style = exp.style

      # allow overriding the style
      if 'color' in plots:
        style['color'] = plots['color']
      if 'width' in plots:
        style['width'] = plots['width']
      if 'dash' in plots and plots['dash'] in dashes_by_name:
        style['style'] = dashes_by_name[plots['dash']]
      
      try:
        pen = pg.mkPen(style)
      except:  # if the style is malformed, use the default style
        pen = pg.mkPen(exp.style)
      
      # check if plot line already exists
      if plot['line'] not in widget.plots_dict:
        # create new line
        line = widget.getPlotItem().plot(xs, ys, pen=pen)
        
        line.curve.setClickable(True, 8)  # size of hover region
        line.mouse_over = False
        
        widget.plots_dict[plot['line']] = line
        exp._plots.append(line)  # register in experiment (to toggle visibility)
      else:
        # update existing one
        line = widget.plots_dict[plot['line']]
        line.setData(xs, ys)
        line.setPen(pen)
  
  def remove(self, plots):
    for plot in plots:
      # find panel
      panel_id = (plot['panel'], plot['x'])
      if panel_id in self.panels:
        widget = self.panels[panel_id]

        # find plot line
        line_id = plot['line']
        if line_id in widget.plots_dict:
          # remove it
          widget.removeItem(widget.plots_dict[line_id])
          del widget.plots_dict[line_id]
        
        # if the last line was deleted, delete the panel too
        if len(widget.plots_dict) == 0:
          widget.setParent(None)
          widget.deleteLater()
          del self.panels[panel_id]

  def update_plots(self, experiments):
    # called by a timer to update plots periodically
    for exp in experiments:
      if not exp.done and next(exp.read_data):  # check if there's new data in the file
        self.add(exp.enumerate_plots())  # update plots



def mouse_move(event, widget):
  # select curves when hovering them, and update mouse cursor
  viewbox = widget.getPlotItem().vb
  point = viewbox.mapSceneToView(event.pos())
  
  selected = None
  for line in widget.plots_dict.values():
    # only the first one gets selected
    inside = (not selected and line.curve.mouseShape().contains(point))

    if inside:
      selected = line
      if not line.mouse_over:
        # change line style to thicker
        line.original_pen = line.opts['pen']
        pen = pg.mkPen(line.original_pen)
        pen.setWidth(3)
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
  widget.cursor_vline.setVisible(True)
  x = point.x()

  if selected:
    # snap vertical line to nearest point (by x coordinate)
    data = selected.getData()
    index = np.argmin(np.abs(data[0] - x))
    (x, y) = (data[0][index], data[1][index])

    # show data coordinates
    names = [name for (name, line) in widget.plots_dict.items() if line is selected]  # ideally should return only 1
    names = ' '.join(names)
    # this trick prints floats with 3 significant digits and no sci notation (e.g. 1e-4). also consider integers.
    if x == int(x): x = str(int(x))
    else: x = float('%.3g' % x)
    if y == int(y): y = str(int(y))
    else: y = float('%.3g' % y)
    text = "%s<br/>(%s, %s)" % (names, x, y)
  else:
    text = ""

  widget.cursor_label.setText(text)  #, size='10pt'
  widget.cursor_vline.setValue(x)


def mouse_leave(event, widget):
  # hide cursor when the mouse leaves
  widget.cursor_vline.setVisible(False)

