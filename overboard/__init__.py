
# expose logger on import

from .logger import Logger

# expose tshow utility function, unless PyQt5 is not found

try:
  from .visualizations import tshow
except ModuleNotFoundError:
  pass
