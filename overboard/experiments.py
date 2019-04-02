import os, collections, json, glob, re
import numpy as np

class Experiment():
  def __init__(self, filename, base_folder):
    directory = os.path.dirname(filename)
    self.name = os.path.relpath(directory, base_folder)  # experiment name is the path relative to base folder
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
    self.read_data = self.read_data_generator()
    try:
      next(self.read_data)
    except StopIteration:
      pass
  
  def read_data_generator(self):  # generator function
    # open CSV file with stat data
    with open(self.filename, 'r') as file:
      has_new_data = False

      while True:
        # try to read new line
        where = file.tell()  # need to restore file pointer when there's no new line to read, to cope with bug while file is being written to
        line = file.readline()

        if line:
          if len(self.names) == 0:
            # read CSV file header (with stat names). they're separated by commas, which can be escaped: \,
            self.names = re.split(r'(?<!\\),', line.strip())
            self.data = [[] for _ in range(len(self.names))]
          else:
            # read line of stat values
            values = line.split(',')

            for i in range(len(values)):  # read one value per column
              self.data[i].append(float(values[i]))

            has_new_data = True
        else:
          if self.done: return
          yield has_new_data
          has_new_data = False
          file.seek(where)  # back to beginning of line

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


def check_new_experiments(experiments, files_before, base_folder, window):
  # find experiment files
  files_now = set(glob.glob(base_folder + "/**/stats.csv", recursive=True))

  # add new ones
  new_files = files_now - files_before
  for filename in new_files:
    exp = Experiment(filename, base_folder)
    experiments.append(exp)
    window.add_experiment(exp, refresh_table=False)

  if len(new_files) > 0:
    window.refresh_table()

    # store the new list of files
    files_before.clear()
    files_before.update(files_now)
