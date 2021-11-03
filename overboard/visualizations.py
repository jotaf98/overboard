
import math, logging, os
from collections import OrderedDict
from importlib.util import spec_from_loader, module_from_spec

from fs import open_fs  # pyfilesystem
from fs.errors import FSError

from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QTimer
import pyqtgraph as pg
import pyqtgraph.opengl as gl

try:
  from torch import load as pt_load
  def load(file):  # ensure tensors are not loaded on the GPU
    return pt_load(file, map_location='cpu')
except ImportError:
  # fall back to regular pickle if pytorch not installed
  from pickle import load

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


class Visualizations(QObject):
  """Custom visualizations, supports both MatPlotLib (MPL) and PyQtGraph (PG) figures"""

  # signal to select a different folder for the VisualizationsLoader object,
  # in a different thread
  select_folder = pyqtSignal(str, bool)

  def __init__(self, window, mpl_dpi, poll_time):
    super().__init__()

    self.window = window
    window.visualizations = self  # back-reference

    self.panels = OrderedDict()  # widgets containing plots, indexed by name
    self.modules = {}  # loaded modules with visualization functions

    if matplotlib is not None:
      matplotlib.rcParams['figure.dpi'] = mpl_dpi
    
    # create loader object and thread
    if poll_time > 0:
      self.loader = VisualizationsLoader(poll_time=poll_time)
      self.thread = QThread()

      # connect VisualizationsLoader's signal to Visualizations method slot,
      # to return new visualizations
      self.loader.visualization_ready.connect(self.on_visualization_ready)
      self.loader.moveToThread(self.thread)  # move the loader object to the thread
      self.thread.start()  # start thread. note only select_folder will start the polling.

      self.select_folder.connect(self.loader.select_folder)

  def render_visualization(self, name, data, source_code):
    """Render a visualization to a MatPlotLib or PyQtGraph figure, by calling a
    custom function loaded from a pickle file"""

    # visualization function info and arguments
    func_name = data['func']
    args = data['args']
    kwargs = data['kwargs']
    source_file = data['source']

    # call a built-in function, e.g. simple tensor visualization
    if source_file == 'builtin' and func_name == 'tensor':
      panels = tshow(*args, **kwargs, create_window=False, title=name)
    else:
      # custom visualization function. load the saved source code file from
      # the experiment directory, and call the specified function in it.
      panels = []

      try:
        if name in self.modules:
          module = self.modules[name]  # reuse cached module
        else:
          # create an empty module, and populate it with exec on the source code string
          module = module_from_spec(spec_from_loader(name, loader=None, origin=source_file))
          exec(source_code, module.__dict__)

          try:
            # call the custom function, only if the module loaded successfully
            panels = getattr(module, func_name)(name, *args, **kwargs)
            
            # cache module if no error so far (otherwise reload next time, maybe it's fixed)
            self.modules[name] = module

          except Exception:
            logging.exception('Error executing visualization function ' + func_name + ' from ' + source_file)

      except Exception:
        logging.exception('Error loading visualization function from ' + source_file)

    # ensure a list is returned
    if not isinstance(panels, list): panels = [panels]
    return panels


  def on_visualization_ready(self, name, data, source_code):
    """Called when an updated visualization (possibly new) has been
    loaded for the current experiment"""

    # render the MatPlotLib/PyQtGraph figures
    new_plots = self.render_visualization(name, data, source_code)
    
    # assign each plot to a new or reused panel.
    # NOTE: most of this complicated logic is to deal with a specific MatPlotLib/
    # FigureCanvas bug. we cannot delete a FigureCanvas and assign a new one to the
    # same figure, or there are many graphical glitches (especially related to DPI).
    # to avoid this, we reuse the same widget (actually the parent panel widget) for
    # the same MatPlotLib figure every time (stored as overboard_panel attribute).
    new_panels = []
    old_panels = self.panels.get(name, [])
    old_panels_pg = [p for p in old_panels if p.plot_type == 'PlotItem']
    old_panels_gl = [p for p in old_panels if p.plot_type == 'GLViewWidget']

    for plot in new_plots:
      plot_type = self.get_plot_type(plot)
      if plot_type == 'Figure':  # MatPlotLib Figure
        if hasattr(plot, 'overboard_panel'):  # always reuse a previous panel
          panel = self.window.add_panel(plot.overboard_panel, name, reuse=True)
          panel.plot_widget.draw()  # ensure the figure is redrawn
        else:  # it's new
          widget = FigureCanvas(plot)
          panel = self.window.add_panel(widget, name)
          plot.overboard_panel = panel  # always associate the same panel with this figure

      elif plot_type == 'PlotItem':  # PyQtGraph PlotItem
        if old_panels_pg:
          # we can reuse an old panel and the pg.GraphicsLayoutWidget that it contains
          panel = old_panels_pg.pop()
          panel.plot_widget.clear()
          panel.plot_widget.addItem(plot)
          panel = self.window.add_panel(panel, name, reuse=True)
        else:  # it's new
          widget = pg.GraphicsLayoutWidget()
          widget.addItem(plot)
          panel = self.window.add_panel(widget, name)

      elif plot_type == 'GLViewWidget':  # PyQtGraph GLViewWidget
        widget = plot
        if old_panels_gl:
          # we can reuse an old panel, but assign the new GLViewWidget to it
          panel = old_panels_gl.pop()

          # remove the old one
          panel.plot_widget.setParent(None)
          panel.layout().removeWidget(panel.plot_widget)
          if panel.plot_widget is not widget:  # don't delete if the same widget was returned by the user's custom function
            panel.plot_widget.deleteLater()

          # insert the new
          panel.plot_widget = widget
          panel.layout().addWidget(widget, stretch=1)
          panel = self.window.add_panel(panel, name, reuse=True)
        else:  # it's new
          panel = self.window.add_panel(widget, name)

        plot.show()  # ensure the OpenGL plot is updated

      panel.plot_type = plot_type  # remember the plot type (regardless of nested widgets)
      new_panels.append(panel)
    
    # remove any panels we did not reuse from the layout
    self.delete_vis_panels(list(set(old_panels) - set(new_panels)))
    self.panels[name] = new_panels

  def select(self, exp):
    """Select a new experiment, showing its visualizations (and removing previously selected ones)"""
    # start loading visualizations
    if exp is not None:
      self.select_folder.emit(exp.directory, exp.done)
    else:
      self.select_folder.emit('', False)

    # remove previous widgets
    self.delete_vis_panels(self.all_panels())
    self.panels = {}
    self.modules = {}  # always reload modules when selecting, in case they're stale

  def all_panels(self):
    """Flatten nested list of panels"""
    if len(self.panels) == 0: return []  # special case
    return [p for panels in self.panels.values() for p in panels]
    
  def delete_vis_panels(self, panels):
    """Remove panels from the layout"""
    # MatPlotLib panels cannot be deleted, they need to be reused if the same figure is
    # displayed. note self.panels is not updated.
    for panel in panels:
      panel.setParent(None)
      if panel.plot_type != 'Figure':
        panel.deleteLater()

  def get_plot_type(self, plot):
    """Return the class name of a plot type (Figure, PlotItem or GLViewWidget).
    Throw an error if the type is not valid."""
    if type(plot).__name__ == 'Figure':
      return 'Figure'
    if isinstance(plot, pg.PlotItem):
      return 'PlotItem'
    if isinstance(plot, gl.GLViewWidget):
      return 'GLViewWidget'
    raise TypeError("Visualization functions (Logger.visualize) should return a list of"
      "MatPlotLib Figure, PyQtGraph PlotItem, or PyQtGraph GLViewWidget. A plot with "
      "class " + type(plot).__name__ + " was found.")


class VisualizationsLoader(QObject):
  """Waits for and loads new visualizations asynchronously, on a separate thread"""

  # signal to return new visualizations to the Visualizations object, on the main thread
  visualization_ready = pyqtSignal(str, dict, str)

  def __init__(self, poll_time):
    super().__init__()
    self.poll_time = poll_time
    self.timer = None
    self.fs = None

  @pyqtSlot(str, bool)
  def select_folder(self, folder, exp_done):
    """Monitor a different folder (or None)"""

    self.base_folder = folder
    self.exp_done = exp_done
    self.known_file_sizes = {}
    self.files_iterator = None
    self.retry_file = None
    self.source_code = {}

    if self.fs:
      self.fs.close()
      self.fs = None

    if self.timer is None:
      # create timer for the first time. note this must be done after
      # the object was moved to the thread, not in the constructor.
      self.timer = QTimer()
      self.timer.timeout.connect(self.poll)
      self.timer.setSingleShot(True)

    self.timer.stop()  # reset timer
    if self.base_folder is not None:  # start polling for changes/loading visualizations
      self.timer.start(100)

  @pyqtSlot()
  def poll(self):
    """Check for new or updated visualizations.
    Since the main use case involves remote files mounted with SSHFS/NFS, polling is
    the only viable mechanism to detect changes. This is further argued here:
    https://github.com/samuelcolvin/watchgod#why-no-inotify--kqueue--fsevent--winapi-support"""

    if not self.base_folder: return

    if not self.fs:  # create a file system object for the visualizations folder
      try:
        self.fs = open_fs(self.base_folder + '/visualizations')
      except FSError:
        # directory doesn't exist yet, try again later
        self.timer.start(self.poll_time * 1000)
        return

    # find files in the visualizations directory
    if self.files_iterator is None:
      self.files_iterator = self.fs.filterdir('.', files=['*.pth'], namespaces=['details'])

    if self.retry_file:  # try the same file again if required
      entry = self.retry_file
      self.retry_file = None
    else:
      # get next file
      try:
        entry = next(self.files_iterator)
      except StopIteration:
        entry = None

    # get pytorch pickle files
    if entry:
      name = entry.name[:-4]  # remove extension
      new_size = entry.size

      if new_size != self.known_file_sizes.get(name):
        # new file or file size changed
        self.known_file_sizes[name] = new_size

        # if the source code hasn't been loaded yet, read it
        if name not in self.source_code:
          try:
            self.source_code[name] = self.fs.readtext(name + '.py')
          except FSError:  # not found, must be a built-in (like tshow)
            self.source_code[name] = None

        # load the file (asynchronously with the main thread)
        try:
          with self.fs.open(name + '.pth', mode='rb') as file:
            data = load(file)

          if not isinstance(data, dict) or 'func' not in data:
            raise OSError("Attempted to load a visualization saved with a different protocol version (saving with PyTorch and loading without it is not supported, and vice-versa).")

          # send a signal with the results to the main thread
          self.visualization_ready.emit(name, data, self.source_code[name])

        except Exception as err:
          # ignore errors about incomplete data, since file may
          # still be written to; otherwise log the error.
          if isinstance(err, RuntimeError) and 'storage has wrong size' in str(err):
            self.retry_file = entry  # try this file again later
          else:
            logging.exception(f"Error loading visualization data from {self.base_folder}/{name}.pth")
    
    # wait a bit before checking next file, or a longer time if finished all files.
    # if the experiment is done, don't check again at the end.
    if entry:
      self.timer.start(100)
    elif not self.exp_done:
      self.files_iterator = None  # check directory contents from scratch next time
      self.timer.start(self.poll_time * 1000)


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

