#os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "TRUE"

import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
from PyQt5.QtCore import Qt
from PyQt5.Qt import QPalette, QColor

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

import os
from time import time

from .flowlayout import FlowLayout
from .fastslider import Slider
from .plots import Smoother


class Window(QtWidgets.QMainWindow):
  def __init__(self, args):
    super(Window, self).__init__(parent=None)
    
    self.experiments = None  # object that manages experiments
    self.plots = None  # object that manages plots
    self.visualizations = None  # object that manages custom visualizations
    self.last_process_events = time()  # to update during heavy loads

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
    plotsize = args.plotsize
    if plotsize == 0:
      plotsize = screen_size.width() * 0.2
    sidebar.addWidget(QtWidgets.QLabel('Panel size'), 0, 0)
    slider = Slider(Qt.Horizontal)  # replaces QtWidgets.QSlider(Qt.Horizontal)
    slider.setMinimum(screen_size.width() * 0.05)
    slider.setMaximum(screen_size.width() * 0.8)
    slider.setTickInterval(screen_size.width() * 0.005)
    slider.setValue(plotsize)  # initial value
    slider.valueChanged.connect(self.size_slider_changed)
    sidebar.addWidget(slider, 0, 1)
    self.size_slider = slider
    
    # dropdown lists for plot configuration
    sidebar.addWidget(QtWidgets.QLabel('X axis'), 1, 0)
    dropdown = QtWidgets.QComboBox()
    dropdown.addItem('First metric')
    dropdown.addItem('Panel metric')
    dropdown.addItem('All metrics')
    dropdown.setCurrentIndex(0)
    dropdown.activated.connect(self.rebuild_plots) 
    sidebar.addWidget(dropdown, 1, 1)
    self.x_dropdown = dropdown

    sidebar.addWidget(QtWidgets.QLabel('Y axis'), 2, 0)
    dropdown = QtWidgets.QComboBox()
    dropdown.addItem('First metric')
    dropdown.addItem('Panel metric')
    dropdown.addItem('All metrics')
    dropdown.setCurrentIndex(1)
    dropdown.activated.connect(self.rebuild_plots) 
    sidebar.addWidget(dropdown, 2, 1)
    self.y_dropdown = dropdown

    sidebar.addWidget(QtWidgets.QLabel('Panels'), 3, 0)
    dropdown = QtWidgets.QComboBox()
    dropdown.addItem('One per metric')
    dropdown.addItem('One per experiment')
    dropdown.setCurrentIndex(0)
    dropdown.activated.connect(self.rebuild_plots) 
    sidebar.addWidget(dropdown, 3, 1)
    self.panel_dropdown = dropdown


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
    table = QtWidgets.QTableWidget(0, 2)  # zero rows, two columns
    table.setHorizontalHeaderLabels(['', 'run'])  # column headers
    table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)

    # table style
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)

    #table.setFocusPolicy(Qt.NoFocus)
    table.setSelectionBehavior(QtWidgets.QTableView.SelectRows)  # allow selecting rows
    table.setSelectionMode(QtWidgets.QTableView.ExtendedSelection)

    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)  # smooth scrolling
    table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
    
    table.verticalHeader().hide()  # hide vertical header
    
    header = table.horizontalHeader()  # configure horizontal header
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignLeft)
    header.setSectionsMovable(True)
    header.setTextElideMode(Qt.ElideRight)  # show ellipsis for cut-off headers
    header.setHighlightSections(False)  # no bold header when cells are clicked

    table.itemClicked.connect(self.table_click)
    table.itemSelectionChanged.connect(self.table_select)

    self.table_args = {}  # maps argument names to column indices
    
    # create timestamp column in table (third) and sort by it
    table.setColumnCount(3)
    table.setHorizontalHeaderItem(2, QtWidgets.QTableWidgetItem('timestamp'))
    table.sortItems(2, Qt.DescendingOrder)
    self.table_args['timestamp'] = 2

    self.table = table
    self.selected_exp = None
    sidebar.addWidget(table, sidebar.rowCount(), 0, 1, 2)
    
    # create the scroll area with plots
    (plot_scroll_widget, plot_scroll_area) = create_scroller()
    main.addWidget(plot_scroll_area)

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

  def process_events_if_needed(self):
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
    plotsize = self.size_slider.value()
    panel.setFixedWidth(plotsize)
    panel.setFixedHeight(plotsize)

    if add_to_layout:  # add to window's flow layout
      self.flow_layout.addWidget(panel)

    return panel
  

  def on_exp_init(self, exp):
    """Called by Experiment when it is initialized"""
    # add experiment to table
    table = self.table
    header = table.horizontalHeader()

    # disable sorting to prevent bug when adding items, to restore afterwards
    prev_sort = (header.sortIndicatorSection(), header.sortIndicatorOrder())
    table.setSortingEnabled(False)

    # new row
    row = table.rowCount()
    table.insertRow(row)

    # persistent mapping between an experiment and its row (even as they're sorted)
    exp.table_row = QtCore.QPersistentModelIndex(table.model().index(row, 0))

    # create icon (label with unicode symbol) with the plot color. u'\u2611 \u2610'
    icon = self.set_table_cell(row, 0, u'\u2611', selectable=False)
    icon.setForeground(QColor(exp.style.get('color', '#808080')))
    # store experiment name with icon, to be retrieved later in table_click
    icon.setData(Qt.UserRole, 'hide')
    icon.setData(Qt.UserRole + 1, exp.name)

    # show experiment name
    self.set_table_cell(row, 1, exp.name)

    # restore sorting, and sort state (which column and direction)
    table.setSortingEnabled(True)
    table.sortItems(*prev_sort)

    self.process_events_if_needed()

  def on_exp_meta_ready(self, exp):
    """Called by Experiment when the meta-data has been read"""
    # print a row of meta-data (argument) values for this experiment in the table
    (table, table_args) = (self.table, self.table_args)
    added_columns = False

    for arg_name in exp.meta.keys():
      if not arg_name.startswith('_'):
        if arg_name not in table_args:  # a new argument name, add a column
          col = table.columnCount()
          table.setColumnCount(col + 1)
          table.setHorizontalHeaderItem(col, QtWidgets.QTableWidgetItem(arg_name))  #, QtWidgets.QTableWidgetItem.Type
          table_args[arg_name] = col
          added_columns = True
        else:
          col = table_args[arg_name]
        
        self.set_table_cell(exp.table_row.row(), col, exp.meta.get(arg_name, ''))

    if added_columns:
      self.resize_table()

    self.process_events_if_needed()
  
  def on_exp_header_ready(self, exp):
    """Called by Experiment when the header data (metrics/column names) has been read"""
    # update dropdown lists to include all metric names
    for name in exp.names:
      if self.x_dropdown.findText(name) < 0:
        self.x_dropdown.addItem(name)
      if self.y_dropdown.findText(name) < 0:
        self.y_dropdown.addItem(name)

  def rebuild_plots(self):
    """Rebuild all plots (e.g. when plot options such as x/y axis change)"""
    self.plots.remove_all()
    for exp in self.experiments.exps.values():
      self.plots.add(exp)

  def set_table_cell(self, row, col, value, selectable=True):
    # helper to set a single table cell in the sidebar.
    # try to interpret as integer or float, to allow numeric sorting of columns
    if not isinstance(value, int) and not isinstance(value, float):
      value = str(value)  # handle e.g. dicts
      try:
        value = float(value)
        if int(value) == value:  # store as int if possible, prints better
          value = int(value)
      except ValueError: pass

    if isinstance(value, str):  # faster option for strings
      item = QtWidgets.QTableWidgetItem(value)
    else:  # sort as number if not a string
      item = QtWidgets.QTableWidgetItem()
      item.setData(Qt.EditRole, QtCore.QVariant(value))

    flags = Qt.ItemIsEnabled  # set not editable
    if selectable:
      flags = flags | Qt.ItemIsSelectable
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

  def table_click(self, item):
    # check if there's an action associated with this cell
    action = item.data(Qt.UserRole)
    if action:
      name = item.data(Qt.UserRole + 1)
      exp = self.experiments.exps[name]
      if action == 'hide':
        # toggle visibility of a given experiment, if the icon is clicked
        if exp.visible:
          # remove all associated plots
          self.plots.remove(exp)

          # reset icon and style, allowing it to be used by other experiments
          item.setForeground(QColor(128, 128, 128))
          item.setText(u'\u2610')
          self.plots.drop_style(exp.style_order, exp.style)
          exp.style = {}
        else:
          # assign new style
          (exp.style_order, exp.style) = self.plots.get_style()
          
          item.setForeground(QColor(exp.style.get('color', "#808080")))
          item.setText(u'\u2611')

          # create plots
          self.plots.add(exp)

        exp.visible = not exp.visible

  def table_select(self):
    # selection changed
    items = self.table.selectedItems()
    if items:  # get associated experiment
      exp = self.row_to_experiment(items[0].row())
    else:
      exp = None

    # unselect previous experiment first
    if self.selected_exp and self.selected_exp != exp:
      self.selected_exp.is_selected = False
      if self.selected_exp.visible:  # update its view
        self.plots.add(self.selected_exp)

    if items:  # select new one
      exp.is_selected = True
      self.plots.add(exp)
      self.selected_exp = exp
      self.visualizations.select(exp)
    else:
      self.selected_exp = None
      self.visualizations.select(None)

  def row_to_experiment(self, row):
    # check left-most cell of the given row to get the associated experiment name
    leftmost = self.table.item(row, 0)
    name = leftmost.data(Qt.UserRole + 1)
    return self.experiments.exps[name]
  
  def size_slider_changed(self):
    # resize plots and visualizations
    plotsize = self.size_slider.value()
    for panel in self.plots.panels.values():
      panel.setFixedWidth(plotsize)
      panel.setFixedHeight(plotsize)
    for panel_group in self.visualizations.panels.values():
      for panel in panel_group:
        panel.setFixedWidth(plotsize)
        panel.setFixedHeight(plotsize)
  
  #def smooth_slider_changed(self):
  #  self.smoother = Smoother(self.smooth_slider.value() / 4.0)


def create_scroller():
  scroll_area = QtWidgets.QScrollArea()
  scroll_area.setWidgetResizable(True)

  scroll_widget = QtWidgets.QWidget(scroll_area)  # additional widget to enable scrollbars
  scroll_widget.setMinimumWidth(50)
  scroll_area.setWidget(scroll_widget)
  return (scroll_widget, scroll_area)


def set_style(app):
  app.setStyle("Fusion")

  directory = os.path.dirname(os.path.realpath(__file__))
  
  with open(directory + '/style.qss', 'r') as file:
    app.setStyleSheet(file.read())
