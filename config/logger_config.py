"""
Logging configuration with file rotation and configurable levels.
"""
import os
import logging
from datetime import datetime
from pathlib import Path


def setup_logging(log_level: str = None):
  """
  Setup logging with file rotation and configurable levels.

  Args:
    log_level: Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
  """
  # Get log level from environment or parameter
  if log_level is None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

  # Create logs directory if it doesn't exist
  log_dir = Path("logs")
  log_dir.mkdir(exist_ok=True)

  # Generate timestamp for new log file
  timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  current_log_file = log_dir / "app_current.log"
  new_log_file = log_dir / f"app_{timestamp}.log"

  # Backup existing log file if it exists and is not a symlink
  if current_log_file.exists() and not current_log_file.is_symlink():
    # Move current log to timestamped backup
    backup_timestamp = datetime.fromtimestamp(
      current_log_file.stat().st_mtime
    ).strftime("%Y%m%d_%H%M%S")
    backup_file = log_dir / f"app_{backup_timestamp}.log"
    # Only backup if the target doesn't already exist
    if not backup_file.exists():
      current_log_file.rename(backup_file)
      print(f"Previous log backed up to: {backup_file}")
  elif current_log_file.is_symlink():
    # Remove stale symlink
    current_log_file.unlink()

  # Configure root logger
  logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
      # File handler for current log
      logging.FileHandler(new_log_file, mode="w"),
      # Console handler for stdout
      logging.StreamHandler(),
    ],
  )

  # Create symlink to current log for easy access
  try:
    if current_log_file.exists() or current_log_file.is_symlink():
      current_log_file.unlink()
    current_log_file.symlink_to(new_log_file.name)
  except Exception as e:
    # If symlink fails, just continue - not critical
    print(f"Warning: Could not create symlink: {e}")

  logger = logging.getLogger(__name__)
  logger.info(f"Logging initialized at level: {log_level}")
  logger.info(f"Log file: {new_log_file}")

  # Suppress noisy libraries
  logging.getLogger("werkzeug").setLevel(logging.WARNING)

  return logger
