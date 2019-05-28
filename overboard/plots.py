
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from itertools import product, cycle, count
from functools import partial
import heapq, logging
import numpy as np

import pyqtgraph as pg

from .plotwidget import create_plot_widget

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

  def add(self, plots):
    # e.g.: plots.add(exp.enumerate_plots())
    plotsize = None
    for plot in plots:
      # check if panel exists. there's a different panel for each x coordinate (e.g. iterations, time)
      panel_id = (plot['panel'], plot['x'])
      if panel_id not in self.panels:
        # create new panel to contain plot.
        # if title not defined, use the panel ID (e.g. stat name)
        title = str(plot.get('title', plot['panel']))
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

        self.panels[panel_id] = panel
      else:
        panel = self.panels[panel_id]  # reuse existing panel
      
      # get data points
      exp = plot['exp']
      (xs, ys) = (exp.data[exp.names.index(plot['x'])], exp.data[exp.names.index(plot['y'])])

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
  
  def remove(self, plots):
    for plot in plots:
      # find panel
      panel_id = (plot['panel'], plot['x'])
      if panel_id in self.panels:
        panel = self.panels[panel_id]

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
          del self.panels[panel_id]

  def update_plots(self, experiments):
    # called by a timer to update plots periodically
      for exp in experiments:
        try:
          if not exp.done and next(exp.read_data):  # check if there's new data in the file
            self.add(exp.enumerate_plots())  # update plots
        except IOError:
          logging.exception('Error reading ' + exp.filename)
        except StopIteration:
          pass


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
    if x.is_integer(): x = str(int(x))
    else: x = float('%.3g' % x)
    if y.is_integer(): y = str(int(y))
    else: y = float('%.3g' % y)
    text = "%s<br/>(%s, %s)" % (names, x, y)
  else:
    text = ""

  panel.cursor_label.setText(text)  #, size='10pt'
  panel.cursor_vline.setValue(x)


def mouse_leave(event, panel):
  # hide cursor when the mouse leaves
  panel.cursor_vline.setVisible(False)

