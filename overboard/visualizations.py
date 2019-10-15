
import math, logging, os, runpy
from collections import OrderedDict

import PyQt5.QtWidgets as QtWidgets
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
  from torchvision.utils import make_grid
except ImportError:
  make_grid = None

try:
  import PyQt5  # needed for matplotlib to recognize the binding to this backend
  import matplotlib
  from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
  from matplotlib.pyplot import cm as colormaps
except:
  def FigureCanvas(fig):
    logging.warning("Could not load MatPlotLib.")
    return pg.PlotWidget()
  colormaps = None
  matplotlib = None


class Visualizations():
  # custom visualizations, supports both MatPlotLib (MPL) and PyQtGraph (PG) figures
  def __init__(self, window, no_vis_snapshot, mpl_dpi):
    self.window = window
    window.visualizations = self  # back-reference

    self.panels = OrderedDict()  # widgets containing plots, indexed by name
    self.selected_exp = None  # selected experiment
    self.modules = {}  # loaded modules with visualization functions

    self.vis_counts = OrderedDict()
    self.last_size = None

    self.no_vis_snapshot = no_vis_snapshot
    if matplotlib is not None:
      matplotlib.rcParams['figure.dpi'] = mpl_dpi

  def load_single_vis(self, exp, name):
    # load a single visualization of the given experiment, with the given name.
    # first, load function info and arguments from pickled file, to the CPU.
    filename = exp.directory + '/' + name + '.pth'
    try:
      data = load(filename, map_location='cpu')
    except Exception as err:
      # ignore error about incomplete data, since file may still be written to; otherwise report it.
      if not isinstance(err, RuntimeError) or 'storage has wrong size' not in str(err):
        logging.exception("Error loading visualization data from " + filename)
        return []

    func_name = data['func']
    args = data['args']
    kwargs = data['kwargs']
    source_file = data['source']

    # call a built-in function, e.g. simple tensor visualization
    if source_file == 'builtin' and func_name == 'tensor':
      panels = tshow(*args, **kwargs, create_window=False, title=name)
    else:
      # custom visualization function. load the original source file or saved file
      # from the experiment directory, and call the specified function in it.
      if not self.no_vis_snapshot: source_file = exp.directory + '/' + name + '.py'
      panels = []

      try:
        # load module from file, unless it's cached already
        if source_file in self.modules:
          module = self.modules[source_file]
        else:
          module = runpy.run_path(source_file)

        try:
          # call the custom function, only if the module loaded successfully
          panels = module[func_name](name, *args, **kwargs)
          
          # cache module if no error so far (otherwise reload next time, maybe it's fixed)
          self.modules[source_file] = module

        except Exception:
          logging.exception('Error executing visualization function ' + func_name + ' from ' + source_file)

      except Exception:
        logging.exception('Error loading visualization function from ' + source_file)

    # ensure a list is returned
    if not isinstance(panels, list): panels = [panels]
    return panels

  def update(self):
    # called by a timer to check for updates. don't update if the experiment is finished.
    if self.selected_exp is None or self.selected_exp.done: return

    # see if the file size changed as a basic check
    try:
      new_size = os.path.getsize(self.selected_exp.directory + '/visualizations')
    except FileNotFoundError:
      return
    if self.last_size is None:
      self.last_size = new_size

    if new_size != self.last_size:
      self.last_size = new_size

      # load the list of visualizations and their refresh counts
      vis_counts = self.read_vis_counts(self.selected_exp)

      # check if any of them is new or its count changed
      for (name, count) in vis_counts.items():
        if name not in self.vis_counts or self.vis_counts[name] != count:
          # load the new data
          new_plots = self.load_single_vis(self.selected_exp, name)
          
          # assign each plot to a new or reused panel.
          # NOTE: most of this complicated logic is to deal with a specific MatPlotLib/
          # FigureCanvas bug. we cannot delete a FigureCanvas and assign a new one to the
          # same figure, or there are many graphical glitches (especially related to DPI).
          # to avoid this, we reuse the same widget (actually the parent panel widget) to
          # the same MatPlotLib figure every time (stored as overboard_panel attribute).
          new_panels = []
          old_panels = self.panels.get(name, [])
          next_idx = 0  # next available panel to reuse

          for plot in new_plots:
            if type(plot).__name__ == 'Figure' and hasattr(plot, 'overboard_panel'):
              # always reuse a previous panel for MPL figures
              panel = self.window.add_panel(plot.overboard_panel, name, reuse=True)
              panel.plot_widget.draw()  # ensure the figure is redrawn
            else:
              # not MPL, try to reuse a panel. first, skip over any existing MPL panels
              while next_idx < len(old_panels) and old_panels[next_idx].is_mpl_figure:
                next_idx += 1
              
              if next_idx < len(old_panels):
                # we can reuse this one. it contains a pg.GraphicsLayoutWidget.
                panel = old_panels[next_idx]
                panel.plot_widget.clear()
                panel.plot_widget.addItem(plot)
                panel = self.window.add_panel(panel, name, reuse=True)

              else:
                # create a new panel
                panel = self.add_vis_panel(plot, name)
            new_panels.append(panel)
          
          # remove any panels we did not reuse from the layout
          self.delete_vis_panels(list(set(old_panels) - set(new_panels)))
          self.panels[name] = new_panels

  def select(self, exp):
    # select a new experiment, showing its visualizations (and removing previously selected ones)
    self.selected_exp = exp
    self.modules = {}  # always reload modules when selecting, in case they're stale
    new_panels = []
    if exp is not None:
      # load master list of visualizations (and their counts), then load each one
      vis_counts = self.read_vis_counts(exp)

      for name in vis_counts.keys():
        # load data into plots, and turn them into visible panels
        plots = self.load_single_vis(exp, name)
        panels = [self.add_vis_panel(plot, name, add_to_layout=False) for plot in plots]
        new_panels.append((name, panels))

    new_panels = OrderedDict(new_panels)

    # remove previous widgets (this is done after loading the visualizations to reduce delay)
    self.delete_vis_panels(self.all_panels())

    # add the new widgets to the flow layout, in order
    self.panels = new_panels
    for panel in self.all_panels():
      self.window.flow_layout.addWidget(panel)

    self.last_size = None

  def all_panels(self):  # flatten nested list of panels
    if len(self.panels) == 0: return []  # special case
    return [p for panels in self.panels.values() for p in panels]
    
  def add_vis_panel(self, plot, name, add_to_layout=True):
    # wrap MatPlotLib figure or PyQtGraph PlotItem in a Qt widget
    is_mpl_figure = (type(plot).__name__ == 'Figure')
    if is_mpl_figure:
      widget = FigureCanvas(plot)
    else:
      widget = pg.GraphicsLayoutWidget()
      widget.addItem(plot)

    # wrap that in a panel with title
    panel = self.window.add_panel(widget, name, add_to_layout=add_to_layout)

    panel.is_mpl_figure = is_mpl_figure
    if is_mpl_figure:
      plot.overboard_panel = panel  # always associate the same panel with this figure

    return panel
  
  def delete_vis_panels(self, panels):
    # remove panels from the layout. MPL panels cannot be deleted, they need to
    # be reused if the same figure is displayed. note self.panels is not updated.
    for panel in panels:
      panel.setParent(None)
      if not panel.is_mpl_figure:
        panel.deleteLater()

  def read_vis_counts(self, exp):
    # read and return visualizations list, including their update counts
    vis_counts = OrderedDict()
    try:
      with open(exp.directory + '/visualizations', 'r') as file:
        for line in file:
          values = line.split('\t')
          if len(values) == 2:
            vis_counts[values[0]] = int(values[1])  # the format is: "name count\n"
    except:
      pass
    return vis_counts


tshow_images = []
def tshow(tensor, create_window=True, title='Tensor', data_range=None, grayscale=False, legend=None, **kwargs):
  """Shows a PyTorch tensor (including one or more RGB images) using PyQtGraph."""

  if make_grid is None:
    raise ImportError('Could not import torchvision (from PyTorch), which is necessary for tshow.')

  tensor = tensor.detach().cpu()
  original_shape = tensor.shape

  if data_range is None:
    data_range = (tensor.min(), tensor.max())

  if len(tensor.shape) > 4:
    logging.exception('Cannot show tensors with more than 4 dimensions.')
    return None

  # insert singleton dimensions on the left to always get 4 dimensions
  while len(tensor.shape) < 4:
    tensor = tensor.unsqueeze(0)

  sh = tensor.shape
  if sh[0] == 1:  # case of 3D tensors, leave singleton dimension for color
    tensor = tensor.reshape(sh[1], 1, sh[2], sh[3])

  sh = tensor.shape
  if sh[1] in [1, 3]:
    # a linear collection of images: channels are RGB or single-channel.
    # choose number of columns such that they are laid out in a square.
    if 'nrow' not in kwargs:
      #kwargs['nrow'] = math.ceil(math.sqrt(sh[0]))
      kwargs['nrow'] = math.ceil(math.sqrt(sh[0]) * sh[2] / sh[3])
  else:
    # when channels are not RGB or single-channel, display them as columns
    tensor = tensor.reshape(sh[0] * sh[1], 1, sh[2], sh[3])
    kwargs['nrow'] = sh[1]


  # arrange into a grid
  image = make_grid(tensor, **kwargs, normalize=False, padding=0)
  image = image.permute(2, 1, 0).numpy()  # pytorch convention to numpy image convention

  # convert grayscale RGB images to colormapped images (single-channel)
  if tensor.shape[1] == 1:
    image = image[:,:,0]

  # show it
  im_item = pg.ImageItem(image)
  title = title + ' ' + str(tuple(original_shape))

  if create_window:  # stand-alone window
    win = pg.GraphicsWindow(title=title)
    plot = win.addPlot()
  else:  # plot item to return
    plot = pg.PlotItem()
  plot.addItem(im_item)

  plot.getViewBox().invertY(True)
  plot.setAspectLocked(True)
  plot.hideAxis('left')
  plot.hideAxis('bottom')

  # draw a grid
  (cell_w, cell_h) = (sh[3], sh[2])
  (w, h) = image.shape[0:2]
  for x in range(0, w + 1, cell_w):
    plot.plot([x, x], [0, h])
  for y in range(0, h + 1, cell_h):
    plot.plot([0, w], [y, y])

  if len(image.shape) == 3:
    # RGB image
    im_item.setLevels([data_range]*3)
  else:
    # grayscale image or heatmap, set up colormap and possibly a legend
    if not grayscale and colormaps is not None:
      # use better colormap if matplotlib is available
      colormap = colormaps.viridis
      colormap._init()
      lut = (colormap._lut * 255)[:-1,:]  # remove last row
      im_item.setLookupTable(lut)
      (low_color, high_color) = (lut[0,:3], lut[-1,:3])
    else:
      lut = []
      (low_color, high_color) = ('k', 'w')

    im_item.setLevels(data_range)

    if legend or (legend is None and not grayscale):
      # create legend with max and min values
      leg = plot.addLegend(offset=(1, 1))
      leg.addItem(FilledIcon(low_color), "Min: {:.3g}".format(data_range[0]))
      leg.addItem(FilledIcon(high_color), "Max: {:.3g}".format(data_range[1]))

      # monkey-patch paint method to draw a more opaque background
      def paint(self, p, *args):
        color = pg.mkColor(pg.getConfigOption('background'))
        color.setAlpha(200)
        p.fillRect(self.boundingRect(), pg.mkBrush(color))
      leg.paint = paint.__get__(leg)

  if create_window:
    tshow_images.append(win)  # keep reference, otherwise the window will be garbage-collected
    win.show()
  else:
    return plot


class FilledIcon(pg.graphicsItems.LegendItem.ItemSample):
  """Custom legend icon, completely filled with a single color."""
  def __init__(self, color):
    super().__init__(None)
    self.color = color
    self.setFixedWidth(20)

  def paint(self, p, *args):
    p.fillRect(self.boundingRect(), pg.mkBrush(*self.color))

