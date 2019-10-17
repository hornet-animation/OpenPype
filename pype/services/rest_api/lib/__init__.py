Splitter = "__splitter__"

from .exceptions import ObjAlreadyExist, AbortException
from .lib import RestMethods, CustomNone, CallbackResult, RequestInfo
from .factory import _RestApiFactory

RestApiFactory = _RestApiFactory()

from .handler import Handler
