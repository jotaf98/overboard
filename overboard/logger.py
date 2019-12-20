
import os, math, time, json, inspect, shutil, re
from datetime import datetime, timezone

try:
  from torch import save
except ImportError:
  # fallback to regular pickle if pytorch not installed
  import pickle
  def save(obj, path):
    with open(path, 'wb') as file:
      pickle.dump(obj, file, pickle.HIGHEST_PROTOCOL)


def get_timestamp(microseconds=True):
  """Current timestamp in UTC timezone (no daylight savings, etc)"""
  t = datetime.now(timezone.utc)
  if not microseconds: t = t.replace(microsecond=0)
  return str(t)


class Logger:
  def __init__(self, directory, stat_names=None, meta=None, save_timestamp=True, resume=False):
    """Initialize log writer on a new directory.
       The main file that is written is "stats.csv", containing one column for each stat."""

    if stat_names and not (all(isinstance(name, str) and not ',' in name for name in stat_names)):
      raise ValueError('stat_names must be a list of strings with no commas, if specified.')

    self.directory = directory
    self.resume = resume
    self.wrote_header = False
    self.stat_names = None  # set later

    # for averaging stats before appending to the log
    self.avg_accum = {}
    self.avg_count = {}

    # meta should be a dict or a Namespace object from argparse
    if meta is None:
      meta = {}  # ensure it's a new dict instance (default arguments all refer to the same instance)
    elif meta.__class__.__name__ == 'Namespace':  # check type without importing argparse
      meta = vars(meta)
    elif not isinstance(meta, dict):
      raise AssertionError("Meta should be a dictionary or argparse.Namespace.")

    self.meta = meta
    self.save_timestamp = save_timestamp

    self.vis_functions = {}  # custom function associated with each visualization
    self.vis_counts = {}  # number of times each visualization was updated
    self.vis_padding = 0

    self.clock = -math.inf  # for rate_limit

    # create directory if it doesn't exist, and (empty) visualizations file
    os.makedirs(self.directory, exist_ok=True)
    with open(self.directory + '/visualizations', 'w') as file:
      pass

    # get current timestamp as string, including timezone offset
    if self.save_timestamp:
      self.meta['timestamp'] = get_timestamp(microseconds=False)
    
    # write metadata to JSON file
    if self.meta:
      with open(self.directory + '/meta.json', 'w') as file:
        json.dump(self.meta, file)
    
    # read existing CSV file and verify integrity
    if self.resume:
      (self.stat_names, lines) = self._read_file(ignore_empty=True)

      if stat_names is not None and stat_names != self.stat_names:
        raise ValueError("Attempting to resume writing to a log with different metrics (stats_names) than those given in the Logger constructor.")

    # clear and open CSV file
    self.file = open(self.directory + '/stats.csv', 'w')
    
    # write back any previous data (including header)
    if self.resume:
      self.file.writelines(lines)
      self.wrote_header = True

  def append(self, points=None):
    """Write the given stats dict to CSV file. If none is given, the average values computed so far are used (see update_average)."""

    if points is None:
      # use computed average, and reset accumulator
      points = self.average()
      self.avg_accum = {}
      self.avg_count = {}

    if self.stat_names is None:  # assume the given stats are all there is
      self.stat_names = list(points.keys())

    else:  # validate them
      for name in points.keys():
        if name not in self.stat_names:
          raise ValueError('Unknown stat name: ' + name + '. Note that no new stats can be added after the first Logger.append call. Alternatively, they can be specified in the constructor.')

    # write header if not done yet
    if not self.wrote_header:
      self.file.write('time,' + ','.join(self.stat_names) + '\n')
      self.wrote_header = True

    # first element is always the time
    self.file.write(get_timestamp())

    # write remaining stat values
    for name in self.stat_names:
      self.file.write(',')
      if name in points:
        self.file.write(str(points[name]))
      else:
        self.file.write('NaN')
    self.file.write('\n')
    self.file.flush()
  
  def update_average(self, points):
    """Keep track of average value for each stat, adding a new data point."""
    for (name, value) in points.items():
      if name not in self.avg_accum:  # initialize
        self.avg_accum[name] = value
        self.avg_count[name] = 1
      else:
        self.avg_accum[name] += value
        self.avg_count[name] += 1
  
  def average(self):
    """Return the average value of each stat so far (see update_average)."""
    return {name: self.avg_accum[name] / self.avg_count[name] for name in self.avg_accum.keys()}

  def print(self, points=None, prefix=None, as_string=False, line_prefix='', line_suffix=''):
    """Print the current stats averages to the console, or the given values, nicely formatted.
    If prefix is given, only stat names beginning with it will be printed (e.g. "train" or "val")."""
    if points is None:
      points = self.average()
    if prefix:  # remove the prefix from the stat names
      points = {key[len(prefix):].strip('.'): val for (key, val) in points.items() if key.startswith(prefix)}
      line_prefix = line_prefix + prefix + ' '

    # this trick prints floats with 3 significant digits and no sci notation (e.g. 1e-4)
    text = ' '.join(["%s: %s" % (key, float('%.3g' % val)) for (key, val) in points.items()])
    text = line_prefix + text + line_suffix

    if as_string:
      return text
    else:
      print(text)
  
  def tensor(self, name, tensor, **kwargs):
    """Store a tensor to display in the OverBoard GUI. The name must be unique.
    Any keyword arguments will be passed to overboard.tshow."""
    self.visualize('tensor', name, tensor, **kwargs)

  def visualize(self, func, name, *args, **kwargs):
    """Store a visualization to display in the OverBoard GUI.
    The first argument must be a function, with the signature:
      figures = func(name, *args, **kwargs)
    where name is a unique name, and the following arguments/keyword arguments can be anything (e.g. tensors).
    The function can draw any graphics and return them as a list of MatPlotLib Figure objects or PyQtGraph PlotItem objects.
    These will be shown when the experiment is selected in the GUI."""

    if name in self.vis_functions:
      # reuse previously registered visualization function
      info = self.vis_functions[name]
      if info['func'] != func:
        raise ValueError("Attempting to register a different visualization function under a previously used name.")
      source_file = info['source']
    else:
      # it's new
      if not isinstance(name, str): raise ValueError("Visualization name must be a string.")
      if '\t' in name: raise ValueError('Visualization name cannot contain tab characters (\\t).')
      
      if func == 'tensor':
        # built-in functions, like the tensor visualization
        source_file = 'builtin'
      else:
        # user function. copy function source file to freeze changes in visualization code
        source_file = inspect.getsourcefile(func)  # python source for function
        if not source_file or func.__name__ == '<lambda>':
          raise ValueError("Only visualization functions defined at the top-level of a script are supported.")
        shutil.copy(source_file, self.directory + '/' + name + '.py')

      # register visualization function for quick look-up next time this is called
      self.vis_functions[name] = {'func': func, 'source': source_file}
      self.vis_counts[name] = 0

    # pickle the function and arguments
    func_name = func if isinstance(func, str) else func.__name__
    data = {'func': func_name, 'source': source_file, 'args': args, 'kwargs': kwargs}
    save(data, self.directory + '/' + name + '.pth')
    
    # update how many times this visualization was written, to signal a refresh in the GUI
    self.vis_counts[name] += 1
    with open(self.directory + '/visualizations', 'w') as file:
      for (key, value) in self.vis_counts.items():
        file.write('%s\t%i\n' % (key, value))
      
      # changes are detected based on file size (more reliable than file date across OS),
      # so pad with a continually changing number of spaces. when some or all visualizations
      # are updated in an iteration, the number of padding spaces will always be different.
      self.vis_padding = self.vis_padding % (len(self.vis_counts) + 1) + 1
      file.write(' ' * self.vis_padding)
  
  def rate_limit(self, seconds, reset=False):
    """Returns true once every N seconds. Can be used to limit the rate of visualizations."""
    if not reset:
      if time.time() - self.clock > seconds:
        self.clock = time.time()
        return True
      return False
    else:
      self.time = -math.inf
      return False

  def _read_file(self, ignore_empty=False):
    """Read CSV file, validating number of values per line. Empty/missing files can optionally be ignored.
    Returns the header (list of column names) and a list of lines (as strings, for easy re-writing)."""

    try:
      # need to return lines, so read them all at once
      with open(self.directory + '/stats.csv', 'rb') as file:
        lines = file.readlines()

      if len(lines) == 0:  # empty file
        raise OSError()

    except OSError:  # ignore or keep error
      if ignore_empty:
        return ([], None)
      else:
        raise
    
    # read CSV file header (with stat names). they're separated by commas, which can be escaped: \,
    stat_names = re.split(r'(?<!\\),', lines[0].strip())
    if len(stat_names) == 0:
      raise IOError('CSV file has empty header.')

    # if the last line is empty (which marks an experiment as done), take it out now
    if len(lines[-1].strip()) == 0:
      del lines[-1]

    # validate the number of values in each line. they're floats, so no escaping is needed
    for (index, line) in enumerate(lines[1:]):  # skip header line
      if len(line.strip().split(',')) != len(stat_names):
        raise IOError('Line %i in CSV file has a different number of values than the header (file is possibly corrupt).' % (index + 1))

    return (stat_names, lines)

  # note about "with" statement/destructors:
  # this class can be used either with a "with" statement, or without.
  # the first is preferred in Python, but the second is still ok in this case for two reasons:
  # 1) circular references that prevent __del__ from being called shouldn't happen
  # 2) even if they do, append() always flushes the buffer so there's no delay, and the file
  #    will be closed anyway once the process exits.
  def __enter__(self):
    return self
  def __exit__(self, exc_type, exc_value, traceback):
    self._finish_write()
  def __del__(self):
    self._finish_write()

  def _finish_write(self):
    # mark experiment as done by writing an extra line break at the end of the CSV file, and close it
    if not self.file.closed:
      self.file.write('\n')
      self.file.close()
  