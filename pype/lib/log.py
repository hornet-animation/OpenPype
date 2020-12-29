"""
Logging to console and to mongo. For mongo logging, you need to set either
``PYPE_LOG_MONGO_URL`` to something like:

.. example::
   mongo://user:password@hostname:port/database/collection?authSource=avalon

or set ``PYPE_LOG_MONGO_HOST`` and other variables.
See :func:`_mongo_settings`

Best place for it is in ``repos/pype-config/environments/global.json``
"""


import datetime
import getpass
import logging
import os
import platform
import socket
import sys
import time
import traceback

from . import Terminal
from .mongo import (
    MongoEnvNotSet,
    decompose_url,
    compose_url,
    get_default_components
)

try:
    import log4mongo
    from log4mongo.handlers import MongoHandler
except ImportError:
def _log_mongo_components():
    mongo_url = os.environ.get("PYPE_LOG_MONGO_URL")
    if mongo_url is not None:
        components = decompose_url(mongo_url)
    else:
        components = get_default_components()
    return components


def _bootstrap_mongo_log(components=None):
    """
    This will check if database and collection for logging exist on server.
    """
    import pymongo

    if components is None:
        components = _log_mongo_components()

    if not components["host"]:
        # fail silently
        return

    timeout = int(os.environ.get("AVALON_TIMEOUT", 1000))
    kwargs = {
        "host": compose_url(**components),
        "serverSelectionTimeoutMS": timeout
    }

    port = components.get("port")
    if port is not None:
        kwargs["port"] = int(port)
    client = pymongo.MongoClient(**kwargs)
    logdb = client[LOG_DATABASE_NAME]

    collist = logdb.list_collection_names()
    if LOG_COLLECTION_NAME not in collist:
        logdb.create_collection(
            LOG_COLLECTION_NAME, capped=True, max=5000, size=1073741824
        )
    return logdb
# Check for `unicode` in builtins
USE_UNICODE = hasattr(__builtins__, "unicode")


class PypeStreamHandler(logging.StreamHandler):
    """ StreamHandler class designed to handle utf errors in python 2.x hosts.

    """

    def __init__(self, stream=None):
        super(PypeStreamHandler, self).__init__(stream)
        self.enabled = True

    def enable(self):
        """ Enable StreamHandler

            Used to silence output
        """
        self.enabled = True
        pass

    def disable(self):
        """ Disable StreamHandler

            Make StreamHandler output again
        """
        self.enabled = False

    def emit(self, record):
        if not self.enable:
            return
        try:
            msg = self.format(record)
            msg = Terminal.log(msg)
            stream = self.stream
            fs = "%s\n"
            # if no unicode support...
            if not USE_UNICODE:
                stream.write(fs % msg)
            else:
                try:
                    if (isinstance(msg, unicode) and  # noqa: F821
                            getattr(stream, 'encoding', None)):
                        ufs = u'%s\n'
                        try:
                            stream.write(ufs % msg)
                        except UnicodeEncodeError:
                            stream.write((ufs % msg).encode(stream.encoding))
                    else:
                        if (getattr(stream, 'encoding', 'utf-8')):
                            ufs = u'%s\n'
                            stream.write(ufs % unicode(msg))  # noqa: F821
                        else:
                            stream.write(fs % msg)
                except UnicodeError:
                    stream.write(fs % msg.encode("UTF-8"))
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            print(repr(record))
            self.handleError(record)


class PypeFormatter(logging.Formatter):

    DFT = '%(levelname)s >>> { %(name)s }: [ %(message)s ]'
    default_formatter = logging.Formatter(DFT)

    def __init__(self, formats):
        super(PypeFormatter, self).__init__()
        self.formatters = {}
        for loglevel in formats:
            self.formatters[loglevel] = logging.Formatter(formats[loglevel])

    def format(self, record):
        formatter = self.formatters.get(record.levelno, self.default_formatter)

        _exc_info = record.exc_info
        record.exc_info = None

        out = formatter.format(record)
        record.exc_info = _exc_info

        if record.exc_info is not None:
            line_len = len(str(record.exc_info[1]))
            out = "{}\n{}\n{}\n{}\n{}".format(
                out,
                line_len * "=",
                str(record.exc_info[1]),
                line_len * "=",
                self.formatException(record.exc_info)
            )
        return out


class PypeMongoFormatter(logging.Formatter):

    DEFAULT_PROPERTIES = logging.LogRecord(
        '', '', '', '', '', '', '', '').__dict__.keys()

    def format(self, record):
        """Formats LogRecord into python dictionary."""
        # Standard document
        document = {
            'timestamp': datetime.datetime.now(),
            'level': record.levelname,
            'thread': record.thread,
            'threadName': record.threadName,
            'message': record.getMessage(),
            'loggerName': record.name,
            'fileName': record.pathname,
            'module': record.module,
            'method': record.funcName,
            'lineNumber': record.lineno
        }
        # Standard document decorated with exception info
        if record.exc_info is not None:
            document['exception'] = {
                'message': str(record.exc_info[1]),
                'code': 0,
                'stackTrace': self.formatException(record.exc_info)
            }

        # Standard document decorated with extra contextual information
        if len(self.DEFAULT_PROPERTIES) != len(record.__dict__):
            contextual_extra = set(record.__dict__).difference(
                set(self.DEFAULT_PROPERTIES))
            if contextual_extra:
                for key in contextual_extra:
                    document[key] = record.__dict__[key]
        return document


class PypeLogger:
    DFT = '%(levelname)s >>> { %(name)s }: [ %(message)s ] '
    DBG = "  - { %(name)s }: [ %(message)s ] "
    INF = ">>> [ %(message)s ] "
    WRN = "*** WRN: >>> { %(name)s }: [ %(message)s ] "
    ERR = "!!! ERR: %(asctime)s >>> { %(name)s }: [ %(message)s ] "
    CRI = "!!! CRI: %(asctime)s >>> { %(name)s }: [ %(message)s ] "

    FORMAT_FILE = {
        logging.INFO: INF,
        logging.DEBUG: DBG,
        logging.WARNING: WRN,
        logging.ERROR: ERR,
        logging.CRITICAL: CRI,
    }

    # Is static class initialized
    bootstraped = False
    initialized = False
    _init_lock = threading.Lock()

    # Defines if mongo logging should be used
    use_mongo_logging = None
    mongo_process_id = None

    # Information about mongo url
    log_mongo_url = None
    log_mongo_url_components = None
    log_database_name = None
    log_collection_name = None

    # PYPE_DEBUG
    pype_debug = 0

    # Data same for all record documents
    process_data = None
    # Cached process name or ability to set different process name
    _process_name = None






    def _get_mongo_handler(self):
        components = _log_mongo_components()
        # Check existence of mongo connection before creating Mongo handler
        if log4mongo.handlers._connection is None:
            _bootstrap_mongo_log(components)

        kwargs = {
            "host": compose_url(**components),
            "database_name": LOG_DATABASE_NAME,
            "collection": LOG_COLLECTION_NAME,
            "username": components["username"],
            "password": components["password"],
            "capped": True,
            "formatter": PypeMongoFormatter()
        }
        if components["port"] is not None:
            kwargs["port"] = int(components["port"])
        if components["auth_db"]:
            kwargs["authentication_db"] = components["auth_db"]

        return MongoHandler(**kwargs)

    def _get_console_handler(self):

        formatter = PypeFormatter(self.FORMAT_FILE)
        console_handler = PypeStreamHandler()

        console_handler.set_name("PypeStreamHandler")
        console_handler.setFormatter(formatter)
        return console_handler

    def get_logger(self, name=None, host=None):
        logger = logging.getLogger(name or '__main__')

        if self.PYPE_DEBUG > 1:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        global _mongo_logging
        add_mongo_handler = _mongo_logging
        add_console_handler = True

        for handler in logger.handlers:
            if isinstance(handler, MongoHandler):
                add_mongo_handler = False
            elif isinstance(handler, PypeStreamHandler):
                add_console_handler = False

        if add_console_handler:
            logger.addHandler(self._get_console_handler())

        if add_mongo_handler:
            try:
                logger.addHandler(self._get_mongo_handler())

            except MongoEnvNotSet:
                # Skip if mongo environments are not set yet
                _mongo_logging = False

            except Exception:
                lines = traceback.format_exception(*sys.exc_info())
                for line in lines:
                    if line.endswith("\n"):
                        line = line[:-1]
                    Terminal.echo(line)
                _mongo_logging = False

        # Do not propagate logs to root logger
        logger.propagate = False

        return logger


def timeit(method):
    """Print time in function.

    For debugging.

    """
    log = logging.getLogger()

    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            log.debug('%r  %2.2f ms' % (method.__name__, (te - ts) * 1000))
            print('%r  %2.2f ms' % (method.__name__, (te - ts) * 1000))
        return result
    return timed
