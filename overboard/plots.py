
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
from numbers import Number
from itertools import zip_longest
import numpy as np

import pyqtgraph as pg

from .plotwidget import create_plot_widget
from .pg_time_axis import timestamp, DateAxisItem

# define lists of styles to cycle
palette = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]
dashes = [QtCore.Qt.SolidLine, QtCore.Qt.DashLine, QtCore.Qt.DotLine, QtCore.Qt.DashDotLine, QtCore.Qt.DashDotDotLine]
#dashes_by_name = dict(zip(['-', '--', ':', '-.', '-..'], dashes))
widths = [2, 1, 3]  # line widths


class Plots():
  def __init__(self, window):
    self.window = window
    window.plots = self  # back-reference

    self.panels = {}  # widgets containing plots, indexed by name (usually the plot title at the top)
    self.hovered_line_id = None
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

  def define_plots(self, exp):
    """Defines plot information for a given experiment. Returns a list of dicts,
    each dict defining the properties of a single line (sources for x, y, color,
    panel, etc). This accesses the window widgets to check the current options."""

    x_option = self.window.x_dropdown.currentText()
    y_option = self.window.y_dropdown.currentText()
    panel_option = self.window.panel_dropdown.currentText()
    merge_option = self.window.merge_dropdown.currentText()

    # some combinations are invalid, change to sensible defaults in those cases
    if panel_option == "One per metric":
      if x_option != "Panel metric" and y_option != "Panel metric":  # Panel metric is unused, so all panels would look the same
        y_option = "Panel metric"
        self.window.y_dropdown.setCurrentText(y_option)
    
    else:
      # x/y_option "Panel metric" is only compatible with panel_option "One per metric"
      if x_option == "Panel metric":
        x_option = "First metric"
        self.window.x_dropdown.setCurrentText(x_option)
      if y_option == "Panel metric":
        y_option = "All metrics"
        self.window.y_dropdown.setCurrentText(y_option)

    if x_option == "All metrics" and y_option == "All metrics":
      x_option = "First metric"
      self.window.x_dropdown.setCurrentText(x_option)

    # get first metric for X or Y if requested
    x_name = (exp.names[0] if x_option == "First metric" else x_option)
    y_name = (exp.names[0] if y_option == "First metric" else y_option)

    # create list of panels by: metric, experiment, hyper-parameter type,
    # value of a single hyper-parameter, or create a single panel
    if panel_option == "One per metric":
      panels = [(x_name, name) for name in exp.names]

    elif panel_option == "One per run":
      panels = [(None, exp.name)]  # add() expects a tuple, using 2nd element for plot title
    
    elif panel_option == "Single panel":
      panels = [(None, y_name)]
    
    else:  # single hyper-parameter selected, create one panel for each value
      panels = [(None, panel_option + ' = ' + str(exp.meta.get(panel_option, None)))]  # None if missing

    # possibly merge lines by some hyper-parameter; otherwise, each experiment is unique
    merge_info = (None if merge_option == "Nothing" else exp.name)
    line_id = (exp.name if merge_option == "Nothing" else str(exp.meta[merge_option]))

    info = []  # the list of lines to plot
    for panel in panels:  # possibly spread plots across panels
      lines = [(x_name, y_name)]  # single line per panel, with these X and Y sources
      if x_option == "All metrics":  # several lines in a panel - one per metric
        lines = [(name, y_name) for name in exp.names]
      elif y_option == "All metrics":
        lines = [(x_name, name) for name in exp.names]

      for (x, y) in lines:  # possibly create multiple lines for this panel
        if x_option == "Panel metric": x = panel[1]  # different metrics per panel
        if y_option == "Panel metric": y = panel[1]

        # a plot with the same values on X and Y is redundant, so skip it
        if x == y: continue

        # label used for the X axis; only show if it's different from the default
        x_label = (None if x_option == "First metric" else x)

        # final touches and compose dict
        style = exp.name
        info.append(dict(panel=panel, x=x, y=y, style=style, x_label=x_label, line_id=(x, y, line_id), merge_info=merge_info))
    return info

  def add(self, exp):
    """Creates or updates plots associated with given experiment, creating panels if needed.
    If the experiment is marked as invisible/filtered, nothing will be drawn."""

    if not exp.visible or exp.is_filtered or len(exp.names) == 0:
      return False  # plots are invisible or no data loaded yet

    plots = self.define_plots(exp)
    for plot in plots:
      # create new panel if it doesn't exist
      if plot['panel'] not in self.panels:
        self.add_plot_panel(plot)

      panel = self.panels[plot['panel']]  # reuse existing panel
      plot_item = panel.plot_widget.getPlotItem()
      
      # get data points, pre-processed to ensure they are numeric. this may edit the axes.
      (xs, ys) = self.get_numeric_data_points(exp, plot, plot_item)

      # check if plot line already exists
      if plot['line_id'] not in panel.plots_dict:
        # create new line
        line = plot_item.plot([], [])
        line.curve.setClickable(True, 8)  # size of hover region
        panel.plots_dict[plot['line_id']] = line
      else:
        # update existing one
        line = panel.plots_dict[plot['line_id']]
      line.mouse_over = False

      # handle merged plots, by updating the statistics to display first
      if plot['merge_info'] is not None:
        (xs, ys, shade_y1, shade_y2) = self.update_merged_stats(line, xs, ys, exp.style, plot['merge_info'])

        # also, share the same style among a group of merged experiments
        if hasattr(line, 'style') and exp.style != line.style:
          exp.style = line.style
          self.window.redraw_icon(None, exp)  # update the icon

      # create pen with the experiment's style (line color, dashes and width)
      pen = pg.mkPen(exp.style)

      if exp.is_selected:  # selected lines are thicker
        pen.setWidth(exp.style.get('width', 2) + 2)
      
      # args to assign to PlotDataItem line
      data = dict(x=xs, y=ys, pen=pen)

      # for single points, plot a marker/symbol, since the line won't show up
      if len(xs) == 1:
        data['symbol'] = 'o'
        data['symbolBrush'] = pen.color()
        data['symbolSize'] = exp.style.get('width', 2) * 2 + 4

      # assign the point coordinates and visual properties to the PlotDataItem
      line.setData(**data)

      # finish merged plots, by plotting the confidence intervals
      if plot['merge_info'] is not None:
        if len(xs) > 1:
          # draw a shaded area. first, set the pen used to draw the outline of the shaded area
          outline_pen = pg.mkPen(pen)
          outline_pen.setWidthF(pen.widthF() / 3)
          
          if plot['line_id'] not in panel.aux_plots_dict:
            # create for first time. we need 2 curves, setting the upper and lower
            # limits, and then a FillBetweenItem to shade the space between them.
            limit1 = plot_item.plot([], [])
            limit2 = plot_item.plot([], [])
            shade = pg.FillBetweenItem(limit1, limit2, (200, 0, 0, 128))
            plot_item.addItem(shade)
            panel.aux_plots_dict[plot['line_id']] = (limit1, limit2, shade)
          else:
            (limit1, limit2, shade) = panel.aux_plots_dict[plot['line_id']]
          limit1.setData(x=xs, y=shade_y1, pen=outline_pen)
          limit2.setData(x=xs, y=shade_y2, pen=outline_pen)

          c = pen.color()  # shade using same color but semi-transparent
          shade.setBrush((c.red(), c.green(), c.blue(), 64))
        else:
          # a single point, plot as an error bar
          data = dict(x=xs, y=ys, bottom=ys-shade_y1, top=shade_y2-ys, pen=pen)
          if plot['line_id'] not in panel.aux_plots_dict:
            # create for first time
            bar = panel.aux_plots_dict[plot['line_id']] = pg.ErrorBarItem(**data)
            plot_item.addItem(bar)
          else:
            panel.aux_plots_dict[plot['line_id']].setData(**data)

    return len(plots) > 0  # True if some plots were actually drawn

  
  def add_plot_panel(self, plot):
    """Adds a single plot panel, from its description as output
    by define_plots. Used by Plots.add."""

    # create new panel to contain plot
    title = plot['panel'][1]
    plot_widget = create_plot_widget(title)
    panel = self.window.add_panel(plot_widget, title)

    plot_item = panel.plot_widget.getPlotItem()

    if plot['x_label'] is not None:  # set X axis label if needed
      plot_item.setLabel('bottom', plot['x_label'])

    # mouse cursor (vertical line)
    panel.cursor_vline = pg.InfiniteLine(angle=90, pen="#B0B0B0")
    panel.cursor_vline.setVisible(False)
    panel.cursor_vline.setZValue(10)
    plot_item.addItem(panel.cursor_vline, ignoreBounds=True)  # ensure it doesn't mess autorange

    # mouse cursor (dot)
    panel.cursor_dot = pg.PlotDataItem([], [], pen=None, symbolPen=None, symbolBrush="#C00000", symbol='o', symbolSize=7)
    panel.cursor_dot.setVisible(False)
    panel.cursor_dot.setZValue(10)
    plot_item.addItem(panel.cursor_dot, ignoreBounds=True)

    # mouse cursor text
    panel.cursor_label = pg.LabelItem(justify='left')
    panel.cursor_label.setParentItem(plot_item.getViewBox())
    panel.cursor_label.anchor(itemPos=(0, 0), parentPos=(0, 0))
    panel.cursor_label.setZValue(10)
    
    # set up mouse events
    plot_widget.mouseMoveEvent = partial(self.on_mouse_move, panel=panel)
    plot_widget.leaveEvent = partial(self.on_mouse_leave, panel=panel)
    plot_widget.mousePressEvent = partial(self.on_mouse_click, panel=panel)

    panel.plots_dict = {}
    panel.aux_plots_dict = {}
    self.panels[plot['panel']] = panel

  def get_numeric_data_points(self, exp, plot, plot_item):
    """Retrieves the data points for a single plot, from its define_plots
    description. Reduction to scalar (single point) is applied if needed, and
    time/categorical data is converted to numeric coordinates. Used by Plots.add."""

    if plot['x'] in exp.meta:
      xs = [exp.meta[plot['x']]]  # a single point, with the chosen hyper-parameter
    else:
      xs = exp.data[exp.names.index(plot['x'])]  # several points, with the chosen metric

    if plot['y'] in exp.meta:
      ys = [exp.meta[plot['y']]]
    else:
      ys = exp.data[exp.names.index(plot['y'])]

    # if one axis is a scalar (hyper-parameter) and another is not (metric), only show
    # a single data point. use "scalar display" option to decide which metric to keep.
    if len(xs) == 1 or len(ys) == 1:
      scalar_option = self.window.scalar_dropdown.currentText()
      if scalar_option == 'Last value':
        if len(xs) > 1: xs = [xs[-1]]
        if len(ys) > 1: ys = [ys[-1]]
      elif scalar_option == 'Maximum':
        if len(xs) > 1: xs = [max(xs)]
        if len(ys) > 1: ys = [max(ys)]
      elif scalar_option == 'Minimum':
        if len(xs) > 1: xs = [min(xs)]
        if len(ys) > 1: ys = [min(ys)]

    assert len(xs) == len(ys)

    # check data points' types to know what axes to create (numeric, time or categorical)
    x_is_time = all(isinstance(x, datetime) for x in xs)
    y_is_time = all(isinstance(y, datetime) for y in ys)
    x_is_numeric = len(xs) == 0 or all(isinstance(x, Number) and not isinstance(x, bool) for x in xs)
    y_is_numeric = len(xs) == 0 or all(isinstance(y, Number) and not isinstance(y, bool) for y in ys)

    # handle datetimes
    if x_is_time:
      # create time axes if needed, and convert datetimes to numeric values
      if not isinstance(plot_item.axes['bottom']['item'], DateAxisItem):
        axis = DateAxisItem(orientation='bottom')
        axis.attachToPlotItem(plot_item)
      xs = [timestamp(x) for x in xs]

    if y_is_time:
      if not isinstance(plot_item.axes['left']['item'], DateAxisItem):
        axis = DateAxisItem(orientation='left')
        axis.attachToPlotItem(plot_item)
      ys = [timestamp(y) for y in ys]

    # handle categorical values
    if not x_is_numeric:
      axes = plot_item.axes['bottom']['item']
      if axes._tickLevels is None:  # initialize
        axes.setTicks([[]])
        axes.ticks_dict = {}
        axes.next_tick = 0
      ticks_dict = axes.ticks_dict

      # TODO: improve performance
      xs = [str(x) for x in xs]  # ensure they're all strings
      for x in set(xs):  # iterate unique values
        if x not in axes.ticks_dict:  # add tick if this value is new
          ticks_dict[x] = axes.next_tick
          axes._tickLevels[0].append((axes.next_tick, x))
          axes.next_tick += 1

      xs = [ticks_dict[x] for x in xs]  # convert to numeric value, by look-up

    if not y_is_numeric:
      axes = plot_item.axes['left']['item']
      if axes._tickLevels is None:  # initialize
        axes.setTicks([[]])
        axes.ticks_dict = {}
        axes.next_tick = 0
      ticks_dict = axes.ticks_dict

      ys = [str(y) for y in ys]  # ensure they're all strings
      for y in set(ys):  # iterate unique values
        if y not in axes.ticks_dict:  # add tick if this value is new
          ticks_dict[y] = axes.next_tick
          axes._tickLevels[0].append((axes.next_tick, y))
          axes.next_tick += 1
          
      ys = [ticks_dict[y] for y in ys]  # convert to numeric value, by look-up
    
    return (xs, ys)

  def update_merged_stats(self, line, xs, ys, style, merge_info):
    # update the unmerged data, stored in the line object
    if not hasattr(line, 'unmerged_xs'):
      line.unmerged_xs = {}
      line.unmerged_ys = {}
      line.style = style
    
    if xs is not None:  # add it
      line.unmerged_xs[merge_info] = xs
    else:  # deleting this entry
      del line.unmerged_xs[merge_info]
      if len(line.unmerged_xs) == 0:  # nothing left
        return [None] * 4

    if ys is not None:
      line.unmerged_ys[merge_info] = ys
    else:
      del line.unmerged_ys[merge_info]
      if len(line.unmerged_xs) == 0:
        return [None] * 4

    # convert all data to numpy arrays, shape = (max number of points, number of repeats)
    # zip_longest is needed to fill in missing values with NaN, for incomplete lines.
    all_xs = np.array(list(zip_longest(*list(line.unmerged_xs.values()), fillvalue=np.nan)))
    all_ys = np.array(list(zip_longest(*list(line.unmerged_ys.values()), fillvalue=np.nan)))

    # compute statistics
    xs = np.nanmean(all_xs, axis=1, keepdims=False)
    ys = np.nanmean(all_ys, axis=1, keepdims=False)
    std = np.nanstd(all_ys, axis=1, keepdims=False)
    (shade_y1, shade_y2) = (ys - 2 * std, ys + 2 * std)

    return (xs, ys, shade_y1, shade_y2)

  def remove(self, exp):
    """Removes all plots associated with an experiment (inverse of Plots.add)"""
    if len(exp.names) == 0:  # no data yet
      return
    plots = self.define_plots(exp)
    for plot in plots:
      # find panel
      if plot['panel'] in self.panels:
        panel = self.panels[plot['panel']]

        # find plot line
        line_id = plot['line_id']
        if line_id in panel.plots_dict:
          line = panel.plots_dict[line_id]

          if plot['merge_info'] is not None:
            # remove this data from the merged line, and update it
            (xs, ys, shade_y1, shade_y2) = self.update_merged_stats(line, None, None, None, plot['merge_info'])
            if xs is not None:
              (limit1, limit2, shade) = panel.aux_plots_dict[plot['line_id']]
              limit1.setData(x=xs, y=shade_y1)
              limit2.setData(x=xs, y=shade_y2)
            else:
              # removed final line, nothing left
              plot['merge_info'] = None
              
              # remove auxiliary plots (e.g. shaded merged plots)
              if line_id in panel.aux_plots_dict:
                plot_item = panel.plot_widget.getPlotItem()
                for aux_object in panel.aux_plots_dict[line_id]:
                  plot_item.removeItem(aux_object)
                del panel.aux_plots_dict[line_id]
          
          if plot['merge_info'] is None:
            # simple line, remove it
            plot_item = panel.plot_widget.getPlotItem()
            plot_item.removeItem(line)
            del panel.plots_dict[line_id]

        # if the last line was deleted, delete the panel too
        if len(panel.plots_dict) == 0:
          panel.setParent(None)
          panel.deleteLater()
          del self.panels[plot['panel']]

  def remove_all(self):
    """Remove all plots, fast"""
    for panel in self.panels.values():
      panel.setParent(None)
      panel.deleteLater()
    self.panels.clear()


  def on_mouse_move(self, event, panel):
    """Select curves when hovering them, and update mouse cursor text"""
    viewbox = panel.plot_widget.getPlotItem().vb
    point = viewbox.mapSceneToView(event.pos())
    
    hovered = None
    hovered_id = (None, None, None)
    for (line_id, line) in panel.plots_dict.items():
      # only the first one gets selected
      inside = (not hovered and (line.curve.mouseShape().contains(point) or line.scatter.pointsAt(point)))

      if inside:
        hovered = line
        hovered_id = line_id
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

    # show cursor
    panel.cursor_vline.setVisible(True)
    x = point.x()

    if hovered:
      # snap vertical line to nearest point (by x coordinate)
      data = hovered.getData()
      index = np.argmin(np.abs(data[0] - x))
      (x, y) = (data[0][index], data[1][index])

      # snap dot to nearest point too
      panel.cursor_dot.setVisible(True)
      panel.cursor_dot.setData([x], [y])

      # print floats with 3 significant digits and no sci notation
      # (e.g. 1e-4). also consider integers.
      if x % 1 == 0: x = str(int(x))
      else: x = float('%.3g' % x)
      if y % 1 == 0: y = str(int(y))
      else: y = float('%.3g' % y)
      
      # show data coordinates and line info
      (x_name, y_name, exp_name) = hovered_id[:3]
      text = f"{exp_name}<br/>({x_name}={x}, {y_name}={y})"

    else:
      panel.cursor_dot.setVisible(False)
      text = ""

    # set positions and text
    panel.cursor_label.setText(text)  #, size='10pt'
    panel.cursor_vline.setValue(x)

    self.hovered_line_id = hovered_id

    pg.PlotWidget.mouseMoveEvent(panel.plot_widget, event)

  def on_mouse_leave(self, event, panel):
    """Hide cursor when the mouse leaves"""
    panel.cursor_vline.setVisible(False)
    panel.cursor_dot.setVisible(False)

  def on_mouse_click(self, event, panel):
    """Select experiment associated with the currently hovered line (by name)"""
    self.window.select_experiment(self.hovered_line_id[2])
    event.accept()
    pg.PlotWidget.mousePressEvent(panel.plot_widget, event)



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
