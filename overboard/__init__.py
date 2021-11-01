
"""Pure Python dashboard for monitoring deep learning experiments."""

# expose tshow utility function
from .visualizations import tshow

__all__ = ['tshow']

# expose logger on import
try:
  from overboard_logger import Logger, get_timestamp, get_timestamp_folder
  __all__.extend(['Logger', 'get_timestamp', 'get_timestamp_folder'])
except ImportError:
  pass
