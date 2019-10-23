import os
import sys
import datetime
import signal
import socket
import pymongo

from ftrack_server import FtrackServer
from pype.ftrack.lib.custom_db_connector import DbConnector
from session_storer import StorerSession
from pypeapp import Logger

log = Logger().get_logger("Event storer")


dbcon = DbConnector(
    mongo_url=os.environ["AVALON_MONGO"],
    database_name="pype"
)
table_name = "ftrack_events"

# ignore_topics = ["ftrack.meta.connected"]
ignore_topics = []

def install_db():
    try:
        dbcon.install()
        dbcon.create_table(table_name, capped=False)
        dbcon.active_table = table_name
    except pymongo.errors.AutoReconnect:
        log.error("Mongo server \"{}\" is not responding, exiting.".format(
            os.environ["AVALON_MONGO"]
        ))
        sys.exit(0)

def launch(event):
    if event.get("topic") in ignore_topics:
        return

    event_data = event._data
    event_id = event["id"]

    event_data["pype_data"] = {
        "stored": datetime.datetime.utcnow(),
        "is_processed": False
    }

    try:
        # dbcon.insert_one(event_data)
        dbcon.update({"id": event_id}, event_data, upsert=True)
        log.debug("Event: {} stored".format(event_id))

    except pymongo.errors.AutoReconnect:
        log.error("Mongo server \"{}\" is not responding, exiting.".format(
            os.environ["AVALON_MONGO"]
        ))
        sys.exit(0)

    except Exception as exc:
        log.error(
            "Event: {} failed to store".format(event_id),
            exc_info=True
        )


def register(session):
    '''Registers the event, subscribing the discover and launch topics.'''
    install_db()
    session.event_hub.subscribe("topic=*", launch)


def main(args):
    port = int(args[-1])

    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect the socket to the port where the server is listening
    server_address = ("localhost", port)
    log.debug("Storer connected to {} port {}".format(*server_address))
    sock.connect(server_address)
    sock.sendall(b"CreatedStore")

    try:
        session = StorerSession(auto_connect_event_hub=True, sock=sock)
        register(session)
        server = FtrackServer("event")
        log.debug("Launched Ftrack Event storer")
        server.run_server(session, load_files=False)

    finally:
        log.debug("First closing socket")
        sock.close()
        return 1


if __name__ == "__main__":
    # Register interupt signal
    def signal_handler(sig, frame):
        print("You pressed Ctrl+C. Process ended.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, "SIGKILL"):
        signal.signal(signal.SIGKILL, signal_handler)

    sys.exit(main(sys.argv))
