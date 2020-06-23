import collections
from Qt import QtCore
from pype.api import Logger
from pypeapp.lib.log import _bootstrap_mongo_log, LOG_COLLECTION_NAME

log = Logger().get_logger("LogModel", "LoggingModule")


class LogModel(QtCore.QAbstractItemModel):
    COLUMNS = [
        "process_name",
        "hostname",
        "hostip",
        "username",
        "system_name",
        "started"
    ]

    colums_mapping = {
        "process_name": "Process Name",
        "process_id": "Process Id",
        "hostname": "Hostname",
        "hostip": "Host IP",
        "username": "Username",
        "system_name": "System name",
        "started": "Started at"
    }
    process_keys = [
        "process_id", "hostname", "hostip",
        "username", "system_name", "process_name"
    ]
    log_keys = [
        "timestamp", "level", "thread", "threadName", "message", "loggerName",
        "fileName", "module", "method", "lineNumber"
    ]
    default_value = "- Not set -"
    NodeRole = QtCore.Qt.UserRole + 1

    def __init__(self, parent=None):
        super(LogModel, self).__init__(parent)
        self._root_node = Node()

        self.dbcon = None
        # Crash if connection is not possible to skip this module
        database = _bootstrap_mongo_log()
        if LOG_COLLECTION_NAME in database.list_collection_names():
            self.dbcon = database[LOG_COLLECTION_NAME]

    def add_log(self, log):
        node = Node(log)
        self._root_node.add_child(node)

    def refresh(self):
        self.log_by_process = collections.defaultdict(list)
        self.process_info = {}

        self.clear()
        self.beginResetModel()
        if self.dbcon:
            result = self.dbcon.find({})
            for item in result:
                process_id = item.get("process_id")
                # backwards (in)compatibility
                if not process_id:
                    continue

                if process_id not in self.process_info:
                    proc_dict = {}
                    for key in self.process_keys:
                        proc_dict[key] = (
                            item.get(key) or self.default_value
                        )
                    self.process_info[process_id] = proc_dict

                if "_logs" not in self.process_info[process_id]:
                    self.process_info[process_id]["_logs"] = []

                log_item = {}
                for key in self.log_keys:
                    log_item[key] = item.get(key) or self.default_value

                if "exception" in item:
                    log_item["exception"] = item["exception"]

                self.process_info[process_id]["_logs"].append(log_item)

        for item in self.process_info.values():
            item["_logs"] = sorted(
                item["_logs"], key=lambda item: item["timestamp"]
            )
            item["started"] = item["_logs"][0]["timestamp"]
            self.add_log(item)

        self.endResetModel()

    def data(self, index, role):
        if not index.isValid():
            return None

        if role == QtCore.Qt.DisplayRole or role == QtCore.Qt.EditRole:
            node = index.internalPointer()
            column = index.column()

            key = self.COLUMNS[column]
            if key == "started":
                return str(node.get(key, None))
            return node.get(key, None)

        if role == self.NodeRole:
            return index.internalPointer()

    def index(self, row, column, parent):
        """Return index for row/column under parent"""

        if not parent.isValid():
            parent_node = self._root_node
        else:
            parent_node = parent.internalPointer()

        child_item = parent_node.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QtCore.QModelIndex()

    def rowCount(self, parent):
        node = self._root_node
        if parent.isValid():
            node = parent.internalPointer()
        return node.childCount()

    def columnCount(self, parent):
        return len(self.COLUMNS)

    def parent(self, index):
        return QtCore.QModelIndex()

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if section < len(self.COLUMNS):
                key = self.COLUMNS[section]
                return self.colums_mapping.get(key, key)

        super(LogModel, self).headerData(section, orientation, role)

    def flags(self, index):
        return (QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)

    def clear(self):
        self.beginResetModel()
        self._root_node = Node()
        self.endResetModel()


class Node(dict):
    """A node that can be represented in a tree view.

    The node can store data just like a dictionary.

    >>> data = {"name": "John", "score": 10}
    >>> node = Node(data)
    >>> assert node["name"] == "John"

    """

    def __init__(self, data=None):
        super(Node, self).__init__()

        self._children = list()
        self._parent = None

        if data is not None:
            assert isinstance(data, dict)
            self.update(data)

    def childCount(self):
        return len(self._children)

    def child(self, row):
        if row >= len(self._children):
            log.warning("Invalid row as child: {0}".format(row))
            return

        return self._children[row]

    def children(self):
        return self._children

    def parent(self):
        return self._parent

    def row(self):
        """
        Returns:
             int: Index of this node under parent"""
        if self._parent is not None:
            siblings = self.parent().children()
            return siblings.index(self)

    def add_child(self, child):
        """Add a child to this node"""
        child._parent = self
        self._children.append(child)
