
from PyQt5.QtCore import QThread, QObject, pyqtSignal, pyqtSlot

import json, re, logging
from time import time
from datetime import datetime

from fs import open_fs, path as fs_path  # pyfilesystem
from fs.errors import FSError

logger = logging.getLogger('overboard.exp')


class Experiments():
  """Stores all Experiment objects, in the name-experiment mapping exps.
  Also manages a thread to find new experiments asynchronously."""
  def __init__(self, base_folder, window, force_reopen_files, poll_time, crawler_poll_time, log_level):
    # set logging messages threshold level
    logger.setLevel(getattr(logging, log_level.upper(), None))

    self.exps = {}
    self.base_folder = base_folder
    self.window = window
    self.force_reopen_files = force_reopen_files
    self.poll_time = poll_time
    
    # create crawler object and thread
    self.crawler = ExperimentsCrawler(base_folder=base_folder, crawler_poll_time=crawler_poll_time)
    self.thread = QThread()

    # connect ExperimentsCrawler's signal to Experiments method slot, to return new experiments
    self.crawler.experiments_ready.connect(self.on_experiments_ready)
    self.crawler.moveToThread(self.thread)  # move the crawler object to the thread
    self.thread.started.connect(self.crawler.start_crawling)  # connect thread started signal to crawler slot
    self.thread.start()  # start thread

  def on_experiments_ready(self, filepaths):
    """The crawler found new files, initialize corresponding Experiment objects"""
    for filepath in filepaths:
      exp = Experiment(filepath, self.base_folder, self.force_reopen_files, self.poll_time, self.window)
      self.exps[exp.name] = exp


class ExperimentsCrawler(QObject):
  """Searches for new experiments asynchronously, on a separate thread"""

  # signal to return new experiments to the Experiments object, on the main thread
  experiments_ready = pyqtSignal(list)

  def __init__(self, base_folder, crawler_poll_time):
    super().__init__()
    self.base_folder = base_folder
    self.crawler_poll_time = crawler_poll_time
    self.fs = open_fs(base_folder)

  @pyqtSlot()
  def start_crawling(self):
    """Check for new experiments.
    Since the main use case involves remote files mounted with SSHFS/NFS, polling is
    the only viable mechanism to detect changes. This is further argued here:
    https://github.com/samuelcolvin/watchgod#why-no-inotify--kqueue--fsevent--winapi-support"""

    known_files = set()
    while True:
      # find experiment files, and see if there are any new ones
      new_files = []
      last_time = time()
      for filename in self.fs.walk.files(filter=['stats.csv']):
        if filename not in known_files:  # it's new
          new_files.append(filename)

          # if it's taking a while, show an intermediate result
          if time() - last_time > 0.5:  # elapsed time in seconds
            # return the new files as a signal to the main thread
            if len(new_files) > 0:
              self.experiments_ready.emit(new_files)
              known_files.update(set(new_files))
              new_files.clear()
            last_time = time()

      # return the new files as a signal to the main thread
      if len(new_files) > 0:
        self.experiments_ready.emit(new_files)
        known_files.update(set(new_files))
        new_files.clear()

      # wait some time before looking again
      QThread.sleep(self.crawler_poll_time)



class Experiment():
  """Stores data for a single experiment, and manages a thread to read new data asynchronously"""
  def __init__(self, filepath, base_folder, force_reopen_files, poll_time, window):
    (rel_path, _, filename) = filepath.rpartition('/')  # extract '/stats.csv' from path; forward slash guaranteed by pyfilesystem
    self.name = rel_path[1:]  # the experiment name is the directory path, relative to the base folder
    self.filename = filename
    self.directory = fs_path.combine(base_folder, rel_path)

    logger.debug(f"Initializing thread to load {self.name}")

    self.meta = {}
    self.metrics = []  # names of metrics
    self.data = []  # data for each metric (one list per metric)
    self.done = False  # true after reading and the experiment is done writing too

    # start hidden if the user hid it the last time (this is a persistent setting)
    if self.directory in window.hidden_exp_paths:
      self.visible = False
      del window.hidden_exp_paths[self.directory]
    else:
      self.visible = True

    self.is_selected = False
    self.is_filtered = False
    self.style_idx = None  # style index, for when it's assigned (see Plots.assign_exp_style)

    # register this experiment with the main window
    self.window = window
    self.table_row = None  # used internally by the window
    window.on_exp_init(self)

    # create reader object and thread
    self.reader = ExperimentReader(filename=filename, directory=self.directory, force_reopen_files=force_reopen_files, poll_time=poll_time, name=self.name)
    self.thread = QThread()

    # connect ExperimentReader's signals to Experiment method slots, to return data
    self.reader.meta_ready.connect(self.on_meta_ready)
    self.reader.header_ready.connect(self.on_header_ready)
    self.reader.data_ready.connect(self.on_data_ready)
    self.reader.done.connect(self.on_done)

    self.reader.moveToThread(self.thread)  # move the reader object to the thread

    self.reader.done.connect(self.thread.quit)  # connect reader done signal to terminate thread slot
    self.thread.started.connect(self.reader.start_reading)  # connect thread started signal to reader slot

    self.thread.start()  # start thread


  # receive signals from thread, and store associated data
  def on_meta_ready(self, meta):  
    self.meta = meta
    self.window.on_exp_meta_ready(self)

  def on_header_ready(self, header):  
    self.metrics = header
    self.data = [[] for _ in header]  # initialize each column of data
    self.window.on_exp_header_ready(self)

  def on_data_ready(self, data):  
    assert(len(self.metrics) > 0)  # sanity check, on_header_ready should have been called before

    # append new values to each existing column, and update plots
    for (column, new_values) in zip(self.data, data):
      column.extend(new_values)

    self.window.plots.add(self)

  def on_done(self):
    # mark experiment as done. this signal is also sent to the QThread's quit slot, so it ends.
    self.done = True

  def is_visible(self):
    # helper for whether it's visible and not filtered out
    return (self.visible and not self.is_filtered)



class ExperimentReader(QObject):
  """Reads data from an experiment asynchronously, on a separate thread"""

  # signals to return data to the Experiment object, on the main thread
  meta_ready = pyqtSignal(dict)
  header_ready = pyqtSignal(list)
  data_ready = pyqtSignal(list)
  done = pyqtSignal()

  def __init__(self, filename, directory, force_reopen_files, poll_time, name):
    super().__init__()
    self.name = name
    self.filename = filename
    self.directory = directory
    self.force_reopen_files = force_reopen_files
    self.poll_time = poll_time
    self.num_columns = None
    self.num_rows = 0

    self.fs = open_fs(directory)

  @pyqtSlot()
  def start_reading(self):
    """Do all the reading asynchronously from the main thread"""

    # read JSON file with metadata (including timestamp), if it exists
    meta = {}
    try:
      meta = json.loads(self.fs.readtext('meta.json'))
    except (IOError, FSError):  # no meta data, not critical
      self.meta_ready.emit({})

    # try interpreting string values in meta-data as an ISO date
    for (key, value) in meta.items():
      if isinstance(value, str):
        try:  # try interpreting as an ISO date
          meta[key] = datetime.fromisoformat(value)
        except (ValueError, AttributeError):
          pass  # otherwise, keep as a string

    # send the meta-data to the main thread
    self.meta_ready.emit(meta)

    # read data
    logger.debug(f"Finished reading experiment meta-data; now reading CSV for {self.name}")
    try:
      if self.force_reopen_files:
        self.read_data_slow()
      else:
        self.read_data_fast()
    except (IOError, FSError, ValueError):
      logger.exception(f"Error reading {self.directory}/{self.filename}")
  
  def read_data_fast(self):
    """Polls the file for new data by attempting another read, keeping the file handle open (fast)"""
    done = False
    with self.fs.open(self.filename) as file:
      (done, line_start) = self.read_lines(file)
      while not done:
        # try to read new data after a while. need to restore read position when there's
        # no new line to read, to cope with incomplete lines (while they're being written)
        QThread.sleep(self.poll_time)
        file.seek(line_start)
        (done, line_start) = self.read_lines(file)

  def read_data_slow(self):
    """Polls the file for new data by tracking size changes, and reopening it to read each time (slower)"""
    old_size = 0
    line_start = None
    while True:
      info = self.fs.getinfo(self.filename, namespaces=['details'])

      if info.size != old_size:
        old_size = info.size
        with self.fs.open(self.filename, 'r') as file:
          # get new data from the file, picking up where we left off. don't use file size, depends on OS
          if line_start is not None:
            file.seek(line_start)

          (done, line_start) = self.read_lines(file)
          if done: return

      QThread.sleep(self.poll_time)

  def read_lines(self, file):
    """Reads as many lines as possible from an open CSV file, emitting appropriate signals with the data and status.
    Returns whether the experiment is finished (boolean), and the position to re-start reading from."""
    (rows, done) = ([], False)
    logger.debug(f"Starting to read lines for {self.name}")

    while True:
      # try to read a new line. need to restore read position when there's no new
      # line to read, to cope with incomplete lines (while they're being written)
      line_start = file.tell()
      line = file.readline()
      
      # an empty line, terminated by a line break (\n, \r or \r\n), marks the end
      # of the experiment; no further reading necessary
      if 1 <= len(line) <= 2 and (char in ('\n', '\r') for char in line):
        done = True
        logger.debug(f"End of experiment {self.name}")
        break

      # reached the end of file, but there's no line break; writing is not complete
      if len(line) == 0 or line[-1] not in ('\n', '\r'):
        logger.debug(f"Incomplete line for {self.name}")
        break

      if self.num_columns is None:
        # read CSV file header (with stat names). they're separated by commas, which can be escaped: \,
        headers = re.split(r'(?<!\\),', line.strip())
        
        if len(headers) == 0: raise IOError('CSV file has too few headers.')

        headers.insert(0, 'iteration')  # insert a default column, the row number
        self.num_columns = len(headers)

        # send a signal with the headers
        self.header_ready.emit(headers)

        logger.debug(f"Read headers for {self.name}: {headers}")
      else:
        # interpret line of stat values
        #row = [float(v) for v in line.split(',')]
        row = [self.num_rows]  # start with iteration count (row number)
        for value in line.split(','):
          try:  # first try converting to float
            value = float(value)
          except ValueError:
            try:  # try interpreting as an ISO date
              value = datetime.fromisoformat(value)
            except (ValueError, AttributeError):
              pass  # otherwise, keep as a string
          row.append(value)

        if len(row) != self.num_columns:
          print(self.num_columns, row)
          raise IOError('A CSV line has an incorrect number of values (compared to the header).')
        
        rows.append(row)
        self.num_rows += 1
        logger.debug(f"Read row {self.num_rows} for {self.name}")

    # send signals that data is ready or the experiment is done, if needed.
    # also return position to seek to, to re-read any incomplete line.
    if len(rows) > 0:  # note we transpose the data (columns instead of rows)
      columns = list(zip(*rows))
      self.data_ready.emit(columns)
    if done:
      self.done.emit()
    return (done, line_start)

