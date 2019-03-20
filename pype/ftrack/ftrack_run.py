import os
import json
import threading
import time
import ftrack_api
from app import style
from app.vendor.Qt import QtCore, QtGui, QtWidgets

from pype.ftrack import credentials, login_dialog as login_dialog

from pype.vendor.pynput import mouse, keyboard
from . import FtrackServer

from pype import api as pype


# load data from templates
pype.load_data_from_templates()

log = pype.Logger.getLogger(__name__, "ftrack")


class FtrackRunner:
    def __init__(self, main_parent=None, parent=None):

        self.parent = parent
        self.widget_login = login_dialog.Login_Dialog_ui(self)
        self.widget_timer = StopTimer(self)
        self.action_server = FtrackServer('action')
        self.thread_action_server = None
        self.thread_timer = None
        self.thread_timer_coundown = None

        # self.signal_start_timer.connect(self.timerStart)

        self.bool_logged = False
        self.bool_action_server = False
        self.bool_timer_event = False

    def show_login_widget(self):
        self.widget_login.show()

    def validate(self):
        validation = False
        cred = credentials._get_credentials()
        try:
            if 'username' in cred and 'apiKey' in cred:
                validation = credentials._check_credentials(
                    cred['username'],
                    cred['apiKey']
                )
                if validation is False:
                    self.show_login_widget()
            else:
                self.show_login_widget()

        except Exception as e:
            log.error("We are unable to connect to Ftrack: {0}".format(e))

        validation = credentials._check_credentials()
        if validation is True:
            log.info("Connected to Ftrack successfully")
            self.loginChange()
        else:
            log.warning("Please sign in to Ftrack")
            self.bool_logged = False
            self.set_menu_visibility()

        return validation

    # Necessary - login_dialog works with this method after logging in
    def loginChange(self):
        self.bool_logged = True
        self.set_menu_visibility()
        self.start_action_server()

    def logout(self):
        credentials._clear_credentials()
        self.stop_action_server()

        log.info("Logged out of Ftrack")
        self.bool_logged = False
        self.set_menu_visibility()

    # Actions part
    def start_action_server(self):
        if self.thread_action_server is None:
            self.thread_action_server = threading.Thread(
                target=self.set_action_server
            )
            self.thread_action_server.daemon = True
            self.thread_action_server.start()

        log.info("Ftrack action server launched")
        self.bool_action_server = True
        self.set_menu_visibility()

    def set_action_server(self):
        try:
            self.action_server.run_server()
        except Exception:
            msg = 'Ftrack Action server crashed! Please try to start again.'
            log.error(msg)
            # TODO show message to user
            self.bool_action_server = False
            self.set_menu_visibility()

    def reset_action_server(self):
        self.stop_action_server()
        self.start_action_server()

    def stop_action_server(self):
        try:
            self.action_server.stop_session()
            if self.thread_action_server is not None:
                self.thread_action_server.join()
                self.thread_action_server = None

            log.info("Ftrack action server stopped")
            self.bool_action_server = False
            self.set_menu_visibility()
        except Exception as e:
            log.error("During Killing action server: {0}".format(e))

    # Definition of Tray menu
    def tray_menu(self, parent_menu):
        # Menu for Tray App
        self.menu = QtWidgets.QMenu('Ftrack', parent_menu)
        self.menu.setProperty('submenu', 'on')
        self.menu.setStyleSheet(style.load_stylesheet())

        # Actions - server
        self.smActionS = self.menu.addMenu("Action server")

        self.aRunActionS = QtWidgets.QAction(
            "Run action server", self.smActionS
        )
        self.aResetActionS = QtWidgets.QAction(
            "Reset action server", self.smActionS
        )
        self.aStopActionS = QtWidgets.QAction(
            "Stop action server", self.smActionS
        )

        self.aRunActionS.triggered.connect(self.start_action_server)
        self.aResetActionS.triggered.connect(self.reset_action_server)
        self.aStopActionS.triggered.connect(self.stop_action_server)

        self.smActionS.addAction(self.aRunActionS)
        self.smActionS.addAction(self.aResetActionS)
        self.smActionS.addAction(self.aStopActionS)

        # Actions - basic
        self.aLogin = QtWidgets.QAction("Login", self.menu)
        self.aLogin.triggered.connect(self.validate)
        self.aLogout = QtWidgets.QAction("Logout", self.menu)
        self.aLogout.triggered.connect(self.logout)

        self.menu.addAction(self.aLogin)
        self.menu.addAction(self.aLogout)

        self.bool_logged = False
        self.set_menu_visibility()

        parent_menu.addMenu(self.menu)

        self.validate()

    # Definition of visibility of each menu actions
    def set_menu_visibility(self):

        self.smActionS.menuAction().setVisible(self.bool_logged)
        self.aLogin.setVisible(not self.bool_logged)
        self.aLogout.setVisible(self.bool_logged)

        if self.bool_logged is False:
            if self.bool_timer_event is True:
                self.stop_timer_thread()
            return

        self.aRunActionS.setVisible(not self.bool_action_server)
        self.aResetActionS.setVisible(self.bool_action_server)
        self.aStopActionS.setVisible(self.bool_action_server)

        if self.bool_timer_event is False:
            self.start_timer_thread()

    def start_timer_thread(self):
        try:
            if self.thread_timer is None:
                self.thread_timer = FtrackEventsThread(self)
                self.bool_timer_event = True
                self.thread_timer.signal_timer_started.connect(
                    self.timer_started
                )
                self.thread_timer.signal_timer_stopped.connect(
                    self.timer_stopped
                )
                self.thread_timer.start()
        except Exception:
            pass

    def stop_timer_thread(self):
        try:
            if self.thread_timer is not None:
                self.thread_timer.terminate()
                self.thread_timer.wait()
                self.thread_timer = None

        except Exception as e:
            log.error("During Killing Timer event server: {0}".format(e))


        if self.thread_timer is not None:

        if self.thread_timer is not None:




class FtrackEventsThread(QtCore.QThread):
    # Senders
    signal_timer_started = QtCore.Signal()
    signal_timer_stopped = QtCore.Signal()

    def __init__(self, parent):
        super(FtrackEventsThread, self).__init__()
        cred = credentials._get_credentials()
        self.username = cred['username']
        self.user = None
        self.last_task = None

    def run(self):
        self.timer_session = ftrack_api.Session(auto_connect_event_hub=True)
        self.timer_session.event_hub.subscribe(
            'topic=ftrack.update and source.user.username={}'.format(
                self.username
            ),
            self.event_handler)

        user_query = 'User where username is "{}"'.format(self.username)
        self.user = self.timer_session.query(user_query).one()

        timer_query = 'Timer where user.username is "{}"'.format(self.username)
        timer = self.timer_session.query(timer_query).first()
        if timer is not None:
            self.last_task = timer['context']

        self.timer_session.event_hub.wait()

    def event_handler(self, event):
        try:
            if event['data']['entities'][0]['objectTypeId'] != 'timer':
                return
        except Exception:
            return

        new = event['data']['entities'][0]['changes']['start']['new']
        old = event['data']['entities'][0]['changes']['start']['old']

        if old is None and new is None:
            return

        timer_query = 'Timer where user.username is "{}"'.format(self.username)
        timer = self.timer_session.query(timer_query).first()
        if timer is not None:
            self.last_task = timer['context']

        if old is None:
        elif new is None:
            self.signal_timer_stopped.emit()

    def ftrack_stop_timer(self):
        try:
            self.user.stop_timer()
            self.timer_session.commit()
        except Exception as e:
            log.debug("Timer stop had issues: {}".format(e))

        )
