"""
Wrapper around interactions with the database

Copy of io module in avalon-core.
 - In this case not working as singleton with api.Session!
"""

import time
import logging
import functools
import atexit
import os

# Third-party dependencies
import pymongo
from pype.api import decompose_url


class NotActiveCollection(Exception):
    def __init__(self, *args, **kwargs):
        msg = "Active collection is not set. (This is bug)"
        if not (args or kwargs):
            args = [msg]
        super().__init__(*args, **kwargs)


def auto_reconnect(func):
    """Handling auto reconnect in 3 retry times"""
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        object = args[0]
        for retry in range(3):
            try:
                return func(*args, **kwargs)
            except pymongo.errors.AutoReconnect:
                object.log.error("Reconnecting..")
                time.sleep(0.1)
        else:
            raise
    return decorated


def check_active_collection(func):
    """Check if CustomDbConnector has active collection."""
    @functools.wraps(func)
    def decorated(obj, *args, **kwargs):
        if not obj.active_collection:
            raise NotActiveCollection()
        return func(obj, *args, **kwargs)
    return decorated


class CustomDbConnector:
    log = logging.getLogger(__name__)
    timeout = int(os.environ["AVALON_TIMEOUT"])

    def __init__(
        self, uri, database_name, port=None, collection_name=None
    ):
        self._mongo_client = None
        self._sentry_client = None
        self._sentry_logging_handler = None
        self._database = None
        self._is_installed = False

        self._uri = uri
        components = decompose_url(uri)
        if port is None:
            port = components.get("port")

        if database_name is None:
            raise ValueError(
                "Database is not defined for connection. {}".format(uri)
            )

        self._port = port
        self._database_name = database_name

        self.active_collection = collection_name

    def __getitem__(self, key):
        # gives direct access to collection withou setting `active_collection`
        return self._database[key]

    def __getattribute__(self, attr):
        # not all methods of PyMongo database are implemented with this it is
        # possible to use them too
        try:
            return super(CustomDbConnector, self).__getattribute__(attr)
        except AttributeError:
            if self.active_collection is None:
                raise NotActiveCollection()
            return self._database[self.active_collection].__getattribute__(
                attr
            )

    def install(self):
        """Establish a persistent connection to the database"""
        if self._is_installed:
            return
        atexit.register(self.uninstall)
        logging.basicConfig()

        kwargs = {
            "host": self._uri,
            "serverSelectionTimeoutMS": self.timeout
        }
        if self._port is not None:
            kwargs["port"] = self._port

        self._mongo_client = pymongo.MongoClient(**kwargs)
        if self._port is None:
            self._port = self._mongo_client.PORT

        for retry in range(3):
            try:
                t1 = time.time()
                self._mongo_client.server_info()
            except Exception:
                self.log.error("Retrying..")
                time.sleep(1)
            else:
                break

        else:
            raise IOError(
                "ERROR: Couldn't connect to %s in "
                "less than %.3f ms" % (self._uri, self.timeout)
            )

        self.log.info("Connected to %s, delay %.3f s" % (
            self._uri, time.time() - t1
        ))

        self._database = self._mongo_client[self._database_name]
        self._is_installed = True

    def uninstall(self):
        """Close any connection to the database"""

        try:
            self._mongo_client.close()
        except AttributeError:
            pass

        self._mongo_client = None
        self._database = None
        self._is_installed = False
        atexit.unregister(self.uninstall)

    def collection_exists(self, collection_name):
        return collection_name in self.collections()

    def create_collection(self, name, **options):
        if self.collection_exists(name):
            return

        return self._database.create_collection(name, **options)

    @auto_reconnect
    def collections(self):
        for col_name in self._database.collection_names():
            if col_name not in ("system.indexes",):
                yield col_name

    @check_active_collection
    @auto_reconnect
    def insert_one(self, item, **options):
        assert isinstance(item, dict), "item must be of type <dict>"
        return self._database[self.active_collection].insert_one(
            item, **options
        )

    @check_active_collection
    @auto_reconnect
    def insert_many(self, items, ordered=True, **options):
        # check if all items are valid
        assert isinstance(items, list), "`items` must be of type <list>"
        for item in items:
            assert isinstance(item, dict), "`item` must be of type <dict>"

        options["ordered"] = ordered
        return self._database[self.active_collection].insert_many(
            items, **options
        )

    @check_active_collection
    @auto_reconnect
    def find(self, filter, projection=None, sort=None, **options):
        options["sort"] = sort
        return self._database[self.active_collection].find(
            filter, projection, **options
        )

    @check_active_collection
    @auto_reconnect
    def find_one(self, filter, projection=None, sort=None, **options):
        assert isinstance(filter, dict), "filter must be <dict>"
        options["sort"] = sort
        return self._database[self.active_collection].find_one(
            filter,
            projection,
            **options
        )

    @check_active_collection
    @auto_reconnect
    def replace_one(self, filter, replacement, **options):
        return self._database[self.active_collection].replace_one(
            filter, replacement, **options
        )

    @check_active_collection
    @auto_reconnect
    def update_one(self, filter, update, **options):
        return self._database[self.active_collection].update_one(
            filter, update, **options
        )

    @check_active_collection
    @auto_reconnect
    def update_many(self, filter, update, **options):
        return self._database[self.active_collection].update_many(
            filter, update, **options
        )

    @check_active_collection
    @auto_reconnect
    def distinct(self, **options):
        return self._database[self.active_collection].distinct(**options)

    @check_active_collection
    @auto_reconnect
    def drop_collection(self, name_or_collection, **options):
        return self._database[self.active_collection].drop(
            name_or_collection, **options
        )

    @check_active_collection
    @auto_reconnect
    def delete_one(self, filter, collation=None, **options):
        options["collation"] = collation
        return self._database[self.active_collection].delete_one(
            filter, **options
        )

    @check_active_collection
    @auto_reconnect
    def delete_many(self, filter, collation=None, **options):
        options["collation"] = collation
        return self._database[self.active_collection].delete_many(
            filter, **options
        )
