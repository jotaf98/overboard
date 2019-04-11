
import collections, json, glob, re, logging
import numpy as np
from os import path as os_path

class Experiment():
  def __init__(self, filename, base_folder, force_reopen_files):
    directory = os_path.dirname(filename)
    self.name = os_path.relpath(directory, base_folder)  # experiment name is the path relative to base folder
    self.filename = filename
    self.directory = directory

    # read JSON file for metadata (including timestamp), if it exists
    try:
      with open(directory + '/meta.json', 'r') as file:
        self.meta = json.load(file)
    except IOError:
      self.meta = {}

    self.names = []
    self.data = []
    
    # store whether the experiment has finished or not
    self.done = self.meta.get('_done', False)

    self.read_data = None
    self.visible = True
    self.is_selected = False
    self.style = {}  # used by Plots
    self.style_order = 1000

    # do first read
    self.read_data = self.read_data_slow() if force_reopen_files else self.read_data_fast()
    try:
      next(self.read_data)
    except StopIteration:
      pass
    except IOError:
      logging.exception('Error reading ' + self.filename)
  
  def read_data_fast(self):  # generator function
    # polls the file for new data, bu keeps the file handle open
    with open(self.filename, 'r') as file:
      has_new_data = False

      while True:
        # try to read new line. need to restore read position when there's no new
        # line to read, to cope with incomplete lines (while they're being written)
        where = file.tell()
        if self.read_single_line(file):
          has_new_data = True  # keep reading
        else:
          if self.done: return
          yield has_new_data

          has_new_data = False
          file.seek(where)  # back to beginning of line

  def read_data_slow(self):  # generator function
    # initial read
    with open(self.filename, 'r') as file:
      while self.read_single_line(file):
        pass
      where = file.tell()  # position for next read
    
    # detect when file size changes (note file handle is closed most of the time)
    old_size = 0
    while not self.done:
      new_size = os_path.getsize(self.filename)
      file_changed = (new_size != old_size)
      old_size = new_size

      if file_changed:
        # get new data from the file, picking up where we left off. don't use file size, depends on OS.
        with open(self.filename, 'r') as file:
          file.seek(where)
          while self.read_single_line(file):
            pass
          where = file.tell()  # remember where we left off for next time

      yield file_changed

  def read_single_line(self, file):
    # reads a single CSV line from the file, returning True if some data was read.
    line = file.readline()
    if line:
      if len(self.names) == 0:
        # read CSV file header (with stat names). they're separated by commas, which can be escaped: \,
        self.names = re.split(r'(?<!\\),', line.strip())

        if len(self.names) < 2: raise IOError('CSV has too few headers.')

        self.data = [[] for _ in range(len(self.names))]
      else:
        # read line of stat values
        values = line.split(',')

        if len(values) == len(self.names):
          for i in range(len(values)):  # read one value per column
            self.data[i].append(float(values[i]))
        else:
          if len(values) > len(self.names):
            raise IOError('CSV line has more cells than the header.')
          return False  # incomplete line, file may still be written to
        
      return True
    return False

  def enumerate_plots(self):
    # return list of plots and where/how to draw them, could be user-configured
    return [{
      'panel': y_name,
      'line': self.name,
      'x': self.names[0],
      'y': y_name,
      'exp': self,
      'width': 4 if self.is_selected else 2
    } for y_name in self.names[1:]]


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


def check_new_experiments(experiments, files_before, base_folder, window, force_reopen_files):
  # find experiment files
  files_now = set(glob.glob(base_folder + "/**/stats.csv", recursive=True))

  # add new ones
  new_files = files_now - files_before
  for filename in new_files:
    exp = Experiment(filename, base_folder, force_reopen_files)
    experiments.append(exp)
    window.add_experiment(exp, refresh_table=False)

  if len(new_files) > 0:
    window.refresh_table()

    # store the new list of files
    files_before.clear()
    files_before.update(files_now)
