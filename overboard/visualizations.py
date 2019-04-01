
import os, runpy
import pyqtgraph as pg

try:
  from torch import load
except ImportError:
  # fallback to regular pickle if pytorch not installed
  import pickle
  def load(path):
    with open(path, 'rb') as file:
      pickle.load(file)

try:
  import PyQt5  # needed for matplotlib to recognize the binding to this backend
  import matplotlib
  from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
except:
  FigureCanvas = None


def show_visualizations(window, exp):
  # support both MatPlotLib (MPL) and PyQtGraph (PG) figures
  figures = []
  for name in exp.meta.get('vis', []):  # iterate visualizations
    # load function info and arguments from pickled file
    data = load(exp.directory + '/' + name + '.pth')

    func_name = data['func']
    args = data['args']
    kwargs = data['kwargs']

    # load the saved module from the experiment directory
    module = runpy.run_path(exp.directory + '/' + name + '.py')

    # get the function from the module and call it
    figs = module[func_name](name, *args, **kwargs)
    figures.extend(figs)
  
  # remove previous panels (this is done after producing the visualizations to reduce delay)
  for widget in window.visualizations:
    widget.setParent(None)
    widget.deleteLater()
  window.visualizations = []

  # show the resulting figures
  plotsize = window.size_slider.value()
  for fig in figures:
    if isinstance(fig, pg.PlotWidget):
      widget = fig
    else:
      if FigureCanvas is None:
        raise ImportError("Could not load MatPlotLib.")
      widget = FigureCanvas(fig)

    # set the widget size and add it to the flow layout
    widget.setFixedWidth(plotsize)
    widget.setFixedHeight(plotsize)

    window.flow_layout.addWidget(widget)
    window.visualizations.append(widget)

