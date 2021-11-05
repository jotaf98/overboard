
import sys, argparse, logging

#import os
#os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "TRUE"
#os.environ["QT_SCALE_FACTOR"] = "2.5"

import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtCore as QtCore

# needed right after QT imports for high-DPI screens
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from .window import Window, set_style
from .experiments import Experiments
from .plots import Plots
from .visualizations import Visualizations


def main():
  # parse command line options
  parser = argparse.ArgumentParser()
  parser.add_argument("folder", help="Root folder where experiments are found.")
  #parser.add_argument("-smoothen", default=0, type=float)
  parser.add_argument("-mpl-dpi", default=100, type=int, help="DPI setting for MatPlotLib plots, may be used if text is too big/small (useful for high-DPI monitors).")
  parser.add_argument("--dashes", action='store_true', default=False, help="Cycle through dashes (line) style instead of colors, to distinguish plot lines.")
  parser.add_argument("--force-reopen-files", action='store_true', default=False, help="Slower but more reliable refresh method, useful for remote files.")
  parser.add_argument("-refresh-plots", default=3, type=int, help="Refresh interval for plot updates, in seconds.")
  parser.add_argument("-refresh-new", default=11, type=int, help="Refresh interval for finding new experiments, in seconds.")
  parser.add_argument("-refresh-vis", default=10, type=int, help="Refresh interval for visualizations, in seconds.")
  #parser.add_argument("--no-vis-snapshot", action='store_true', default=False, help="Visualizations are draw using a snapshot of the visualization function, saved with each experiment. This ensures visualizations from old experiments are maintained. Passing this option disables this behavior, which may be useful for debugging.")
  parser.add_argument("-max-hidden-history", default=1000, type=int, help="Maximum number of hidden experiments to remember.")
  parser.add_argument("--debug", action='store_true', default=False, help="Does not suppress exceptions during operation, useful for debugging.")
  parser.add_argument("-loader-log", default='warning', choices=['debug', 'info', 'warning', 'error'], help="Logging verbosity level for experiments loader, from most verbose to least verbose.")
  parser.add_argument("-vis-log", default='warning', choices=['debug', 'info', 'warning', 'error'], help="Logging verbosity level for visualizations, from most verbose to least verbose.")
  parser.add_argument("-plots-log", default='warning', choices=['debug', 'info', 'warning', 'error'], help="Logging verbosity level for plots, from most verbose to least verbose.")
  parser.add_argument("--clear-settings", action='store_true', default=False, help="Clears all stored settings about the GUI state.")
  args = parser.parse_args()


  logging.basicConfig(format="[%(levelname)s] %(message)s")

  # since SSH is a common use case, warn in case fs.sshfs is not installed
  if args.folder.lower().startswith('ssh://'):
    try:
      import fs.sshfs
    except ModuleNotFoundError:
      raise ModuleNotFoundError("To load remote experiments over SSH, the fs.sshfs module must be installed.")


  # create exception and warning hooks, to avoid GUI exiting on uncaught exceptions and suppress warnings
  if not args.debug:
    def trap_exceptions(err_type, err_value, traceback):
      logging.exception('Uncaught exception ' + str(err_type), exc_info=err_value)
    def ignore_qt_warnings(msg_type, msg_log_context, msg_string):
      pass
    sys.excepthook = trap_exceptions
    QtCore.qInstallMessageHandler(ignore_qt_warnings)
  

  # create Qt application
  app = QtWidgets.QApplication(sys.argv)
  set_style(app)

  # create window, experiments and plots holders
  window = Window(window_title='OverBoard - ' + args.folder,
    max_hidden_history=args.max_hidden_history, clear_settings=args.clear_settings)
  
  experiments = Experiments(args.folder, window, args.force_reopen_files,
    args.refresh_plots, args.refresh_new, log_level=args.loader_log)

  plots = Plots(window, args.dashes, log_level=args.plots_log)

  visualizations = Visualizations(window, args.mpl_dpi, args.refresh_vis,
    log_level=args.vis_log)

  window.experiments = experiments

  window.show()
  
  app.exec_()
  #sys.exit(app.exec_())


if __name__ == "__main__":
  main()
