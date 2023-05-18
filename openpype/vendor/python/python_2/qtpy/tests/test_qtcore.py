from __future__ import absolute_import

import pytest
from qtpy import PYQT5, PYSIDE2, QtCore

"""Test QtCore."""


def test_qtmsghandler():
    """Test qtpy.QtMsgHandler"""
    assert QtCore.qInstallMessageHandler is not None


@pytest.mark.skipif(not (PYQT5 or PYSIDE2),
                    reason="Targeted to PyQt5 or PySide2")
def test_DateTime_toPython():
    """Test QDateTime.toPython"""
    assert QtCore.QDateTime.toPython is not None


@pytest.mark.skipif(PYSIDE2,
                    reason="Doesn't seem to be present on PySide2")
def test_QtCore_SignalInstance():
    class ClassWithSignal(QtCore.QObject):
        signal = QtCore.Signal()

    instance = ClassWithSignal()

    assert isinstance(instance.signal, QtCore.SignalInstance)
