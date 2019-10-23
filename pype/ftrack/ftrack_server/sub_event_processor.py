import os
import sys
import datetime
import signal
import socket
import pymongo

from ftrack_server import FtrackServer
from pype.ftrack.ftrack_server.session_processor import ProcessSession
from pypeapp import Logger

log = Logger().get_logger("Event processor")


def main(args):
    port = int(args[-1])
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect the socket to the port where the server is listening
    server_address = ("localhost", port)
    log.debug("Processor connected to {} port {}".format(*server_address))
    sock.connect(server_address)

    sock.sendall(b"CreatedProcess")
    try:
        session = ProcessSession(auto_connect_event_hub=True, sock=sock)
        server = FtrackServer('event')
        log.debug("Launched Ftrack Event processor")
        server.run_server(session)

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
