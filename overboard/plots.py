
import PyQt5.QtCore as QtCore

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from functools import partial
import heapq, logging
from datetime import datetime
from numbers import Number
from itertools import zip_longest
from random import random
import numpy as np

import pyqtgraph as pg

from .plotwidget import create_plot_widget
from .pg_time_axis import timestamp, DateAxisItem

# define lists of styles to cycle
palette = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]
dashes = [QtCore.Qt.SolidLine, QtCore.Qt.DashLine, QtCore.Qt.DotLine, QtCore.Qt.DashDotLine, QtCore.Qt.DashDotDotLine]
#dashes_by_name = dict(zip(['-', '--', ':', '-.', '-..'], dashes))
widths = [2, 1, 3]  # line widths

logger = logging.getLogger('overboard.plt')


class Plots():
  def __init__(self, window, dashes, log_level):
    # set logging messages threshold level
    logger.setLevel(getattr(logging, log_level.upper(), None))

    self.window = window
    window.plots = self  # back-reference
    self.dashes = dashes  # option to cycle through dashes first instead of colors

    self.panels = {}  # widgets containing plots, indexed by name (usually the plot title at the top)
    self.hovered_plot_info = None

    # reuse styles from hidden experiments if possible (early styles are
    # more distinguishable). note we only store style indexes, to allow
    # easy changing later (e.g. style by dashes only or colors).
    self.unused_styles = []  # keep unused styles in a heap so early styles have priority
    self.next_style_index = 0  # next unused style that is not in the heap

    # create timer to restore auto-range of plot axis progressively
    # (auto-range is disabled when plotting for performance)
    self.autorange_panels = {}
    self.autorange_timer = QtCore.QTimer()
    self.autorange_timer.timeout.connect(self.restore_autorange)
    self.autorange_timer.start(500)
    
    # set general PyQtGraph options
    pg.setConfigOptions(antialias=True, background='w', foreground='k')  # black on white

  def assign_exp_style(self, exp):
    """Assign a new style to an experiment"""
    # reuse a previous style if possible, in order
    if len(self.unused_styles) > 0:
      exp.style_idx = heapq.heappop(self.unused_styles)
    else:
      # otherwise, get a new one
      exp.style_idx = self.next_style_index
      self.next_style_index += 1

  def drop_exp_style(self, exp):
    """Remove the style of an experiment, and consider that style available for others"""
    if exp.style_idx is not None:
      heapq.heappush(self.unused_styles, exp.style_idx)
      exp.style_idx = None
  
  def drop_all_exp_styles(self):
    """Quickly reset the styles of all experiments"""
    self.unused_styles.clear()
    self.next_style_index = 0
    for exp in self.window.experiments.exps.values():
      exp.style_idx = None

  def get_exp_style(self, exp, assign=True):
    """Return a dict with the unique style of an experiment, assigning one if necessary"""
    if exp.style_idx is None:
      if not assign: return None  # asked to not assign a style
      self.assign_exp_style(exp)
    idx = exp.style_idx

    # start by varying color, then dashes, then line width
    if not self.dashes:
      color = palette[idx % len(palette)]
      dash = dashes[(idx // len(palette)) % len(dashes)]
      width = widths[(idx // (len(palette) * len(dashes))) % len(widths)]
    else:
      # alternative order: dashes, width, color
      dash = dashes[idx % len(dashes)]
      width = widths[(idx // len(dashes)) % len(widths)]
      color = palette[(idx // (len(dashes) * len(widths))) % len(palette)]

    return {'color': color, 'style': dash, 'width': width}

  def define_plots(self, exp):
    """Defines plot information for a given experiment. Returns a list of dicts,
    each dict defining the properties of a single line (sources for x, y, color,
    panel, etc). This accesses the window widgets to check the current options."""

    x_option = self.window.x_dropdown.currentText()
    y_option = self.window.y_dropdown.currentText()
    panel_option = self.window.panel_dropdown.currentText()
    merge_option = self.window.merge_dropdown.currentText()
    metrics_subset = set(self.window.metrics_subset_dropdown.get_checked_list())

    # some combinations are invalid, change to sensible defaults in those cases
    if panel_option == "One per metric":
      # Panel metric is unused, so all panels would look the same
      if x_option != "Panel metric" and y_option != "Panel metric":
        y_option = "Panel metric"
        self.window.y_dropdown.setCurrentText(y_option)
    
    else:
      # x/y_option "Panel metric" is only compatible with panel_option "One per metric"
      if x_option == "Panel metric":
        x_option = "iteration"
        self.window.x_dropdown.setCurrentText(x_option)
      if y_option == "Panel metric":
        y_option = "time"
        self.window.y_dropdown.setCurrentText(y_option)

    # don't let X and Y axis be set to the same value
    if x_option == y_option:
      if x_option != "iteration":
        x_option = "iteration"
      else:
        x_option = "time (relative)"
      self.window.x_dropdown.setCurrentText(x_option)

    # create list of panels by: metric, experiment, hyper-parameter type,
    # value of a single hyper-parameter, or create a single panel
    if panel_option == "One per metric": panels = exp.metrics[:]  # explicit copy
    elif panel_option == "One per run": panels = [exp.name]
    elif panel_option == "Single panel": panels = [y_option]
    else:  # single hyper-parameter selected, create different panels based on value
      panels = [panel_option + ' = ' + str(exp.meta.get(panel_option, None))]  # None if missing

    # possibly merge lines by some hyper-parameter; otherwise, each experiment is unique
    if merge_option == "Nothing" or merge_option not in exp.meta:
      (merge_info, line_id) = (None, exp.name)
    else:
      (merge_info, line_id) = (exp.name, str(exp.meta[merge_option]))

    info = []  # the list of lines to plot
    for panel in panels:  # possibly spread plots across panels
      lines = [(x_option, y_option)]  # single line per panel, with these X and Y sources
      if x_option == "All metrics":  # several lines in a panel - one per metric
        lines = [(name, y_option) for name in exp.metrics]
      elif y_option == "All metrics":
        lines = [(x_option, name) for name in exp.metrics]

      for (x, y) in lines:  # possibly create multiple lines for this panel
        if x_option == "Panel metric": x = panel  # different metrics per panel
        if y_option == "Panel metric": y = panel

        # special option: time aligned to the same origin
        if x == 'time (relative)': (x, x_relative) = ('time', True)
        else: x_relative = False
        if y == 'time (relative)': (y, y_relative) = ('time', True)
        else: y_relative = False

        # skip if not part of the subset
        if x not in metrics_subset or y not in metrics_subset: continue

        # a plot with the same values on X and Y is redundant, so skip it
        if x == y: continue

        # skip (arguably) useless plots: time vs iteration
        if x in ('time', 'iteration') and y in ('time', 'iteration'):
          continue

        # skip if this experiment does not have the required data
        if x not in exp.meta and x not in exp.metrics: continue
        if y not in exp.meta and y not in exp.metrics: continue

        # final touches and compose dict
        info.append(dict(panel=panel, x=x, y=y, line_id=(x, y, line_id),
          exp_name=exp.name, merge_info=merge_info,
          x_relative=x_relative, y_relative=y_relative))
    return info

  def add(self, exp):
    """Creates or updates plots associated with given experiment, creating panels if needed.
    If the experiment is marked as invisible/filtered, nothing will be drawn."""

    if not exp.is_visible() or len(exp.metrics) == 0:
      return False  # plots are invisible or no data loaded yet

    plots = self.define_plots(exp)
    for plot in plots:
      # create new panel if it doesn't exist
      if plot['panel'] not in self.panels:
        self.add_plot_panel(plot)

      panel = self.panels[plot['panel']]  # reuse existing panel
      self.pause_autorange(panel)
      plot_item = panel.plot_widget.getPlotItem()
      
      # get data points, pre-processed to ensure they are numeric. this may edit the axes.
      (xs, ys, x_is_categ, y_is_categ) = self.get_numeric_data_points(exp, plot, plot_item)

      # check if plot line already exists
      if plot['line_id'] not in panel.plots_dict:
        # create new line
        line = plot_item.plot([], [])
        line.curve.setClickable(True, 8)  # size of hover region
        panel.plots_dict[plot['line_id']] = line
      else:
        # update existing one
        line = panel.plots_dict[plot['line_id']]
      line.plot_info = plot  # store the plot information for later, e.g. on mouse-over
      line.mouse_over = False

      has_new_style = (exp.style_idx is None)  # remember if a new style is assigned

      if plot['merge_info'] is not None:
        # handle merged plots, by updating the statistics to display first
        (xs, ys, shade_y1, shade_y2) = self.update_merged_stats(line, plot['merge_info'], xs, ys)

        # share the same style among a group of merged experiments
        if exp.style_idx is None:
          if not hasattr(line, 'style_idx'):
            self.assign_exp_style(exp)  # new style
            line.style_idx = exp.style_idx
          else:  # use the same style as the previous merged experiments
            exp.style_idx = line.style_idx

      # get the experiment's style (color, dashes, etc)
      style = self.get_exp_style(exp)

      if has_new_style:  # update the icon if the style was missing before
        self.window.redraw_icon(exp)
      
      if exp.is_selected:  # selected lines are thicker
        style['width'] = style.get('width', 2) + 2
      
      # create pen with the experiment's style, and args to assign to PlotDataItem line
      pen = pg.mkPen(style)
      data = dict(x=xs, y=ys, pen=pen)

      # for single points, plot a marker/symbol, since the line won't show up
      if len(xs) == 1:
        data['symbol'] = 'o'
        data['symbolBrush'] = pen.color()
        data['symbolSize'] = pen.width() * 2 + 4
        
        # for categorical axis, jitter single points. unfortunately, points will
        # jump around when selecting/deselecting plots, so we need to keep the
        # amount of jitter in a state variable per line.
        if x_is_categ:
          if not hasattr(line, 'jitter_x'): line.jitter_x = random() * 0.2 - 0.1
          xs[0] += line.jitter_x
        if y_is_categ:
          if not hasattr(line, 'jitter_y'): line.jitter_y = random() * 0.2 - 0.1
          ys[0] += line.jitter_y
      else:
        data['symbol'] = None

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
    title = plot['panel']
    plot_widget = create_plot_widget()
    panel = self.window.add_panel(plot_widget, title)

    logger.info(f"Adding plot panel {title}")

    plot_item = panel.plot_widget.getPlotItem()
    plot_item.setLabel('bottom', plot['x'])  # set X axis label

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
    (x_is_categ, y_is_categ) = (False, False)  # whether an axis is categorical

    if plot['x'] in exp.meta:
      xs = [exp.meta[plot['x']]]  # a single point, with the chosen hyper-parameter
    else:
      if plot['x'] not in exp.metrics:  # final sanity check
        logging.warning("The chosen metric was not found in this experiment.")
        xs = []
      else:
        xs = exp.data[exp.metrics.index(plot['x'])]  # several points, with the chosen metric

    if plot['y'] in exp.meta:
      ys = [exp.meta[plot['y']]]
    else:
      if plot['y'] not in exp.metrics:  # final sanity check
        logging.warning("The chosen metric was not found in this experiment.")
        ys = []
      else:
        ys = exp.data[exp.metrics.index(plot['y'])]

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


    # check data points' types to know what axes to create (numeric, time or categorical).
    # handle datetimes. create time axes if needed, and convert datetimes to numeric values
    if len(xs) > 0 and all(isinstance(x, datetime) for x in xs):
      if not isinstance(plot_item.axes['bottom']['item'], DateAxisItem):
        axis = DateAxisItem(orientation='bottom')
        axis.attachToPlotItem(plot_item)
        axis.setGrid(255)

      # plot values relative to the same origin (i.e. remove minimum)
      if plot['x_relative']:
        earliest = min(xs)
        origin = datetime(year=2000, month=1, day=1)
        xs = [x - earliest + origin for x in xs]

      xs = [timestamp(x) for x in xs]

    # handle categorical values
    elif len(xs) > 0 and (self.window.x_categorical_checkbox.isChecked() or
     any(not isinstance(x, Number) or isinstance(x, bool) for x in xs)):
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

      # convert to numeric value, by look-up
      xs = [ticks_dict[x] for x in xs]
      x_is_categ = True


    # same as above, for Y axis.
    # handle datetimes. create time axes if needed, and convert datetimes to numeric values
    if len(ys) > 0 and all(isinstance(y, datetime) for y in ys):
      if not isinstance(plot_item.axes['left']['item'], DateAxisItem):
        axis = DateAxisItem(orientation='left', backgroundColor=None)
        axis.attachToPlotItem(plot_item)
        axis.setGrid(1)

      # plot values relative to the same origin (i.e. remove minimum)
      if plot['y_relative']:
        earliest = min(ys)
        origin = datetime(year=2000, month=1, day=1)
        ys = [y - earliest + origin for y in ys]

      ys = [timestamp(y) for y in ys]

    # handle categorical values
    elif len(ys) > 0 and (self.window.y_categorical_checkbox.isChecked() or
     any(not isinstance(y, Number) or isinstance(y, bool) for y in ys)):

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
          
      # convert to numeric value, by look-up
      ys = [ticks_dict[y] for y in ys]
      x_is_categ = True
    
    return (xs, ys, x_is_categ, y_is_categ)

  def update_merged_stats(self, line, merge_info, xs=None, ys=None):
    # update the unmerged data, stored in the line object
    if not hasattr(line, 'unmerged_xs'):
      line.unmerged_xs = {}
      line.unmerged_ys = {}
    
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
    merged_line = self.window.merge_line_dropdown.currentText()
    merged_shade = self.window.merge_shade_dropdown.currentText()

    if merged_line == 'Median':
      xs = np.nanmedian(all_xs, axis=1, keepdims=False)
      ys = np.nanmedian(all_ys, axis=1, keepdims=False)
    else:  # mean
      xs = np.nanmean(all_xs, axis=1, keepdims=False)
      ys = np.nanmean(all_ys, axis=1, keepdims=False)

    if merged_shade == 'Maximum and minimum':
      shade_y1 = np.nanmin(all_ys, axis=1, keepdims=False)
      shade_y2 = np.nanmax(all_ys, axis=1, keepdims=False)
    else:
      # '2 x standard deviations', extract the integer factor in the first character and use it
      factor = int(merged_shade[0])
      std = factor * np.nanstd(all_ys, axis=1, keepdims=False)
      (shade_y1, shade_y2) = (ys - std, ys + std)

    return (xs, ys, shade_y1, shade_y2)

  def remove(self, exp):
    """Removes all plots associated with an experiment (inverse of Plots.add)"""
    if len(exp.metrics) == 0:  # no data yet
      return

    plots = self.define_plots(exp)
    for plot in plots:
      # find panel
      if plot['panel'] in self.panels:
        panel = self.panels[plot['panel']]
        self.pause_autorange(panel)

        # find plot line
        line_id = plot['line_id']
        if line_id in panel.plots_dict:
          line = panel.plots_dict[line_id]

          if plot['merge_info'] is not None:
            # remove this data from the merged line, and update it
            (xs, ys, shade_y1, shade_y2) = self.update_merged_stats(line, plot['merge_info'])
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
    self.window.flow_layout.clear()
    self.panels.clear()


  def on_mouse_move(self, event, panel):
    """Select curves when hovering them, and update mouse cursor text"""
    # access PlotItem's ViewBox to map mouse to data coordinates
    plot_item = panel.plot_widget.getPlotItem()
    point = plot_item.vb.mapSceneToView(event.pos())
    
    hovered = None
    for line in panel.plots_dict.values():
      # only the first one gets selected
      inside = (not hovered and (line.curve.mouseShape().contains(point) or line.scatter.pointsAt(point)))

      if inside:
        hovered = line
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
      vline_x = x

      # show X value as string for categorical axes
      axes = plot_item.axes['bottom']['item']
      if hasattr(axes, 'ticks_dict'):  # X axis is categorical
        index = round(x)  # round due to possible jittering
        # awkward indexing into axes.ticks_dict by value (index/x value) instead of key (text label)
        labels = [label for (label, idx) in axes.ticks_dict.items() if idx == index]
        if len(labels) > 0: x = labels[0]
      else:
        # numeric value. print floats with 3 significant digits and no
        # sci notation (e.g. 1e-4). also consider integers.
        if x % 1 == 0: x = str(int(x))
        else: x = float('%.3g' % x)

      # show Y value as string for categorical axes
      axes = plot_item.axes['left']['item']
      if hasattr(axes, 'ticks_dict'):  # X axis is categorical
        index = round(y)  # round due to possible jittering
        # awkward indexing into axes.ticks_dict by value (index/x value) instead of key (text label)
        labels = [label for (label, idx) in axes.ticks_dict.items() if idx == index]
        if len(labels) > 0: y = labels[0]
      else:
        # numeric value, same as above
        if y % 1 == 0: y = str(int(y))
        else: y = float('%.3g' % y)
      
      # show data coordinates and line information, and store it
      # for on_mouse_click to access later
      info = self.hovered_plot_info = hovered.plot_info
      text = f"{info['exp_name']}<br/>({info['x']}={x}, {info['y']}={y})"

    else:
      panel.cursor_dot.setVisible(False)
      text = ""
      vline_x = x
      self.hovered_plot_info = None

    # set positions and text
    panel.cursor_label.setText(text)  #, size='10pt'
    panel.cursor_vline.setValue(vline_x)

    pg.PlotWidget.mouseMoveEvent(panel.plot_widget, event)

  def on_mouse_leave(self, event, panel):
    """Hide cursor when the mouse leaves"""
    panel.cursor_vline.setVisible(False)
    panel.cursor_dot.setVisible(False)

  def on_mouse_click(self, event, panel):
    """Select experiment associated with the currently hovered line (by name)"""
    if self.hovered_plot_info is not None:
      self.window.select_experiment(self.hovered_plot_info['exp_name'])
      event.accept()
    pg.PlotWidget.mousePressEvent(panel.plot_widget, event)

  def pause_autorange(self, panel):
    """Pause auto-range temporarily when plotting, for performance (restored by a timer)"""
    if panel not in self.autorange_panels:  # if already paused do nothing
      view = panel.plot_widget.getPlotItem().getViewBox()
      state = view.autoRangeEnabled()
      if any(state):  # list with 2 booleans, True if each axis has auto-range enabled
        view.disableAutoRange()
        self.autorange_panels[panel] = state

  def restore_autorange(self):
    """Restore auto-range of plot axis progressively, called by a timer"""
    if len(self.autorange_panels) > 0:
      # pop oldest panel off the stack (this is still an ordered dict to check membership)
      (panel, state) = next(iter(self.autorange_panels.items()))
      del self.autorange_panels[panel]

      view = panel.plot_widget.getPlotItem().getViewBox()
      try:
        view.enableAutoRange(x=state[0], y=state[1])
      except RuntimeError:  # sometimes the object was deleted in the meanwhile
        pass


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
