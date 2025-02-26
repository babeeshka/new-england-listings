# src/new_england_listings/utils/logging_config.py

import os
import logging
import logging.handlers
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import Dict, Any, Optional, List

# Default log directory
DEFAULT_LOG_DIR = "logs"

# Log retention settings
DEFAULT_RETENTION_DAYS = 7
MAX_LOG_SIZE_MB = 10


class LogRotationPolicy:
    """Manages log rotation and cleanup policies."""

    @staticmethod
    def clean_old_logs(log_dir: str, retention_days: int = DEFAULT_RETENTION_DAYS):
        """Remove log files older than retention_days."""
        try:
            log_path = Path(log_dir)
            if not log_path.exists():
                return

            cutoff_time = time.time() - (retention_days * 86400)  # seconds in a day

            for log_file in log_path.glob("*.log*"):  # Include rotated logs
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    print(f"Removed old log file: {log_file}")

        except Exception as e:
            print(f"Error cleaning old logs: {e}")

    @staticmethod
    def limit_run_logs(log_dir: str, app_name: str, max_logs: int = 10):
        """Keep only the most recent N run-specific logs."""
        try:
            log_path = Path(log_dir)
            if not log_path.exists():
                return

            # Find all run-specific logs (pattern: app_name_YYYYMMDD_HHMMSS.log)
            run_logs = list(log_path.glob(f"{app_name}_*.log"))

            # Sort by modification time (newest first)
            run_logs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Delete older logs beyond the limit
            for log_file in run_logs[max_logs:]:
                log_file.unlink()
                print(f"Removed old run log: {log_file}")

        except Exception as e:
            print(f"Error limiting run logs: {e}")

    @staticmethod
    def compress_old_logs(log_dir: str, age_days: int = 3):
        """Compress logs older than age_days to save space."""
        import gzip
        import shutil

        try:
            log_path = Path(log_dir)
            if not log_path.exists():
                return

            cutoff_time = time.time() - (age_days * 86400)

            for log_file in log_path.glob("*.log"):
                # Skip already compressed files
                if log_file.name.endswith(".gz"):
                    continue

                # Compress logs older than cutoff
                if log_file.stat().st_mtime < cutoff_time:
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(f"{log_file}.gz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    log_file.unlink()  # Remove original after compression
                    print(f"Compressed log file: {log_file}")

        except Exception as e:
            print(f"Error compressing logs: {e}")

class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno
        }

        # Add exception info if available
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text",
                           "filename", "funcName", "id", "levelname", "levelno",
                           "lineno", "module", "msecs", "message", "msg",
                           "name", "pathname", "process", "processName",
                           "relativeCreated", "stack_info", "thread", "threadName"]:
                log_data[key] = value

        return json.dumps(log_data)


class ContextFilter(logging.Filter):
    """Add context information to log records."""

    def __init__(self, context=None):
        super().__init__()
        self.context = context or {}

    def filter(self, record):
        # Add context to the record
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


def configure_logging(level=logging.INFO,
                      log_dir: str = DEFAULT_LOG_DIR,
                      app_name: str = "new_england_listings",
                      context: Dict[str, Any] = None,
                      enable_json_logging: bool = False,
                      include_console: bool = True,
                      retention_days: int = DEFAULT_RETENTION_DAYS):
    """
    Configure comprehensive logging with organized outputs.
    
    Args:
        level: Base logging level
        log_dir: Directory for log files
        app_name: Application name for log file prefixes
        context: Additional context to include in all logs
        enable_json_logging: Whether to use JSON format for file logs
        include_console: Whether to include console output
        retention_days: Number of days to keep log files
        
    Returns:
        Logger instance configured for the application
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        logger = logging.getLogger(__name__)
        logger.debug("Logging already configured, skipping initialization")
        return root_logger
    
    # Make sure context always contains run_id
    if context is None:
        context = {}

    # Create timestamp for this run if not provided
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{timestamp}_{os.getpid()}"

    # Ensure run_id is in the context
    if "run_id" not in context:
        context["run_id"] = run_id

    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create and set up log directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Clean up old logs and limit run logs
    LogRotationPolicy.clean_old_logs(log_dir, retention_days)
    LogRotationPolicy.limit_run_logs(log_dir, app_name)
    # Compress logs older than 3 days
    LogRotationPolicy.compress_old_logs(log_dir, age_days=3)

    # Add a context filter
    ctx_filter = ContextFilter(context or {"run_id": run_id})
    logger.addFilter(ctx_filter)

    # Create formatters
    if enable_json_logging:
        file_formatter = JsonFormatter()
    else:
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Main application log with rotation
    app_log_file = log_path / f"{app_name}.log"
    app_handler = logging.handlers.RotatingFileHandler(
        app_log_file,
        maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,  # Convert to bytes
        backupCount=5,
        encoding='utf-8'
    )
    app_handler.setFormatter(file_formatter)
    app_handler.setLevel(level)
    logger.addHandler(app_handler)

    # 2. Error log with rotation (errors only)
    error_log_file = log_path / f"{app_name}_errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setFormatter(file_formatter)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    # 3. Run-specific detailed log (new for each run)
    run_log_file = log_path / f"{app_name}_{timestamp}.log"
    run_handler = logging.FileHandler(
        run_log_file,
        mode='w',  # Overwrite for each run
        encoding='utf-8'
    )
    run_handler.setFormatter(file_formatter)
    # Always capture debug for run-specific logs
    run_handler.setLevel(logging.DEBUG)
    logger.addHandler(run_handler)

    # 4. Notion integration log (filtered to notion operations)
    notion_log_file = log_path / f"{app_name}_notion.log"
    notion_handler = logging.handlers.RotatingFileHandler(
        notion_log_file,
        maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    notion_handler.setFormatter(file_formatter)
    notion_handler.setLevel(logging.DEBUG)
    notion_handler.addFilter(lambda record: 'notion' in record.name.lower())
    logger.addHandler(notion_handler)

    # 5. Console output if requested
    if include_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(level)
        logger.addHandler(console_handler)

    # Configure module-specific levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('WDM').setLevel(logging.INFO)

    # Log startup information
    logger.info(f"Logging initialized for run {run_id}")
    logger.info(f"Log files: {log_dir}/{app_name}*.log")

    return logger


def get_logger(name: str, **kwargs) -> logging.Logger:
    """
    Get a configured logger for a specific module.
    Creates a child logger with the given name.
    
    Args:
        name: Logger name (usually __name__)
        **kwargs: Additional parameters to pass to configure_logging
        
    Returns:
        Configured logger
    """
    if not logging.getLogger().handlers:
        # If root logger isn't configured yet, configure it
        configure_logging(**kwargs)

    logger = logging.getLogger(name)

    # Apply context filter to this logger if it doesn't have one
    has_context_filter = any(isinstance(f, ContextFilter)
                             for f in logger.filters)
    if not has_context_filter:
        # Create timestamp for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{timestamp}_{os.getpid()}"
        ctx_filter = ContextFilter({"run_id": run_id})
        logger.addFilter(ctx_filter)

    return logger


# A function to log extraction results for analysis
def log_extraction_results(listing_url: str, data: Dict[str, Any],
                           success: bool, error: Optional[str] = None):
    """
    Log extraction results in a standardized format for later analysis.
    
    Args:
        listing_url: URL of the listing
        data: Extracted data (can be partial if there was an error)
        success: Whether extraction was completely successful
        error: Error message if there was an error
    """
    logger = logging.getLogger("extraction_results")

    # Create a clean structure for the log
    result = {
        "timestamp": datetime.now().isoformat(),
        "url": listing_url,
        "platform": data.get("platform", "Unknown"),
        "success": success,
        "data": {
            k: v for k, v in data.items()
            if k in ["listing_name", "location", "price", "acreage",
                     "property_type", "platform"]
        }
    }

    if not success and error:
        result["error"] = error

    # Log with appropriate level based on success
    log_level = logging.INFO if success else logging.ERROR

    # Add extraction_result attribute to allow filtering
    logger.log(log_level, json.dumps(result),
               extra={"extraction_result": True})


# Example usage in __init__.py
"""
from .utils.logging_config import configure_logging, get_logger

# Configure at application startup
configure_logging(
    level=logging.INFO,
    log_dir="logs",
    app_name="new_england_listings",
    context={"version": "0.2.0"}
)

# Then in each module:
logger = get_logger(__name__)
"""
