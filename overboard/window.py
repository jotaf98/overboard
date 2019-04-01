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

from .flowlayout import FlowLayout
from .fastslider import Slider
from .visualizations import show_visualizations
from .experiments import Smoother


class Window(QtWidgets.QMainWindow):
  def __init__(self, args):
    super(Window, self).__init__(parent=None)
    
    self.experiments = {}  # filled in later
    self.plots = None  # standard stats plots
    self.visualizations = []  # custom visualization

    # get screen size
    screen_size = QtWidgets.QDesktopWidget().availableGeometry(self).size()

    # create the parent of both sidebar and plot area
    main = QtWidgets.QSplitter(self)

    # create sidebar
    sidebar = QtWidgets.QVBoxLayout()
    sidebar.setAlignment(Qt.AlignTop)
    widget = QtWidgets.QWidget(main)  # need dummy widget to wrap box layout
    widget.setLayout(sidebar)

    # plot size slider
    plotsize = args.plotsize
    if plotsize == 0:
      plotsize = screen_size.width() * 0.1
    sidebar.addWidget(QtWidgets.QLabel('Plot size'))
    slider = Slider(Qt.Horizontal)  #QtWidgets.QSlider(Qt.Horizontal)
    slider.setMinimum(screen_size.width() * 0.05)
    slider.setMaximum(screen_size.width() * 0.8)
    slider.setTickInterval(screen_size.width() * 0.005)
    slider.setValue(plotsize)  # initial value
    slider.valueChanged.connect(self.size_slider_changed)
    sidebar.addWidget(slider)
    self.size_slider = slider
    
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
    table.setFocusPolicy(Qt.NoFocus);  # disable item selection
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)  # smooth scrolling
    table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
    
    table.verticalHeader().hide()  # hide vertical header
    
    header = table.horizontalHeader()  # configure horizontal header
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignLeft)
    header.setSectionsMovable(True)
    header.setTextElideMode(Qt.ElideRight)  # show ellipsis for cut-off headers

    table.itemClicked.connect(self.table_click)

    sidebar.addWidget(table)
    self.table = table
    self.table_args = {}  # maps argument names to column indices
    self.prev_sort = None

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
  
  def add_experiment(self, exp, refresh_table=True):
    # ensure it has a style assigned, even if it has no plots
    if len(exp.style) == 0:
      (exp.style_order, exp.style) = next(self.plots.style_generator)

    # add experiment to plots
    self.plots.add(exp.enumerate_plots())
    self.experiments[exp.name] = exp

    # add experiment to table
    (table, table_args) = (self.table, self.table_args)
    header = table.horizontalHeader()

    # disable sorting to prevent bug when adding items. will be restored by refresh_table.
    self.prev_sort = (header.sortIndicatorSection(), header.sortIndicatorOrder())  # save state
    table.setSortingEnabled(False)

    # new row
    row = table.rowCount()
    table.insertRow(row)

    # create icon (label with unicode symbol) with the plot color. u'\u2611 \u2610'
    icon = self.set_table_cell(row, 0, u'\u2611')
    icon.setForeground(QColor(exp.style.get('color', '#808080')))
    # store experiment name with icon, to be retrieved later in table_click
    icon.setData(Qt.UserRole, 'hide')
    icon.setData(Qt.UserRole + 1, exp.name)

    # experiment name
    label = self.set_table_cell(row, 1, exp.name)
    label.setData(Qt.UserRole, 'select')
    label.setData(Qt.UserRole + 1, exp.name)

    # print a row of argument values for this experiment
    for arg_name in exp.meta.keys():
      if not arg_name.startswith('_'):
        if arg_name not in table_args:  # a new argument name, add a column
          col = table.columnCount()
          table.setColumnCount(col + 1)
          table.setHorizontalHeaderItem(col, QtWidgets.QTableWidgetItem(arg_name))  #, QtWidgets.QTableWidgetItem.Type
          table_args[arg_name] = col
        else:
          col = table_args[arg_name]
        
        self.set_table_cell(row, col, exp.meta.get(arg_name, ''))

    if refresh_table:
      self.refresh_table()
  
  def set_table_cell(self, row, col, value):
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

    item.setFlags(Qt.ItemIsEnabled)  # set not editable
    self.table.setItem(row, col, item)
    return item

  def refresh_table(self):
    # restore sorting
    table = self.table
    table.setSortingEnabled(True)
    if self.prev_sort:  # restore sort state (which column and direction)
      table.sortItems(*self.prev_sort)

    table.resizeColumnsToContents()
    
    # resize the column headers to fully contain the header text (resizeColumnsToContents ignores the headers)
    max_width = int(0.9 * table.parentWidget().width())  # don't let any column become wider than 90% of the sidebar
    header = table.horizontalHeader()
    metrics = QtGui.QFontMetrics(table.horizontalHeaderItem(0).font())
    for col in range(table.columnCount()):
      text = table.horizontalHeaderItem(col).text()
      text_width = metrics.boundingRect(text).width()
      header.resizeSection(col, min(max_width, max(table.sizeHintForColumn(col), text_width + 20)))  # needs some extra width
  
  def sort_table_by_timestamp(self, refresh_table=True):
    # convenience function called at initialization to move the timestamp column to the start, and sort it
    if 'timestamp' in self.table_args:
      header = self.table.horizontalHeader()
      col = self.table_args['timestamp']  # (logical) column index of timestamp
      header.moveSection(col, 2)  # move to the start (after the icon and experiment name)
      self.prev_sort = (col, Qt.DescendingOrder)  # refresh_table will sort using this column and order
      
    if refresh_table:
      self.refresh_table()

  def table_click(self, item):
    # check if there's an action associated with this cell
    action = item.data(Qt.UserRole)
    if action:
      name = item.data(Qt.UserRole + 1)
      exp = self.experiments[name]
      if action == 'hide':
        # toggle visibility of a given experiment, if the icon is clicked
        if exp.visible:
          # remove all associated plots
          self.plots.remove(exp.enumerate_plots())

          # reset icon and style, allowing it to be used by other experiments
          item.setForeground(QColor(128, 128, 128))
          item.setText(u'\u2610')
          self.plots.drop_style(exp.style_order, exp.style)
          exp.style = {}
        else:
          # assign new style
          if len(exp.style) == 0:
            (exp.style_order, exp.style) = next(self.plots.style_generator)
          
          item.setForeground(QColor(exp.style.get('color', "#808080")))
          item.setText(u'\u2611')

          # create plots
          self.plots.add(exp.enumerate_plots())

        exp.visible = not exp.visible

      elif action == 'select':
        # show visualizations for a given experiment
        show_visualizations(self, exp)

  def size_slider_changed(self):
    # resize plots and visualizations
    plotsize = self.size_slider.value()
    for panel in self.plots.panels.values():
      panel.setFixedWidth(plotsize)
      panel.setFixedHeight(plotsize)
    for panel in self.visualizations:
      panel.setFixedWidth(plotsize)
      panel.setFixedHeight(plotsize)
  
  def smooth_slider_changed(self):
    self.smoother = Smoother(self.smooth_slider.value() / 4.0)


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
