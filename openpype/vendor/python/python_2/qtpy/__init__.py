# -*- coding: utf-8 -*-
#
# Copyright © 2009- The Spyder Development Team
# Copyright © 2014-2015 Colin Duquesnoy
#
# Licensed under the terms of the MIT License
# (see LICENSE.txt for details)

"""
**QtPy** is a shim over the various Python Qt bindings. It is used to write
Qt binding independent libraries or applications.

If one of the APIs has already been imported, then it will be used.

Otherwise, the shim will automatically select the first available API (PyQt5,
PySide2, PyQt4 and finally PySide); in that case, you can force the use of one
specific bindings (e.g. if your application is using one specific bindings and
you need to use library that use QtPy) by setting up the ``QT_API`` environment
variable.

PyQt5
=====

For PyQt5, you don't have to set anything as it will be used automatically::

    >>> from qtpy import QtGui, QtWidgets, QtCore
    >>> print(QtWidgets.QWidget)


PySide2
======

Set the QT_API environment variable to 'pyside2' before importing other
packages::

    >>> import os
    >>> os.environ['QT_API'] = 'pyside2'
    >>> from qtpy import QtGui, QtWidgets, QtCore
    >>> print(QtWidgets.QWidget)

PyQt4
=====

Set the ``QT_API`` environment variable to 'pyqt' before importing any python
package::

    >>> import os
    >>> os.environ['QT_API'] = 'pyqt'
    >>> from qtpy import QtGui, QtWidgets, QtCore
    >>> print(QtWidgets.QWidget)

PySide
======

Set the QT_API environment variable to 'pyside' before importing other
packages::

    >>> import os
    >>> os.environ['QT_API'] = 'pyside'
    >>> from qtpy import QtGui, QtWidgets, QtCore
    >>> print(QtWidgets.QWidget)

"""

from distutils.version import LooseVersion
import os
import platform
import sys
import warnings

# Version of QtPy
from ._version import __version__
from .py3compat import PY2


class PythonQtError(RuntimeError):
    """Error raise if no bindings could be selected."""
    pass


class PythonQtWarning(Warning):
    """Warning if some features are not implemented in a binding."""
    pass


# Qt API environment variable name
QT_API = 'QT_API'

# Names of the expected PyQt5 api
PYQT5_API = ['pyqt5']

# Names of the expected PyQt4 api
PYQT4_API = [
    'pyqt',  # name used in IPython.qt
    'pyqt4'  # pyqode.qt original name
]

# Names of the expected PySide api
PYSIDE_API = ['pyside']

# Names of the expected PySide2 api
PYSIDE2_API = ['pyside2']

# Names of the legacy APIs that we should warn users about
LEGACY_APIS = PYQT4_API + PYSIDE_API

# Minimum fully supported versions of Qt and the bindings
PYQT_VERSION_MIN = '5.9.0'
PYSIDE_VERSION_MIN = '5.12.0'
QT_VERSION_MIN = '5.9.0'

# Detecting if a binding was specified by the user
binding_specified = QT_API in os.environ

# Setting a default value for QT_API
os.environ.setdefault(QT_API, 'pyqt5')

API = os.environ[QT_API].lower()
initial_api = API
assert API in (PYQT5_API + PYQT4_API + PYSIDE_API + PYSIDE2_API)

is_old_pyqt = is_pyqt46 = False
PYQT5 = True
PYQT4 = PYSIDE = PYSIDE2 = False

# When `FORCE_QT_API` is set, we disregard
# any previously imported python bindings.
if not os.environ.get('FORCE_QT_API'):
    if 'PyQt5' in sys.modules:
        API = initial_api if initial_api in PYQT5_API else 'pyqt5'
    elif 'PySide2' in sys.modules:
        API = initial_api if initial_api in PYSIDE2_API else 'pyside2'
    elif 'PyQt4' in sys.modules:
        API = initial_api if initial_api in PYQT4_API else 'pyqt4'
    elif 'PySide' in sys.modules:
        API = initial_api if initial_api in PYSIDE_API else 'pyside'


if API in PYQT5_API:
    try:
        from PyQt5.QtCore import PYQT_VERSION_STR as PYQT_VERSION  # analysis:ignore
        from PyQt5.QtCore import QT_VERSION_STR as QT_VERSION  # analysis:ignore
        PYSIDE_VERSION = None

        if sys.platform == 'darwin':
            macos_version = LooseVersion(platform.mac_ver()[0])
            if macos_version < LooseVersion('10.10'):
                if LooseVersion(QT_VERSION) >= LooseVersion('5.9'):
                    raise PythonQtError("Qt 5.9 or higher only works in "
                                        "macOS 10.10 or higher. Your "
                                        "program will fail in this "
                                        "system.")
            elif macos_version < LooseVersion('10.11'):
                if LooseVersion(QT_VERSION) >= LooseVersion('5.11'):
                    raise PythonQtError("Qt 5.11 or higher only works in "
                                        "macOS 10.11 or higher. Your "
                                        "program will fail in this "
                                        "system.")

            del macos_version
    except ImportError:
        API = os.environ['QT_API'] = 'pyside2'

if API in PYSIDE2_API:
    try:
        from PySide2 import __version__ as PYSIDE_VERSION  # analysis:ignore
        from PySide2.QtCore import __version__ as QT_VERSION  # analysis:ignore

        PYQT_VERSION = None
        PYQT5 = False
        PYSIDE2 = True

        if sys.platform == 'darwin':
            macos_version = LooseVersion(platform.mac_ver()[0])
            if macos_version < LooseVersion('10.11'):
                if LooseVersion(QT_VERSION) >= LooseVersion('5.11'):
                    raise PythonQtError("Qt 5.11 or higher only works in "
                                        "macOS 10.11 or higher. Your "
                                        "program will fail in this "
                                        "system.")

            del macos_version
    except ImportError:
        API = os.environ['QT_API'] = 'pyqt'

if API in PYQT4_API:
    try:
        import sip
        try:
            sip.setapi('QString', 2)
            sip.setapi('QVariant', 2)
            sip.setapi('QDate', 2)
            sip.setapi('QDateTime', 2)
            sip.setapi('QTextStream', 2)
            sip.setapi('QTime', 2)
            sip.setapi('QUrl', 2)
        except (AttributeError, ValueError):
            # PyQt < v4.6
            pass
        try:
            from PyQt4.Qt import PYQT_VERSION_STR as PYQT_VERSION  # analysis:ignore
            from PyQt4.Qt import QT_VERSION_STR as QT_VERSION  # analysis:ignore
        except ImportError:
            # In PyQt4-sip 4.19.13 PYQT_VERSION_STR and QT_VERSION_STR are in PyQt4.QtCore
            from PyQt4.QtCore import PYQT_VERSION_STR as PYQT_VERSION  # analysis:ignore
            from PyQt4.QtCore import QT_VERSION_STR as QT_VERSION  # analysis:ignore
        PYSIDE_VERSION = None
        PYQT5 = False
        PYQT4 = True
    except ImportError:
        API = os.environ['QT_API'] = 'pyside'
    else:
        is_old_pyqt = PYQT_VERSION.startswith(('4.4', '4.5', '4.6', '4.7'))
        is_pyqt46 = PYQT_VERSION.startswith('4.6')

if API in PYSIDE_API:
    try:
        from PySide import __version__ as PYSIDE_VERSION  # analysis:ignore
        from PySide.QtCore import __version__ as QT_VERSION  # analysis:ignore
        PYQT_VERSION = None
        PYQT5 = PYSIDE2 = False
        PYSIDE = True
    except ImportError:
        raise PythonQtError('No Qt bindings could be found')

# If a correct API name is passed to QT_API and it could not be found,
# switches to another and informs through the warning
if API != initial_api and binding_specified:
    warnings.warn('Selected binding "{}" could not be found, '
                  'using "{}"'.format(initial_api, API), RuntimeWarning)

API_NAME = {'pyqt5': 'PyQt5', 'pyqt': 'PyQt4', 'pyqt4': 'PyQt4',
            'pyside': 'PySide', 'pyside2':'PySide2'}[API]

if PYQT4:
    import sip
    try:
        API_NAME += (" (API v{0})".format(sip.getapi('QString')))
    except AttributeError:
        pass

try:
    # QtDataVisualization backward compatibility (QtDataVisualization vs. QtDatavisualization)
    # Only available for Qt5 bindings > 5.9 on Windows
    from . import QtDataVisualization as QtDatavisualization
except (ImportError, PythonQtError):
    pass


def _warn_old_minor_version(name, old_version, min_version):
    warning_message = (
        "{name} version {old_version} is unsupported upstream and "
        "deprecated by QtPy. To ensure your application is still supported "
        "in QtPy 2.0, please make sure it doesn't depend upon {name} versions "
        "older than {min_version}.".format(
            name=name, old_version=old_version, min_version=min_version))
    warnings.warn(warning_message, DeprecationWarning)


# Warn if using a legacy, soon to be unsupported Qt API/binding
if API in LEGACY_APIS or initial_api in LEGACY_APIS:
    warnings.warn(
        "A deprecated Qt4-based binding (PyQt4/PySide) was installed, "
        "imported or set via the 'QT_API' environment variable. "
        "To ensure your application is still supported in QtPy 2.0, "
        "please make sure it doesn't depend upon, import or "
        "set the 'QT_API' env var to 'pyqt', 'pyqt4' or 'pyside'.",
        DeprecationWarning,
    )
else:
    if LooseVersion(QT_VERSION) < LooseVersion(QT_VERSION_MIN):
        _warn_old_minor_version('Qt', QT_VERSION, QT_VERSION_MIN)
    if PYQT_VERSION and (LooseVersion(PYQT_VERSION)
                         < LooseVersion(PYQT_VERSION_MIN)):
        _warn_old_minor_version('PyQt', PYQT_VERSION, PYQT_VERSION_MIN)
    elif PYSIDE_VERSION and (LooseVersion(PYSIDE_VERSION)
                             < LooseVersion(PYSIDE_VERSION_MIN)):
        _warn_old_minor_version('PySide', PYSIDE_VERSION, PYSIDE_VERSION_MIN)
