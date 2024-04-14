import logging
import sys

from asyncio_relay_server.config import Config


def gen_log_config(config: Config):
    server_log_level = "DEBUG" if config.DEBUG else "INFO"
    server_log_formatter = "diagnostic" if config.DEBUG else "generic"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {
            "relay_server.root": {"level": server_log_level, "handlers": ["console"]},
            "relay_server.error": {
                "level": server_log_level,
                "handlers": ["error_console"],
                "propagate": True,
                "qualname": "relay_server.error",
            },
            "relay_server.access": {
                "level": server_log_level,
                "handlers": ["access_console"],
                "propagate": True,
                "qualname": "relay_server.access",
            },
            "relay_server.lfile": { "level": server_log_level, "handlers": ["lfile"]},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": server_log_formatter,
                "stream": sys.stdout,
            },
            "error_console": {
                "class": "logging.StreamHandler",
                "formatter": server_log_formatter,
                "stream": sys.stderr,
            },
            "access_console": {
                "class": "logging.StreamHandler",
                "formatter": server_log_formatter,
                "stream": sys.stdout,
            },
            "lfile": {
                "class": "logging.FileHandler",
                "formatter": "lfile",
                "filename": "a.log",
            },
        },
        "formatters": {
            "lfile": {
                "format": "%(asctime)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
                "class": "logging.Formatter",
            },
            "generic": {
                "format": "%(asctime)s | %(levelname)-8s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
                "class": "logging.Formatter",
            },
            "diagnostic": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d \n└─%(message)s\n",
                "datefmt": "%Y-%m-%d %H:%M:%S %z",
                "class": "logging.Formatter",
            },
        },
    }


logger = logging.getLogger("relay_server.root")

error_logger = logging.getLogger("relay_server.error")

access_logger = logging.getLogger("relay_server.access")
lfile_logger = logging.getLogger("relay_server.lfile")
