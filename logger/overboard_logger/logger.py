
import os, math, time, json, inspect, shutil, re, errno
from datetime import datetime, timezone
from numbers import Number

try:
  from torch import save
except ImportError:
  # fallback to regular pickle if pytorch not installed
  import pickle
  def save(obj, path):
    with open(path, 'wb') as file:
      pickle.dump(obj, file)


def get_timestamp(microseconds=True):
  """Current timestamp in UTC timezone (no daylight savings, etc)"""
  ts = datetime.now(timezone.utc)
  if not microseconds: ts = ts.replace(microsecond=0)
  return str(ts)

def get_timestamp_folder(ts=None):
  """Timestamp string with valid directory characters and no timezone"""
  if ts is None: ts = get_timestamp()
  return ts.replace('+00:00', '').replace(' ', '_').replace('.', '_').replace(':', '-')


class Logger:
  """Writes experiment data to a directory."""

  def __init__(self, directory, *, meta=None, unique=True, resume=False, save_timestamp=True, stat_names=None):
    """Initialize log writer for a single experiment.

  directory: str
    Directory where the data will be stored. The main file that is written is "stats.csv", containing one column for each metric.
    Note that if unique is True (the default), a unique subdirectory will be created here.

  meta: dict or argparse.Namespace [empty]
    Meta-data, which can consist of hyper-parameter names and values. Useful for sorting and inspecting experiments. A convenient method is to use the output of the argparse module, so any command-line options are stored as meta-data.

  unique: bool [True]
    If true, a unique folder (using the current timestamp) will be created inside the given directory.

  resume: bool [False]
    Appends new data to an existing log, to resume an experiment.

  save_timestamp: bool [True]
    Saves the current time as a "timestamp" entry in the meta-data.

  stat_names: list of str [automatic]
    Defines the column names (metrics) written to the "stats.csv" file. Otherwise, they are set automatically when Logger.append is called for the first time, and cannot be changed later. This argument is useful if you want to define a larger set of columns than those written in the first call to Logger.append."""

    self.file = None
    if stat_names and not (all(isinstance(name, str) and not ',' in name for name in stat_names)):
      raise ValueError("stat_names must be a list of strings with no commas, if specified.")

    if save_timestamp or unique: timestamp = get_timestamp()
    
    directory = str(directory)  # Python 2 compatibility; should replace str with Path

    if unique:
      if resume: raise ValueError("Cannot create a unique directory and resume logging to it (`resume` and `unique` cannot both be True)")

      # transform timestamp into a valid folder name
      self.directory = directory + '/' + get_timestamp_folder(timestamp)
    else:
      self.directory = directory

    if resume and not os.path.isfile(directory + '/stats.csv'):
      self.resume = False  # log file does not exist, just write from scratch
    else:
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
    self.vis_file_sizes = {}  # visualization file sizes, used to signal changes

    self.clock = -math.inf  # for rate_limit

    # create directory if it doesn't exist, and we're not resuming an existing log.
    # note os.makedirs is an atomic operation of checking existence and creating the
    # folder if needed, to avoid race conditions between different processes.
    while not self.resume:
      try:
        os.makedirs(self.directory, exist_ok=False)
        break  # success

      except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(self.directory):
          # errored because this exact timestamped folder already exists. this should
          # be extremely rare due to the microseconds resolution, but still possible.
          time.sleep(1e-5)  # try again in about 10 microseconds
          timestamp = get_timestamp()
          self.directory = directory + '/' + get_timestamp_folder(timestamp)
        else:
          raise  # some other error, re-raise it

    # get current timestamp as string, including timezone offset
    if save_timestamp:
      self.meta['timestamp'] = timestamp
    
    # write metadata to JSON file
    if self.meta:
      with open(self.directory + '/meta.json', 'w') as file:
        json.dump(self.meta, file, sort_keys=True, indent=4)
    
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
    """Write the given statistics dict to CSV file. If none is given, the average values computed so far are used (see update_average)."""

    if points is None:
      # use computed average, and reset accumulator
      points = self.average()
      self.reset_average()
    else:
      for value in points.values():
        if not isinstance(value, Number):
          raise ValueError('Statistics to log must be native Python numbers.')

    if self.stat_names is None:  # assume the given stats are all there is
      self.stat_names = list(points.keys())
      if not (all(isinstance(name, str) and not ',' in name for name in self.stat_names)):
        raise ValueError("The names of statistics to log must be strings with no commas.")

    else:  # validate them
      for name in points.keys():
        if name not in self.stat_names:
          raise ValueError('Unknown stat name: ' + name + '. Note that no new stats can be added after the first Logger.append call, since the output CSV file has a fixed number of columns. Alternatively, they can be specified in the constructor.')

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
      if not isinstance(value, Number):
        raise ValueError('Statistics to log must be native Python numbers.')
        
      if name not in self.avg_accum:  # initialize
        self.avg_accum[name] = value
        self.avg_count[name] = 1
      else:
        self.avg_accum[name] += value
        self.avg_count[name] += 1
  
  def average(self):
    """Return the average value of each stat so far (see update_average)."""
    return {name: self.avg_accum[name] / self.avg_count[name] for name in self.avg_accum.keys()}

  def reset_average(self):
    """Reset the running average estimates (see update_average)."""
    self.avg_accum = {}
    self.avg_count = {}
    
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
    where name is a unique name, and the following arguments/keyword arguments
    can be anything (e.g. tensors).
    The function can draw any graphics and return them as a list of MatPlotLib
    Figure objects, or PyQtGraph PlotItem/PlotWidget/GLViewWidget objects.
    These will be shown when the experiment is selected in the GUI.
    A dict with the plot titles as strings may also be returned instead."""

    # create folder 'visualizations' to store the files, if it doesn't exist
    vis_dir = self.directory + '/visualizations'
    try:  # compatibility. Python 3.5+ would use pathlib's mkdir with exist_ok=True
      os.makedirs(vis_dir)
    except OSError:
      if not os.path.isdir(vis_dir):
        raise

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
        if not source_file or func.__name__ == '<lambda>' or inspect.ismethod(func):
          raise ValueError("Only visualization functions (not methods) defined at the top-level of a script are supported.")
        shutil.copy(source_file, vis_dir + '/' + name + '.py')

      # register visualization function for quick look-up next time this is called
      self.vis_functions[name] = {'func': func, 'source': source_file}

    # pickle the function and arguments
    func_name = func if isinstance(func, str) else func.__name__
    filename = vis_dir + '/' + name + '.pth'
    data = {'func': func_name, 'source': source_file, 'args': args, 'kwargs': kwargs}
    save(data, filename)

    # changes are detected based on file size (more reliable than file date across OS),
    # so pad with an extra 0-byte in case the file has the exact same size as before
    size = os.path.getsize(filename)
    if name in self.vis_file_sizes and size == self.vis_file_sizes[name]:
      with open(filename, 'ab') as f:  # append the byte
        f.write(bytes([0]))
      size += 1
    self.vis_file_sizes[name] = size

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


__all__ = ['Logger', 'get_timestamp', 'get_timestamp_folder']
