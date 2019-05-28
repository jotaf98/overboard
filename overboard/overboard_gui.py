
import sys, argparse, glob, collections, logging
from functools import partial

#import os
#os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "TRUE"
#os.environ["QT_SCALE_FACTOR"] = "2.5"

import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore

# needed right after QT imports for high-DPI screens
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from .window import Window, set_style
from .experiments import Experiment, check_new_experiments
from .plots import Plots
from .visualizations import Visualizations


def main():
  # parse command line options
  parser = argparse.ArgumentParser()
  parser.add_argument("folder", help="Root folder where experiments are found.")
  parser.add_argument("-plotsize", default=0, type=float, help="Initial size of plots, in pixels.")
  #parser.add_argument("-smoothen", default=0, type=float)
  parser.add_argument("-mpl-dpi", default=100, type=int, help="DPI setting for MatPlotLib plots, may be used if text is too big/small (useful for high-DPI monitors).")
  parser.add_argument("--force-reopen-files", action='store_true', default=False, help="Slower but more reliable refresh method, useful for remote files.")
  parser.add_argument("-refresh-plots", default=1999, type=int, help="Refresh interval for plot updates, in miliseconds.")
  parser.add_argument("-refresh-new", default=3999, type=int, help="Refresh interval for finding new experiments, in miliseconds.")
  parser.add_argument("-refresh-vis", default=2999, type=int, help="Refresh interval for visualizations, in miliseconds.")
  parser.add_argument("--no-vis-snapshot", action='store_true', default=False, help="Visualizations are draw using a snapshot of the visualization function, saved with each experiment. This ensures visualizations from old experiments are maintained. Passing this option disables this behavior, which may be useful for debugging.")
  parser.add_argument("--debug", action='store_true', default=False, help="Does not suppress exceptions during operation, useful for debugging.")
  args = parser.parse_args()

  # create an exception hook, to avoid GUI exiting on uncaught exceptions
  if not args.debug:
    def trap_exceptions(err_type, err_value, traceback):
      logging.exception('Uncaught exception ' + str(err_type), exc_info=err_value)
    sys.excepthook = trap_exceptions
  
  # find experiment files
  logging.info('Finding experiments...')
  files = glob.glob(args.folder + "/**/stats.csv", recursive=True)

  # load the experiments
  logging.info('Loading experiments...')
  experiments = [Experiment(filename, args.folder, args.force_reopen_files) for filename in files]
  logging.info('Done.')

  # create Qt application
  app = QtWidgets.QApplication(sys.argv)
  set_style(app)

  # create window and plots holders
  window = Window(args)
  plots = Plots(window)
  visualizations = Visualizations(window, args.no_vis_snapshot, args.mpl_dpi)

  # create initial plots for all the experiments
  for exp in experiments:
    window.add_experiment(exp, refresh_table=False)
  
  # create timer for updating the plots periodically if needed
  plot_timer = QtCore.QTimer()
  plot_timer.timeout.connect(partial(plots.update_plots, experiments))
  plot_timer.start(args.refresh_plots)
  
  # create timer to check for new experiments
  new_exp_timer = QtCore.QTimer()
  new_exp_timer.timeout.connect(partial(check_new_experiments, experiments, set(files), args.folder, window, args.force_reopen_files))
  new_exp_timer.start(args.refresh_new)
  
  # create timer for updating the current visualizations
  vis_timer = QtCore.QTimer()
  vis_timer.timeout.connect(visualizations.update)
  vis_timer.start(args.refresh_vis)

  window.show()
  
  window.sort_table_by_timestamp(refresh_table=True)

  if window.table.rowCount() > 0:  # select first row if any (after sorting)
    window.table.selectRow(0)
  
  app.exec_()
  #sys.exit(app.exec_())


if __name__ == "__main__":
  main()
