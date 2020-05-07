#os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "TRUE"

import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
from PyQt5.QtCore import Qt

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

import os, json
from time import time
from datetime import datetime, timezone
from functools import partial

import pyqtgraph as pg

from .flowlayout import FlowLayout
from .fastslider import Slider
#from .plots import Smoother


filter_tooltip_text = """Write a Python expression and then press Enter to filter.

Example: regularization >= 0.1 and batch_norm == True

Runs (displayed as table rows) for which the expression evaluates to False will be hidden.
Any hyper-parameters (displayed as table column headers) can be used in this expression.
Hyper-parameters are saved automatically by passing them to the Logger instance that records a run's results (see Logger documentation)."""


# constants referring to different data types stored in table cells.
# e.g.: item.data(table_data_exp), with item a QTableWidgetItem
table_data_exp = Qt.UserRole  # experiment name, identifies table row
table_data_column = Qt.UserRole + 1  # column name
table_data_order = Qt.UserRole + 2  # sorting order (for custom sorting, used for datetimes)


class Window(QtWidgets.QMainWindow):
  def __init__(self, args):
    super(Window, self).__init__(parent=None)
    
    self.experiments = None  # object that manages experiments
    self.plots = None  # object that manages plots
    self.visualizations = None  # object that manages custom visualizations
    self.last_process_events = time()  # to update during heavy loads
    self.rebuilding_plots = False  # used by rebuild_plots

    # persistent settings
    self.settings = QtCore.QSettings('OverBoard', 'OverBoard')

    # get screen size
    screen_size = QtWidgets.QDesktopWidget().availableGeometry(self).size()

    # create the parent of both sidebar and plot area
    main = QtWidgets.QSplitter(self)

    # create sidebar
    sidebar = QtWidgets.QGridLayout()
    sidebar.setAlignment(Qt.AlignTop)
    widget = QtWidgets.QWidget(main)  # need dummy widget to wrap box layout
    widget.setLayout(sidebar)

    # panel size slider
    panel_size = float(self.settings.value('panel_size', screen_size.width() * 0.2))
    sidebar.addWidget(QtWidgets.QLabel('Panel size'), 0, 0)
    slider = Slider(Qt.Horizontal)  # replaces QtWidgets.QSlider(Qt.Horizontal)
    slider.setMinimum(screen_size.width() * 0.05)
    slider.setMaximum(screen_size.width() * 0.8)
    slider.setTickInterval(screen_size.width() * 0.005)
    slider.setValue(panel_size)  # initial value
    slider.valueChanged.connect(self.on_size_slider_changed)
    sidebar.addWidget(slider, 0, 1)
    self.size_slider = slider
    
    # dropdown lists for plot configuration
    self.x_dropdown = self.create_dropdown(sidebar, label='X axis', default='iteration',
      options=['Panel metric', 'All metrics', 'iteration', 'time', 'time (relative)'], setting_name='x_dropdown')

    self.x_categorical_checkbox = self.create_checkbox(sidebar,
      label='Treat X as categorical', default=False, setting_name='x_categorical_checkbox')

    self.y_dropdown = self.create_dropdown(sidebar, label='Y axis', default='Panel metric',
      options=['Panel metric', 'All metrics', 'iteration', 'time', 'time (relative)'], setting_name='y_dropdown')

    self.y_categorical_checkbox = self.create_checkbox(sidebar,
      label='Treat Y as categorical', default=False, setting_name='y_categorical_checkbox')

    self.panel_dropdown = self.create_dropdown(sidebar, label='Panels', default='One per metric',
      options=['Single panel', 'One per metric', 'One per run'], setting_name='panel_dropdown')

    self.scalar_dropdown = self.create_dropdown(sidebar, label='Scalar display', default='Last value',
      options=['Last value', 'Maximum', 'Minimum'], setting_name='scalar_dropdown')

    self.merge_dropdown = self.create_dropdown(sidebar, label='Merge', default='Nothing',
      options=['Nothing'], setting_name='merge_dropdown', reset_style=True)

    self.merge_line_dropdown = self.create_dropdown(sidebar, label='Merged line', default='Mean',
      options=['Mean', 'Median'], setting_name='merge_line_dropdown')

    self.merge_shade_dropdown = self.create_dropdown(sidebar, label='Merged shade', default='2 x standard deviations',
      options=['1 x standard deviation', '2 x standard deviations', '3 x standard deviations',
      'Maximum and minimum'], setting_name='merge_shade_dropdown')

    # experiments filter text box
    rows = sidebar.rowCount()
    sidebar.addWidget(QtWidgets.QLabel('Filter'), rows, 0)
    edit = QtWidgets.QLineEdit(self.settings.value('filter_edit', ''))
    edit.setPlaceholderText('Hover for help')
    edit.returnPressed.connect(self.on_filter_ready)
    edit.setToolTipDuration(60000)  # 1 minute
    edit.setToolTip(filter_tooltip_text)
    edit.focusInEvent = self.on_filter_focus
    sidebar.addWidget(edit, rows, 1)
    self.filter_edit = edit
    self.compiled_filter = None  # compiled code of filter

    # filter auto-complete
    history = self.settings.value('filter_completer', None)
    if history is None: history = []  # QSettings doesn't like this empty list as default value
    completer = QtWidgets.QCompleter(history)
    edit.setCompleter(completer)

    """# smoothness slider
    sidebar.addWidget(QtWidgets.QLabel('Smoothness'))
    slider = Slider(Qt.Horizontal)  #QtWidgets.QSlider(Qt.Horizontal)
    slider.setMinimum(0)
    slider.setMaximum(10 * 4)  # smooth_slider_changed always divides by 4 (since sliders only support ints)
    slider.setTickInterval(1)
    slider.setValue(args.smoothen)  # initial value
    slider.valueChanged.connect(self.smooth_slider_changed)
    sidebar.addWidget(slider)
    self.smooth_slider = slider
    self.smoother = Smoother(args.smoothen)"""

    # experiments list in sidebar, as a table
    table = QtWidgets.QTableWidget(0, 4)  # start with zero rows
    table.setHorizontalHeaderLabels(['', 'run', 'timestamp', 'notes'])  # initial column headers

    self.table_col_by_name = {'timestamp': 2, 'notes': 3}  # maps column names (hyper-parameters) to column indices
    table.sortItems(2, Qt.DescendingOrder)  # sort by timestamp column

    # table style
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)

    table.setSelectionBehavior(QtWidgets.QTableView.SelectRows)  # allow selecting rows
    table.setSelectionMode(QtWidgets.QTableView.SingleSelection)
    table.setAutoScroll(False)  # don't scroll when user clicks table cells

    table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)  # start editing cell with first click
    table.itemChanged.connect(self.on_table_edit)
    self.table_edit_enabled = True

    table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)  # smooth scrolling
    table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
    
    table.verticalHeader().hide()  # hide vertical header
    
    header = table.horizontalHeader()  # configure horizontal header
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignLeft)
    header.setSectionsMovable(True)
    header.setTextElideMode(Qt.ElideRight)  # show ellipsis for cut-off headers
    header.setHighlightSections(False)  # no bold header when cells are clicked

    table.itemSelectionChanged.connect(self.on_table_select)
    table.mousePressEvent = self.on_table_click
    table.contextMenuEvent = self.on_table_context_menu

    self.table = table
    self.selected_exp = (None, None)
    sidebar.addWidget(table, sidebar.rowCount(), 0, 1, 2)
    
    # create the scroll area with plots
    (plot_scroll_widget, self.scroll_area) = create_scroller()
    main.addWidget(self.scroll_area)

    # override wheel event to prevent a bug
    self.scroll_area.wheelEvent = self.scroll_wheel_event

    # finish the parent: let sidebar width remain fixed when resizing the window, while
    # the plot area can vary; and set initial sidebar size.
    main.setStretchFactor(0, 0)
    main.setStretchFactor(1, 1)
    sidebar_size = screen_size.width() * 0.15
    main.setSizes([sidebar_size, 1])

    # main layout for plots
    self.flow_layout = FlowLayout(plot_scroll_widget)
    
    self.setCentralWidget(main)

    # window size and title
    self.resize(screen_size.width() * 0.6, screen_size.height() * 0.95)
    self.setWindowTitle('OverBoard - ' + args.folder)

    self.clipboard = QtGui.QApplication.clipboard()

    # load list of previously-hidden experiments. this is looked up when an experiment loads.
    self.hidden_exp_paths = self.settings.value('hidden_exp_paths', None)
    if self.hidden_exp_paths is None:
      self.hidden_exp_paths = []
    self.hidden_exp_paths = set(self.hidden_exp_paths)

    # compile loaded filter
    self.on_filter_ready()

  def process_events_if_needed(self):
    """Process events if enough time has passed, to keep the GUI
    responsive during potentially heavy operations in the main thread"""
    if time() - self.last_process_events > 0.5:  # limit to once every 0.5 seconds      
      QtWidgets.QApplication.processEvents()
      self.last_process_events = time()

  def add_panel(self, widget, title, add_to_layout=True, reuse=False):
    # adds a panel to the FlowLayout (main plots display), containing a widget (e.g. FigureCanvas).
    # first, create a QGroupBox around it, to show the title
    if not reuse:
      vbox = QtWidgets.QVBoxLayout()
      vbox.addWidget(widget)
      panel = QtWidgets.QGroupBox(title)
      panel.setLayout(vbox)
      panel.plot_widget = widget  # keep a reference to the inner widget
    else:
      panel = widget  # reusing a previous panel (less common)
      panel.setTitle(title)
    
    # set the size
    panel_size = self.size_slider.value()
    panel.setFixedWidth(panel_size)
    panel.setFixedHeight(panel_size)

    if add_to_layout and not reuse:  # add to window's flow layout
      self.flow_layout.addWidget(panel)

    return panel
  
  def create_dropdown(self, sidebar, label, options, setting_name, default, reset_style=False):
    """Create a new dropdown menu, associated with a persistent setting"""
    rows = sidebar.rowCount()
    sidebar.addWidget(QtWidgets.QLabel(label), rows, 0)
    dropdown = QtWidgets.QComboBox()
    for option in options:
      dropdown.addItem(option)
    dropdown.setCurrentText(self.settings.value(setting_name, default, type=str))
    dropdown.activated.connect(partial(self.rebuild_plots, reset_style=reset_style))
    sidebar.addWidget(dropdown, rows, 1)
    return dropdown

  def create_checkbox(self, sidebar, label, setting_name, default):
    """Create a new checkbox, associated with a persistent setting"""
    rows = sidebar.rowCount()
    checkbox = QtWidgets.QCheckBox(label)
    checkbox.setChecked(self.settings.value(setting_name, default, type=bool))
    checkbox.toggled.connect(self.rebuild_plots)
    sidebar.addWidget(checkbox, rows, 0, 1, 2)
    return checkbox


  def on_exp_init(self, exp):
    """Called by Experiment when it is initialized"""
    # add experiment to table
    table = self.table

    # disable sorting to prevent bug when adding items, to restore afterwards
    header = table.horizontalHeader()
    prev_sort = (header.sortIndicatorSection(), header.sortIndicatorOrder())
    table.setSortingEnabled(False)

    # new row
    row = table.rowCount()
    table.insertRow(row)

    # persistent mapping between an experiment and its row (even as they're sorted)
    exp.table_row = QtCore.QPersistentModelIndex(table.model().index(row, 0))

    # create icon (empty label with writable pixmap)
    size = table.rowHeight(row)
    pixmap = QtGui.QPixmap(size, size)  # make it square
    icon = QtGui.QLabel()
    icon.setPixmap(pixmap)
    icon.setFixedWidth(size)
    icon.mousePressEvent = lambda _: self.on_icon_click(icon, exp)

    table.setCellWidget(row, 0, icon)
    self.redraw_icon(exp, icon)

    # show experiment name
    self.set_table_cell(row, 1, exp.name, exp, 'run')

    # restore sorting, and sort state (which column and direction)
    table.setSortingEnabled(True)
    table.sortItems(*prev_sort)

    self.process_events_if_needed()

  def redraw_icon(self, exp, icon=None, style=None):
    """Update an icon in the table by redrawing its pixmap with an experiment's style.
    Both the icon widget and the style are optional (for optimization only)."""
    if icon is None:  # allow omitting the icon widget for convenience
      icon = self.table.cellWidget(exp.table_row.row(), 0)

    pixmap = icon.pixmap()
    pixmap.fill()  # white background by default

    (x, y, w, h) = pixmap.rect().getRect()
    painter = QtGui.QPainter(pixmap)
    painter.fillRect(x, y, w, h, QtGui.QColor('white'))

    # draw box around icon
    pen = QtGui.QPen()
    pen.setWidth(2)
    if exp.is_selected:
      pen.setWidth(4)
    else:
      pen.setWidth(2)
    pen.setColor(QtGui.QColor("#EAEAF2"))
    painter.setPen(pen)

    painter.drawRoundedRect(x + 0.1 * w, y + 0.1 * h, 0.8 * w, 0.8 * h, 0.15 * w, 0.15 * h)

    # draw line, if the experiment is visible
    if exp.visible:
      if style is None:
        style = self.plots.get_exp_style(exp, assign=False)
      if style is not None:  # may not be assigned yet
        pen = pg.mkPen(style)
        if exp.is_selected:
          pen.setWidth(pen.width() + 2)
        painter.setPen(pen)
        painter.drawLine(x + 0.2 * w, y + 0.5 * h, x + 0.8 * w, y + 0.5 * h)

    painter.end()
    icon.repaint()  # important, to show changes on screen

  def on_exp_meta_ready(self, exp):
    """Called by Experiment when the meta-data has been read"""

    # print a row of meta-data (argument) values for this experiment in the table
    (table, table_col_by_name) = (self.table, self.table_col_by_name)
    row = exp.table_row.row()
    added_columns = False
    self.table_edit_enabled = False  # avoid on_table_edit when filling in an editable cell for the first time

    # disable sorting to prevent bug when adding items, to restore afterwards
    header = table.horizontalHeader()
    prev_sort = (header.sortIndicatorSection(), header.sortIndicatorOrder())
    table.setSortingEnabled(False)

    for arg_name in exp.meta.keys():
      if not arg_name.startswith('_'):
        if arg_name not in table_col_by_name:  # a new argument name, add a column
          col = table.columnCount()
          table.setColumnCount(col + 1)
          table.setHorizontalHeaderItem(col, QtWidgets.QTableWidgetItem(arg_name))  #, QtWidgets.QTableWidgetItem.Type
          table_col_by_name[arg_name] = col
          added_columns = True
        else:
          col = table_col_by_name[arg_name]
        
        cell_value = exp.meta.get(arg_name, '')
        
        self.set_table_cell(row, col, cell_value, exp, arg_name, editable=(arg_name == 'notes'))

    if 'notes' not in exp.meta:  # explicitly create editable notes cell, if not created already
      self.set_table_cell(row, table_col_by_name['notes'], '', exp, 'notes', editable=True)

    if added_columns:
      self.resize_table()

    # update dropdown lists to include all hyper-parameter names
    for arg_name in exp.meta.keys():
      for widget in [self.x_dropdown, self.y_dropdown, self.panel_dropdown, self.merge_dropdown]:
        if widget.findText(arg_name) < 0:
          widget.addItem(arg_name)
    
    # hide row if filter says so
    self.filter_experiment(exp)

    self.table_edit_enabled = True

    # restore sorting, and sort state (which column and direction)
    table.setSortingEnabled(True)
    table.sortItems(*prev_sort)

    self.process_events_if_needed()

  def on_exp_header_ready(self, exp):
    """Called by Experiment when the header data (metrics/column names) has been read"""
    # update dropdown lists to include all metric names
    for name in exp.metrics:
      if self.x_dropdown.findText(name) < 0:
        self.x_dropdown.addItem(name)
      if self.y_dropdown.findText(name) < 0:
        self.y_dropdown.addItem(name)

  def rebuild_plots(self, reset_style=False):
    """Rebuild all plots (e.g. when plot options such as x/y axis change)"""
    if not self.rebuilding_plots:  # cancel when already rebuilding the plots (i.e. called recursively)
      self.rebuilding_plots = True
      if reset_style:
        self.plots.drop_all_exp_styles()
      self.plots.remove_all()
      for exp in self.experiments.exps.values():
        visible = self.plots.add(exp)
        if visible:
          self.process_events_if_needed()  # keep it responsive
      self.rebuilding_plots = False

  def set_table_cell(self, row, col, value, exp, col_name, selectable=True, editable=False):
    """Set a single table cell in the sidebar"""
    # try to interpret as integer or float, to allow numeric sorting of columns. editable is only for strings.
    if not editable and not isinstance(value, (int, float, datetime)):
      value = str(value)  # handle e.g. dicts
      try:
        value = float(value)
        if int(value) == value:  # store as int if possible, prints better
          value = int(value)
      except ValueError: pass

    if isinstance(value, str):  # faster option for strings
      item = QtWidgets.QTableWidgetItem(value)

    elif isinstance(value, datetime):  # show nicer-looking timestamps, sorted correctly
      item = SortableTableItem(print_datetime(value), value.timestamp)

    else:  # sort as number if not a string
      item = QtWidgets.QTableWidgetItem()
      item.setData(Qt.EditRole, QtCore.QVariant(value))

    item.setData(table_data_exp, exp.name)  # pointer to original experiment (by name), i.e. row name
    item.setData(table_data_column, col_name)  # column name

    flags = Qt.ItemIsEnabled
    if selectable: flags |= Qt.ItemIsSelectable
    if editable: flags |= Qt.ItemIsEditable
    item.setFlags(flags)
    
    self.table.setItem(row, col, item)
    return item

  def resize_table(self):
    """Resize the column headers to fully contain the header text
    (note that Qt's resizeColumnsToContents ignores the headers)"""
    table = self.table
    table.resizeColumnsToContents()
    
    max_width = int(0.9 * table.parentWidget().width())  # don't let any column become wider than 90% of the sidebar
    header = table.horizontalHeader()
    metrics = QtGui.QFontMetrics(table.horizontalHeaderItem(0).font())
    for col in range(table.columnCount()):
      text = table.horizontalHeaderItem(col).text()
      text_width = metrics.boundingRect(text).width()
      header.resizeSection(col, min(max_width, max(table.sizeHintForColumn(col), text_width + 20)))  # needs some extra width

  def on_icon_click(self, icon, exp):
    """Toggle visibility of a given experiment, when the
    icon (first column of table) is clicked"""

    if exp.is_filtered: return  # shouldn't happen    
    if exp.visible:
      # remove all associated plots, and reset the experiment style so it can be used by others
      exp.visible = False
      self.plots.remove(exp)
      self.plots.drop_exp_style(exp)
    else:
      # create plots (a new style will be assigned if necessary)
      exp.visible = True
      self.plots.add(exp)

    # update icon
    self.redraw_icon(exp, icon)

  def on_table_select(self):
    """Select experiment on table row click"""
    exp = None
    selected = self.table.selectedItems()
    if len(selected) > 0:  # select new one
      exp = self.experiments.exps[selected[0].data(table_data_exp)]
    self.select_experiment(exp, clicked_table=True)

  def on_table_click(self, event):
    """Clear selection on click (before selecting a row), to allow de-selecting by clicking outside table items"""
    self.table.clearSelection()
    QtGui.QTableWidget.mousePressEvent(self.table, event)
  
  def on_table_context_menu(self, event):
    """Show menu when right-clicking a cell in the table"""
    # get the selected row and column
    row = self.table.rowAt(event.pos().y())
    col = self.table.columnAt(event.pos().x())

    action = QtGui.QAction('Copy', self)
    action.triggered.connect(lambda: self.copy_cell(row, col))
    
    self.menu = QtGui.QMenu(self)
    self.menu.addAction(action)
    self.menu.popup(QtGui.QCursor.pos())

  def copy_cell(self, row, col):
    """Copy a table cell to the clibpard (called via the context menu)"""
    cell = self.table.item(row, col)
    if cell:
      self.clipboard.setText(cell.text())

  def select_experiment(self, exp=None, clicked_table=False):
    """Select an experiment in the table, highlighting it in the plots.
    Passing None deselects previous one."""

    if isinstance(exp, str):  # experiment name, look it up
      exp = self.experiments.exps.get(exp, None)

    # unselect previous experiment first
    (old_exp, old_icon) = self.selected_exp
    if old_exp:
      old_exp.is_selected = False
      self.redraw_icon(old_exp, old_icon)
      self.plots.add(old_exp)  # update its view, in case it's visible

    if exp and exp.visible:  # don't select if invisible
      icon = self.table.cellWidget(exp.table_row.row(), 0)

      exp.is_selected = True
      self.plots.add(exp)
      self.selected_exp = (exp, icon)
      self.visualizations.select(exp)
      self.redraw_icon(exp, icon)

      if not clicked_table:  # update table selection
        self.table.selectRow(exp.table_row.row())
    else:
      self.selected_exp = (None, None)
      self.visualizations.select(None)
      if not clicked_table:  # update table selection
        self.table.clearSelection()

  def on_table_edit(self, item):
    """Finished editing a cell in the table"""
    if self.table_edit_enabled:
      if item.data(table_data_column) == 'notes':
        # update experiment meta-data with updated note, and update the JSON file
        exp = self.experiments.exps[item.data(table_data_exp)]

        if item.text() != exp.meta.get('notes', ''):  # user changed the text
          # write to another file and only then replace the original (in case of crashes/bad writes)
          exp.meta['notes'] = item.text()
          with open(exp.directory + '/meta.json.partial', 'w') as file:
            json.dump(exp.meta, file, sort_keys=True, indent=4, default=str)
          os.replace(exp.directory + '/meta.json.partial', exp.directory + '/meta.json')
          

  def on_filter_ready(self):
    """User pressed Enter in filter text box, filter the experiments"""
    if len(self.filter_edit.text().strip()) == 0:  # no filter
      self.compiled_filter = None
      self.filter_edit.setStyleSheet("color: black;")
    else:
      # compile filter code
      try:
        self.compiled_filter = compile(self.filter_edit.text(), '<filter>', 'eval')
        self.filter_edit.setStyleSheet("color: black;")
      except Exception as err:
        self.show_filter_error(err)
        return

    if self.experiments is not None:
      for exp in self.experiments.exps.values():
        err = self.filter_experiment(exp)
        if err: return
        self.process_events_if_needed()  # keep it responsive
      
      # add to auto-complete model, if there was no error
      text = self.filter_edit.text()
      model = self.filter_edit.completer().model()
      entries = model.stringList()
      if text and text not in entries:
        entries.insert(0, text)  # insert at top of list
        model.setStringList(entries)

  def filter_experiment(self, exp):
    """Apply filter to a single experiment, hiding it or showing it"""
    if self.compiled_filter is None:
      # no filter, show experiment unconditionally
      if exp.is_filtered:
        self.table.setRowHidden(exp.table_row.row(), False)
        exp.is_filtered = False
        self.plots.add(exp)
    else:
      # create a dict with the hyper-parameters from this experiment, and all
      # missing hyper-parameters set to None, to be accessed by the filter function.
      vars_table = dict(zip(self.table_col_by_name.keys(), [None] * len(self.table_col_by_name)))
      vars_table.update(exp.meta)

      # other special variables that will be available to the filter function
      vars_table['run'] = exp.name
      vars_table['datetime'] = datetime  # useful to manipulate timestamps
      vars_table['timezone'] = timezone

      # evaluate filter to obtain boolean
      try:
        hide = not eval(self.compiled_filter, vars_table, vars_table)
      except Exception as err:
        self.show_filter_error(err)
        return True

      # hide or show depending on context
      was_hidden = (exp.is_filtered or not exp.visible)
      exp.is_filtered = hide  # will be checked by Plots.add

      self.table.setRowHidden(exp.table_row.row(), hide)
      if hide:
        if not was_hidden:
          self.plots.remove(exp)
      else:
        self.plots.add(exp)
      return False

  def show_filter_error(self, err):
    """Show filter expression error as a tooltip, and change color to red"""
    text = err.__class__.__name__ + ": " + str(err)
    QtGui.QToolTip.showText(QtGui.QCursor.pos(), text, self.filter_edit)
    self.filter_edit.setStyleSheet("color: #B00000;")

  def on_filter_focus(self, event):
    """Event handler for when filter line-edit widget gets focus"""
    QtWidgets.QLineEdit.focusInEvent(self.filter_edit, event)
    self.filter_edit.completer().complete()

  def on_size_slider_changed(self):
    """Resize panels for plots and visualizations"""
    panel_size = self.size_slider.value()
    for panel in self.plots.panels.values():
      panel.setFixedWidth(panel_size)
      panel.setFixedHeight(panel_size)
    for panel_group in self.visualizations.panels.values():
      for panel in panel_group:
        panel.setFixedWidth(panel_size)
        panel.setFixedHeight(panel_size)
  
  #def smooth_slider_changed(self):
  #  self.smoother = Smoother(self.smooth_slider.value() / 4.0)

  def scroll_wheel_event(self, event):
    """Override QScrollArea wheelEvent, to prevent it from scrolling simultaneously with PyQtGraph's PlotItem"""
    for panel in self.plots.panels.values():
      if panel.plot_widget.underMouse():  # panel is under the mouse, so don't let QScrolArea scroll too
        event.ignore()
        return
    QtWidgets.QScrollArea.wheelEvent(self.scroll_area, event)
  
  def closeEvent(self, event):
    """Write state to settings before closing"""
    self.settings.setValue('panel_size', self.size_slider.value())
    self.settings.setValue('x_dropdown', self.x_dropdown.currentText())
    self.settings.setValue('x_categorical_checkbox', self.x_categorical_checkbox.isChecked())
    self.settings.setValue('y_dropdown', self.y_dropdown.currentText())
    self.settings.setValue('y_categorical_checkbox', self.y_categorical_checkbox.isChecked())
    self.settings.setValue('panel_dropdown', self.panel_dropdown.currentText())
    self.settings.setValue('scalar_dropdown', self.scalar_dropdown.currentText())
    self.settings.setValue('merge_dropdown', self.merge_dropdown.currentText())
    self.settings.setValue('merge_line_dropdown', self.merge_line_dropdown.currentText())
    self.settings.setValue('merge_shade_dropdown', self.merge_shade_dropdown.currentText())

    self.settings.setValue('filter_edit', self.filter_edit.text())

    # save auto-complete model for filter, up to 50 entries
    m = self.filter_edit.completer().model()
    history = [m.data(m.index(i), 0) for i in range(min(50, m.rowCount()))]
    self.settings.setValue('filter_completer', history)

    # save hidden status of individual experiments
    hidden_exp_paths = [exp.directory for exp in self.experiments.exps.values() if not exp.visible]
    self.settings.setValue('hidden_exp_paths', hidden_exp_paths)

    self.settings.sync()
    event.accept()


class SortableTableItem(QtWidgets.QTableWidgetItem):
  """Used to define custom sort order (stored as the 3rd UserRole data)
  for table cells representing objects such as datetimes"""
  def __init__(self, text, order):
    super().__init__(text)
    self.setData(table_data_order, order)

  def __lt__(self, other):
    return (self.data(table_data_order)() < other.data(table_data_order)())

def create_scroller():
  scroll_area = QtWidgets.QScrollArea()
  scroll_area.setWidgetResizable(True)

  scroll_widget = QtWidgets.QWidget(scroll_area)  # additional widget to enable scrollbars
  scroll_widget.setMinimumWidth(50)
  scroll_area.setWidget(scroll_widget)
  return (scroll_widget, scroll_area)

def print_datetime(dt):
  """Prints a friendly string with a given datetime object"""
  now = datetime.now(timezone.utc)
  dt = dt.astimezone()  # convert from UTC to local time for display
  if dt.day == now.day: return f"{dt:%X}"  # time
  if (now - dt).days <= 7: return f"{dt:%a, %X}"  # weekday, time
  if dt.year == now.year: return f"{dt.day} {dt:%b, %X}"  # day month, time
  return f"{dt.day} {dt:%b %Y, %X}"  # day month year, time


def set_style(app):
  app.setStyle("Fusion")

  directory = os.path.dirname(os.path.realpath(__file__))
  
  with open(directory + '/style.qss', 'r') as file:
    app.setStyleSheet(file.read())
