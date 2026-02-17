"""Utility module for configuring and managing application-wide logging.

Provides a centralized logging configuration that outputs to both stdout and a
rotating log file under the workspace ``logs/`` directory.
"""

from __future__ import annotations

import logging
import os
import sys


class LoggingUtils:
    """Centralized logging utility for the Security Analysis Tool.

    Manages logger creation with consistent formatting across the application.
    Loggers are configured with both a console (stdout) handler and a file
    handler that writes to ``<base_path>/logs/sat.log``.

    Attributes:
        loglevel: The default logging level applied to new loggers.
            Defaults to ``logging.INFO``.
    """

    loglevel: int = logging.INFO

    @classmethod
    def set_logger_level(cls, loglevel_v: int) -> None:
        """Set the default logging level for subsequently created loggers.

        Args:
            loglevel_v: A logging level constant (e.g. ``logging.DEBUG``,
                ``logging.WARNING``). Must be called before ``get_logger``
                for the level to take effect on new loggers.
        """
        cls.loglevel = loglevel_v

    # DEBUG < INFO < WARNING < ERROR < CRITICAL
    @classmethod
    def get_logger(cls, modname: str = "_profiler_") -> logging.Logger:
        """Create or retrieve a logger with console and file handlers.

        If the logger for *modname* has no handlers yet, a ``StreamHandler``
        (stdout) and a ``FileHandler`` (``<base_path>/logs/sat.log``) are
        attached with the format
        ``%(asctime)s - %(name)s - %(levelname)s - %(message)s``.

        Args:
            modname: Name for the logger, typically the calling module's name.
                Defaults to ``"_profiler_"``.

        Returns:
            logging.Logger: Configured logger instance.
        """
        log_base_dir = f"{cls.base_path()}/logs"

        if not os.path.isdir(log_base_dir):
            os.makedirs(log_base_dir)

        logpath = f"{log_base_dir}/sat.log"

        # Create a custom logger
        logger = logging.getLogger(modname)

        if logger.handlers == []:
            # Create handlers
            c_handler = logging.StreamHandler(sys.stdout)
            f_handler = logging.FileHandler(logpath)
            # Create formatters and add it to handlers
            c_format = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            f_format = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            c_handler.setFormatter(c_format)
            f_handler.setFormatter(f_format)

            # Add handlers to the logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)
        logger.setLevel(cls.loglevel)
        return logger

    # DEBUG < INFO < WARNING < ERROR < CRITICAL
    @staticmethod
    def get_log_level(vloglevel: str) -> int:
        """Convert a log-level name string to its ``logging`` module constant.

        Looks up *vloglevel* as a module-level attribute on ``logging``
        (e.g. ``logging.DEBUG``), falling back to ``logging.INFO`` when the
        name does not correspond to a known level constant.

        Args:
            vloglevel: Case-insensitive level name (e.g. ``"DEBUG"``,
                ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``).

        Returns:
            int: The corresponding ``logging`` level constant, or
            ``logging.INFO`` if *vloglevel* does not match a known level.
        """
        return getattr(logging, vloglevel.upper(), logging.INFO)

    @staticmethod
    def base_path() -> str:
        """Resolve the workspace base path for log file storage.

        Derives the path by stripping everything after ``/notebooks`` in the
        current working directory and ensuring a ``/Workspace`` prefix. Falls
        back to ``~/temp`` if the working directory does not contain
        ``/notebooks``.

        Returns:
            str: The resolved workspace base path.
        """
        path = os.getcwd()
        ind = path.find("/notebooks")
        if ind == -1:
            return "~/temp"
        path = path[:ind]
        if path.startswith("/Workspace"):
            return f"{path}"
        return f"/Workspace{path}"
