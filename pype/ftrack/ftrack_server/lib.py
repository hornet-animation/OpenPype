import os
import requests
try:
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from urlparse import urlparse, parse_qs


def ftrack_events_mongo_settings():
    host = None
    port = None
    username = None
    password = None
    collection = None
    database = None
    auth_db = ""

    if os.environ.get('FTRACK_EVENTS_MONGO_URL'):
        result = urlparse(os.environ['FTRACK_EVENTS_MONGO_URL'])

        host = result.hostname
        try:
            port = result.port
        except ValueError:
            raise RuntimeError("invalid port specified")
        username = result.username
        password = result.password
        try:
            database = result.path.lstrip("/").split("/")[0]
            collection = result.path.lstrip("/").split("/")[1]
        except IndexError:
            if not database:
                raise RuntimeError("missing database name for logging")
        try:
            auth_db = parse_qs(result.query)['authSource'][0]
        except KeyError:
            # no auth db provided, mongo will use the one we are connecting to
            pass
    else:
        host = os.environ.get('FTRACK_EVENTS_MONGO_HOST')
        port = int(os.environ.get('FTRACK_EVENTS_MONGO_PORT', "0"))
        database = os.environ.get('FTRACK_EVENTS_MONGO_DB')
        username = os.environ.get('FTRACK_EVENTS_MONGO_USER')
        password = os.environ.get('FTRACK_EVENTS_MONGO_PASSWORD')
        collection = os.environ.get('FTRACK_EVENTS_MONGO_COL')
        auth_db = os.environ.get('FTRACK_EVENTS_MONGO_AUTH_DB', 'avalon')

    return host, port, database, username, password, collection, auth_db


def get_ftrack_event_mongo_info():
    host, port, database, username, password, collection, auth_db = (
        ftrack_events_mongo_settings()
    )
    user_pass = ""
    if username and password:
        user_pass = "{}:{}@".format(username, password)

    socket_path = "{}:{}".format(host, port)

    dab = ""
    if database:
        dab = "/{}".format(database)

    auth = ""
    if auth_db:
        auth = "?authSource={}".format(auth_db)

    url = "mongodb://{}{}{}{}".format(user_pass, socket_path, dab, auth)

    return url, database, collection


def check_ftrack_url(url, log_errors=True):
    """Checks if Ftrack server is responding"""
    if not url:
        print('ERROR: Ftrack URL is not set!')
        return None

    url = url.strip('/ ')

    if 'http' not in url:
        if url.endswith('ftrackapp.com'):
            url = 'https://' + url
        else:
            url = 'https://{0}.ftrackapp.com'.format(url)
    try:
        result = requests.get(url, allow_redirects=False)
    except requests.exceptions.RequestException:
        if log_errors:
            print('ERROR: Entered Ftrack URL is not accesible!')
        return False

    if (result.status_code != 200 or 'FTRACK_VERSION' not in result.headers):
        if log_errors:
            print('ERROR: Entered Ftrack URL is not accesible!')
        return False

    print('DEBUG: Ftrack server {} is accessible.'.format(url))

    return url


class StorerEventHub(ftrack_api.event.hub.EventHub):
    def __init__(self, *args, **kwargs):
        self.sock = kwargs.pop("sock")
        super(StorerEventHub, self).__init__(*args, **kwargs)

    def _handle_packet(self, code, packet_identifier, path, data):
        """Override `_handle_packet` which extend heartbeat"""
        code_name = self._code_name_mapping[code]
        if code_name == "heartbeat":
            # Reply with heartbeat.
            self.sock.sendall(b"storer")
            return self._send_packet(self._code_name_mapping['heartbeat'])

        elif code_name == "connect":
            event = ftrack_api.event.base.Event(
                topic="pype.storer.started",
                data={},
                source={
                    "id": self.id,
                    "user": {"username": self._api_user}
                }
            )
            self._event_queue.put(event)

        return super(StorerEventHub, self)._handle_packet(
            code, packet_identifier, path, data
        )
