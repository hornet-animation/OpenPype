import os
import attr
from bson.objectid import ObjectId

from Qt import QtWidgets, QtCore, QtGui
from Qt.QtCore import Qt

from avalon.tools.delegates import pretty_timestamp

from openpype.lib import PypeLogger

from openpype.modules.sync_server.tray import lib


log = PypeLogger().get_logger("SyncServer")


class ProjectModel(QtCore.QAbstractListModel):
    def __init__(self, *args, projects=None, **kwargs):
        super(ProjectModel, self).__init__(*args, **kwargs)
        self.projects = projects or []

    def data(self, index, role):
        if role == Qt.DisplayRole:
            # See below for the data structure.
            status, text = self.projects[index.row()]
            # Return the todo text only.
            return text

    def rowCount(self, index):
        return len(self.todos)

    def columnCount(self, _index):
        return len(self._header)



class _SyncRepresentationModel(QtCore.QAbstractTableModel):

    COLUMN_LABELS = []

    PAGE_SIZE = 20  # default page size to query for
    REFRESH_SEC = 5000  # in seconds, requery DB for new status

    @property
    def dbcon(self):
        """
            Database object with preselected project (collection) to run DB
            operations (find, aggregate).

            All queries should go through this (because of collection).
        """
        return self.sync_server.connection.database[self.project]

    @property
    def project(self):
        """Returns project"""
        return self._project

    def rowCount(self, _index):
        return len(self._data)

    def columnCount(self, _index):
        return len(self._header)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.COLUMN_LABELS[section][1]

    def get_header_index(self, value):
        """
            Returns index of 'value' in headers

            Args:
                value (str): header name value
            Returns:
                (int)
        """
        return self._header.index(value)

    def refresh(self, representations=None, load_records=0):
        """
            Reloads representations from DB if necessary, adds them to model.

            Runs periodically (every X seconds) or by demand (change of
            sorting, filtering etc.)

            Emits 'modelReset' signal.

            Args:
                representations (PaginationResult object): pass result of
                    aggregate query from outside - mostly for testing only
                load_records (int) - enforces how many records should be
                    actually queried (scrolled a couple of times to list more
                    than single page of records)
        """
        if self.sync_server.is_paused() or \
                self.sync_server.is_project_paused(self.project):
            return
        self.refresh_started.emit()
        self.beginResetModel()
        self._data = []
        self._rec_loaded = 0

        if not representations:
            self.query = self.get_default_query(load_records)
            representations = self.dbcon.aggregate(self.query)

        self.add_page_records(self.local_site, self.remote_site,
                               representations)
        self.endResetModel()
        self.refresh_finished.emit()

    def tick(self):
        """
            Triggers refresh of model.

            Because of pagination, prepared (sorting, filtering) query needs
            to be run on DB every X seconds.
        """
        self.refresh(representations=None, load_records=self._rec_loaded)
        self.timer.start(self.REFRESH_SEC)

    def canFetchMore(self, _index):
        """
            Check if there are more records than currently loaded
        """
        # 'skip' might be suboptimal when representation hits 500k+
        return self._total_records > self._rec_loaded

    def fetchMore(self, index):
        """
            Add more record to model.

            Called when 'canFetchMore' returns true, which means there are
            more records in DB than loaded.
        """
        log.debug("fetchMore")
        items_to_fetch = min(self._total_records - self._rec_loaded,
                             self.PAGE_SIZE)
        self.query = self.get_default_query(self._rec_loaded)
        representations = self.dbcon.aggregate(self.query)
        self.beginInsertRows(index,
                             self._rec_loaded,
                             self._rec_loaded + items_to_fetch - 1)

        self.add_page_records(self.local_site, self.remote_site,
                               representations)

        self.endInsertRows()

    def sort(self, index, order):
        """
            Summary sort per representation.

            Sort is happening on a DB side, model is reset, db queried
            again.

            Args:
                index (int): column index
                order (int): 0|
        """
        # limit unwanted first re-sorting by view
        if index < 0:
            return

        self._rec_loaded = 0
        if order == 0:
            order = 1
        else:
            order = -1

        self.sort = {self.SORT_BY_COLUMN[index]: order, '_id': 1}
        self.query = self.get_default_query()
        # import json
        # log.debug(json.dumps(self.query, indent=4).\
        #           replace('False', 'false').\
        #           replace('True', 'true').replace('None', 'null'))

        representations = self.dbcon.aggregate(self.query)
        self.refresh(representations)

    def set_filter(self, word_filter):
        """
            Adds text value filtering

            Args:
                word_filter (str): string inputted by user
        """
        self.word_filter = word_filter
        self.refresh()

    def set_project(self, project):
        """
            Changes project, called after project selection is changed

            Args:
                project (str): name of project
        """
        self._project = project
        self.sync_server.set_sync_project_settings()
        self.local_site = self.sync_server.get_active_site(self.project)
        self.remote_site = self.sync_server.get_remote_site(self.project)
        self.refresh()

    def get_index(self, id):
        """
            Get index of 'id' value.

            Used for keeping selection after refresh.

            Args:
                id (str): MongoDB _id
            Returns:
                (QModelIndex)
        """
        for i in range(self.rowCount(None)):
            index = self.index(i, 0)
            value = self.data(index, Qt.UserRole)
            if value == id:
                return index
        return None

class SyncRepresentationSummaryModel(_SyncRepresentationModel):
    """
        Model for summary of representations.

        Groups files information per representation. Allows sorting and
        full text filtering.

        Allows pagination, most of heavy lifting is being done on DB side.
        Single model matches to single collection. When project is changed,
        model is reset and refreshed.

        Args:
            sync_server (SyncServer) - object to call server operations (update
                db status, set site status...)
            header (list) - names of visible columns
            project (string) - collection name, all queries must be called on
                a specific collection

    """
    COLUMN_LABELS = [
        ("asset", "Asset"),
        ("subset", "Subset"),
        ("version", "Version"),
        ("representation", "Representation"),
        ("local_site", "Active site"),
        ("remote_site", "Remote site"),
        ("files_count", "Files"),
        ("files_size", "Size"),
        ("priority", "Priority"),
        ("state", "Status")
    ]

    DEFAULT_SORT = {
        "updated_dt_remote": -1,
        "_id": 1
    }
    SORT_BY_COLUMN = [
        "context.asset",  # asset
        "context.subset",  # subset
        "context.version",  # version
        "context.representation",  # representation
        "updated_dt_local",  # local created_dt
        "updated_dt_remote",  # remote created_dt
        "files_count",  # count of files
        "files_size",  # file size of all files
        "context.asset",  # priority TODO
        "status"  # state
    ]

    refresh_started = QtCore.Signal()
    refresh_finished = QtCore.Signal()

    @attr.s
    class SyncRepresentation:
        """
            Auxiliary object for easier handling.

            Fields must contain all header values (+ any arbitrary values).
        """
        _id = attr.ib()
        asset = attr.ib()
        subset = attr.ib()
        version = attr.ib()
        representation = attr.ib()
        created_dt = attr.ib(default=None)
        sync_dt = attr.ib(default=None)
        local_site = attr.ib(default=None)
        remote_site = attr.ib(default=None)
        local_provider = attr.ib(default=None)
        remote_provider = attr.ib(default=None)
        local_progress = attr.ib(default=None)
        remote_progress = attr.ib(default=None)
        files_count = attr.ib(default=None)
        files_size = attr.ib(default=None)
        priority = attr.ib(default=None)
        state = attr.ib(default=None)
        path = attr.ib(default=None)

    def __init__(self, sync_server, header, project=None):
        super(SyncRepresentationSummaryModel, self).__init__()
        self._header = header
        self._data = []
        self._project = project
        self._rec_loaded = 0
        self._total_records = 0  # how many documents query actually found
        self.word_filter = None

        self._initialized = False
        if not self._project or self._project == lib.DUMMY_PROJECT:
            return

        self.sync_server = sync_server
        # TODO think about admin mode
        # this is for regular user, always only single local and single remote
        self.local_site = self.sync_server.get_active_site(self.project)
        self.remote_site = self.sync_server.get_remote_site(self.project)

        self.projection = self.get_default_projection()

        self.sort = self.DEFAULT_SORT

        self.query = self.get_default_query()
        self.default_query = list(self.get_default_query())

        representations = self.dbcon.aggregate(self.query)
        self.refresh(representations)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(self.REFRESH_SEC)

    def data(self, index, role):
        item = self._data[index.row()]

        header_value = self._header[index.column()]
        if role == lib.ProviderRole:
            if header_value == 'local_site':
                return item.local_provider
            if header_value == 'remote_site':
                return item.remote_provider

        if role == lib.ProgressRole:
            if header_value == 'local_site':
                return item.local_progress
            if header_value == 'remote_site':
                return item.remote_progress

        if role == lib.DateRole:
            if header_value == 'local_site':
                if item.created_dt:
                    return pretty_timestamp(item.created_dt)
            if header_value == 'remote_site':
                if item.sync_dt:
                    return pretty_timestamp(item.sync_dt)

        if role == lib.FailedRole:
            if header_value == 'local_site':
                return item.state == lib.STATUS[2] and item.local_progress < 1
            if header_value == 'remote_site':
                return item.state == lib.STATUS[2] and item.remote_progress < 1

        if role == Qt.DisplayRole:
            # because of ImageDelegate
            if header_value in ['remote_site', 'local_site']:
                return ""

            return attr.asdict(item)[self._header[index.column()]]
        if role == Qt.UserRole:
            return item._id


    def add_page_records(self, local_site, remote_site, representations):
        """
            Process all records from 'representation' and add them to storage.

            Args:
                local_site (str): name of local site (mine)
                remote_site (str): name of cloud provider (theirs)
                representations (Mongo Cursor) - mimics result set, 1 object
                    with paginatedResults array and totalCount array
        """
        result = representations.next()
        count = 0
        total_count = result.get("totalCount")
        if total_count:
            count = total_count.pop().get('count')
        self._total_records = count

        local_provider = lib.translate_provider_for_icon(self.sync_server,
                                                      self.project,
                                                      local_site)
        remote_provider = lib.translate_provider_for_icon(self.sync_server,
                                                       self.project,
                                                       remote_site)

        for repre in result.get("paginatedResults"):
            context = repre.get("context").pop()
            files = repre.get("files", [])
            if isinstance(files, dict):  # aggregate returns dictionary
                files = [files]

            # representation without files doesnt concern us
            if not files:
                continue

            local_updated = remote_updated = None
            if repre.get('updated_dt_local'):
                local_updated = \
                    repre.get('updated_dt_local').strftime("%Y%m%dT%H%M%SZ")

            if repre.get('updated_dt_remote'):
                remote_updated = \
                    repre.get('updated_dt_remote').strftime("%Y%m%dT%H%M%SZ")

            avg_progress_remote = lib.convert_progress(
                repre.get('avg_progress_remote', '0'))
            avg_progress_local = lib.convert_progress(
                repre.get('avg_progress_local', '0'))

            if context.get("version"):
                version = "v{:0>3d}".format(context.get("version"))
            else:
                version = "master"

            item = self.SyncRepresentation(
                repre.get("_id"),
                context.get("asset"),
                context.get("subset"),
                version,
                context.get("representation"),
                local_updated,
                remote_updated,
                local_site,
                remote_site,
                local_provider,
                remote_provider,
                avg_progress_local,
                avg_progress_remote,
                repre.get("files_count", 1),
                lib.pretty_size(repre.get("files_size", 0)),
                1,
                lib.STATUS[repre.get("status", -1)],
                files[0].get('path')
            )

            self._data.append(item)
            self._rec_loaded += 1

    def get_default_query(self, limit=0):
        """
            Returns basic aggregate query for main table.

            Main table provides summary information about representation,
            which could have multiple files. Details are accessible after
            double click on representation row.
            Columns:
                'created_dt' - max of created or updated (when failed) per repr
                'sync_dt' - same for remote side
                'local_site' - progress of repr on local side, 1 = finished
                'remote_site' - progress on remote side, calculates from files
                'state' -
                    0 - in progress
                    1 - failed
                    2 - queued
                    3 - paused
                    4 - finished on both sides

                are calculated and must be calculated in DB because of
                pagination

            Args:
                limit (int): how many records should be returned, by default
                    it 'PAGE_SIZE' for performance.
                    Should be overridden by value of loaded records for refresh
                    functionality (got more records by scrolling, refresh
                    shouldn't reset that)
        """
        if limit == 0:
            limit = SyncRepresentationSummaryModel.PAGE_SIZE

        return [
            {"$match": self.get_match_part()},
            {'$unwind': '$files'},
            # merge potentially unwinded records back to single per repre
            {'$addFields': {
                'order_remote': {
                    '$filter': {'input': '$files.sites', 'as': 'p',
                                'cond': {'$eq': ['$$p.name', self.remote_site]}
                                }},
                'order_local': {
                    '$filter': {'input': '$files.sites', 'as': 'p',
                                'cond': {'$eq': ['$$p.name', self.local_site]}
                                }}
            }},
            {'$addFields': {
                # prepare progress per file, presence of 'created_dt' denotes
                # successfully finished load/download
                'progress_remote': {'$first': {
                    '$cond': [{'$size': "$order_remote.progress"},
                              "$order_remote.progress",
                              {'$cond': [
                                  {'$size': "$order_remote.created_dt"},
                                  [1],
                                  [0]
                              ]}
                              ]}},
                'progress_local': {'$first': {
                    '$cond': [{'$size': "$order_local.progress"},
                              "$order_local.progress",
                              {'$cond': [
                                  {'$size': "$order_local.created_dt"},
                                  [1],
                                  [0]
                              ]}
                              ]}},
                # file might be successfully created or failed, not both
                'updated_dt_remote': {'$first': {
                    '$cond': [{'$size': "$order_remote.created_dt"},
                              "$order_remote.created_dt",
                              {'$cond': [
                                  {'$size': "$order_remote.last_failed_dt"},
                                  "$order_remote.last_failed_dt",
                                  []
                              ]}
                              ]}},
                'updated_dt_local': {'$first': {
                    '$cond': [{'$size': "$order_local.created_dt"},
                              "$order_local.created_dt",
                              {'$cond': [
                                  {'$size': "$order_local.last_failed_dt"},
                                  "$order_local.last_failed_dt",
                                  []
                              ]}
                              ]}},
                'files_size': {'$ifNull': ["$files.size", 0]},
                'failed_remote': {
                    '$cond': [{'$size': "$order_remote.last_failed_dt"},
                              1,
                              0]},
                'failed_local': {
                    '$cond': [{'$size': "$order_local.last_failed_dt"},
                              1,
                              0]},
                'failed_local_tries': {
                    '$cond': [{'$size': '$order_local.tries'},
                              {'$first': '$order_local.tries'},
                              0]},
                'failed_remote_tries': {
                    '$cond': [{'$size': '$order_remote.tries'},
                              {'$first': '$order_remote.tries'},
                              0]},
                'paused_remote': {
                    '$cond': [{'$size': "$order_remote.paused"},
                              1,
                              0]},
                'paused_local': {
                    '$cond': [{'$size': "$order_local.paused"},
                              1,
                              0]},
            }},
            {'$group': {
                '_id': '$_id',
                # pass through context - same for representation
                'context': {'$addToSet': '$context'},
                'data': {'$addToSet': '$data'},
                # pass through files as a list
                'files': {'$addToSet': '$files'},
                # count how many files
                'files_count': {'$sum': 1},
                'files_size': {'$sum': '$files_size'},
                # sum avg progress, finished = 1
                'avg_progress_remote': {'$avg': "$progress_remote"},
                'avg_progress_local': {'$avg': "$progress_local"},
                # select last touch of file
                'updated_dt_remote': {'$max': "$updated_dt_remote"},
                'failed_remote': {'$sum': '$failed_remote'},
                'failed_local': {'$sum': '$failed_local'},
                'failed_remote_tries': {'$sum': '$failed_remote_tries'},
                'failed_local_tries': {'$sum': '$failed_local_tries'},
                'paused_remote': {'$sum': '$paused_remote'},
                'paused_local': {'$sum': '$paused_local'},
                'updated_dt_local': {'$max': "$updated_dt_local"}
            }},
            {"$project": self.projection},
            {"$sort": self.sort},
            {
                '$facet': {
                    'paginatedResults': [{'$skip': self._rec_loaded},
                                         {'$limit': limit}],
                    'totalCount': [{'$count': 'count'}]
                }
            }
        ]

    def get_match_part(self):
        """
            Extend match part with word_filter if present.

            Filter is set by user input. Each model has different fields to be
            checked.
            If performance issues are found, '$text' and text indexes should
            be investigated.

            Fulltext searches in:
                context.subset
                context.asset
                context.representation  names AND _id (ObjectId)
        """
        base_match = {
                "type": "representation",
                'files.sites.name': {'$all': [self.local_site,
                                              self.remote_site]}
        }
        if not self.word_filter:
            return base_match
        else:
            regex_str = '.*{}.*'.format(self.word_filter)
            base_match['$or'] = [
                    {'context.subset': {'$regex': regex_str, '$options': 'i'}},
                    {'context.asset': {'$regex': regex_str, '$options': 'i'}},
                    {'context.representation': {'$regex': regex_str,
                                                '$options': 'i'}}]

            if ObjectId.is_valid(self.word_filter):
                base_match['$or'] = [{'_id': ObjectId(self.word_filter)}]

            return base_match

    def get_default_projection(self):
        """
            Projection part for aggregate query.

            All fields with '1' will be returned, no others.

            Returns:
                (dict)
        """
        return {
            "context.subset": 1,
            "context.asset": 1,
            "context.version": 1,
            "context.representation": 1,
            "data.path": 1,
            "files": 1,
            'files_count': 1,
            "files_size": 1,
            'avg_progress_remote': 1,
            'avg_progress_local': 1,
            'updated_dt_remote': 1,
            'updated_dt_local': 1,
            'paused_remote': 1,
            'paused_local': 1,
            'status': {
                '$switch': {
                    'branches': [
                        {
                            'case': {
                                '$or': ['$paused_remote', '$paused_local']},
                            'then': 3  # Paused
                        },
                        {
                            'case': {
                                '$or': [
                                    {'$gte': ['$failed_local_tries', 3]},
                                    {'$gte': ['$failed_remote_tries', 3]}
                                ]},
                            'then': 2},  # Failed
                        {
                            'case': {
                                '$or': [{'$eq': ['$avg_progress_remote', 0]},
                                        {'$eq': ['$avg_progress_local', 0]}]},
                            'then': 1  # Queued
                        },
                        {
                            'case': {'$or': [{'$and': [
                                {'$gt': ['$avg_progress_remote', 0]},
                                {'$lt': ['$avg_progress_remote', 1]}
                            ]},
                                {'$and': [
                                    {'$gt': ['$avg_progress_local', 0]},
                                    {'$lt': ['$avg_progress_local', 1]}
                                ]}
                            ]},
                            'then': 0  # In progress
                        },
                        {
                            'case': {'$and': [
                                {'$eq': ['$avg_progress_remote', 1]},
                                {'$eq': ['$avg_progress_local', 1]}
                            ]},
                            'then': 4  # Synced OK
                        },
                    ],
                    'default': -1
                }
            }
        }


class SyncRepresentationDetailModel(_SyncRepresentationModel):
    """
        List of all syncronizable files per single representation.

        Used in detail window accessible after clicking on single repre in the
        summary.

        Args:
            sync_server (SyncServer) - object to call server operations (update
                db status, set site status...)
            header (list) - names of visible columns
            _id (string) - MongoDB _id of representation
            project (string) - collection name, all queries must be called on
                a specific collection
    """
    COLUMN_LABELS = [
        ("file", "File name"),
        ("local_site", "Active site"),
        ("remote_site", "Remote site"),
        ("files_size", "Size"),
        ("priority", "Priority"),
        ("state", "Status")
    ]

    PAGE_SIZE = 30
    DEFAULT_SORT = {
        "files.path": 1
    }
    SORT_BY_COLUMN = [
        "files.path",
        "updated_dt_local",  # local created_dt
        "updated_dt_remote",  # remote created_dt
        "size",  # remote progress
        "context.asset",  # priority TODO
        "status"  # state
    ]

    refresh_started = QtCore.Signal()
    refresh_finished = QtCore.Signal()

    @attr.s
    class SyncRepresentationDetail:
        """
            Auxiliary object for easier handling.

            Fields must contain all header values (+ any arbitrary values).
        """
        _id = attr.ib()
        file = attr.ib()
        created_dt = attr.ib(default=None)
        sync_dt = attr.ib(default=None)
        local_site = attr.ib(default=None)
        remote_site = attr.ib(default=None)
        local_provider = attr.ib(default=None)
        remote_provider = attr.ib(default=None)
        local_progress = attr.ib(default=None)
        remote_progress = attr.ib(default=None)
        size = attr.ib(default=None)
        priority = attr.ib(default=None)
        state = attr.ib(default=None)
        tries = attr.ib(default=None)
        error = attr.ib(default=None)
        path = attr.ib(default=None)

    def __init__(self, sync_server, header, _id,
                 project=None):
        super(SyncRepresentationDetailModel, self).__init__()
        self._header = header
        self._data = []
        self._project = project
        self._rec_loaded = 0
        self._total_records = 0  # how many documents query actually found
        self.word_filter = None
        self._id = _id
        self._initialized = False

        self.sync_server = sync_server
        # TODO think about admin mode
        # this is for regular user, always only single local and single remote
        self.local_site = self.sync_server.get_active_site(self.project)
        self.remote_site = self.sync_server.get_remote_site(self.project)

        self.sort = self.DEFAULT_SORT

        # in case we would like to hide/show some columns
        self.projection = self.get_default_projection()

        self.query = self.get_default_query()
        representations = self.dbcon.aggregate(self.query)
        self.refresh(representations)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(SyncRepresentationSummaryModel.REFRESH_SEC)

    def data(self, index, role):
        item = self._data[index.row()]

        header_value = self._header[index.column()]
        if role == lib.ProviderRole:
            if header_value == 'local_site':
                return item.local_provider
            if header_value == 'remote_site':
                return item.remote_provider

        if role == lib.ProgressRole:
            if header_value == 'local_site':
                return item.local_progress
            if header_value == 'remote_site':
                return item.remote_progress

        if role == lib.DateRole:
            if header_value == 'local_site':
                if item.created_dt:
                    return pretty_timestamp(item.created_dt)
            if header_value == 'remote_site':
                if item.sync_dt:
                    return pretty_timestamp(item.sync_dt)

        if role == lib.FailedRole:
            if header_value == 'local_site':
                return item.state == lib.STATUS[2] and item.local_progress < 1
            if header_value == 'remote_site':
                return item.state == lib.STATUS[2] and item.remote_progress < 1

        if role == Qt.DisplayRole:
            # because of ImageDelegate
            if header_value in ['remote_site', 'local_site']:
                return ""
            return attr.asdict(item)[self._header[index.column()]]
        if role == Qt.UserRole:
            return item._id

    def add_page_records(self, local_site, remote_site, representations):
        """
            Process all records from 'representation' and add them to storage.

            Args:
                local_site (str): name of local site (mine)
                remote_site (str): name of cloud provider (theirs)
                representations (Mongo Cursor) - mimics result set, 1 object
                    with paginatedResults array and totalCount array
        """
        # representations is a Cursor, get first
        result = representations.next()
        count = 0
        total_count = result.get("totalCount")
        if total_count:
            count = total_count.pop().get('count')
        self._total_records = count

        local_provider = lib.translate_provider_for_icon(self.sync_server,
                                                      self.project,
                                                      local_site)
        remote_provider = lib.translate_provider_for_icon(self.sync_server,
                                                       self.project,
                                                       remote_site)

        for repre in result.get("paginatedResults"):
            # log.info("!!! repre:: {}".format(repre))
            files = repre.get("files", [])
            if isinstance(files, dict):  # aggregate returns dictionary
                files = [files]

            for file in files:
                local_updated = remote_updated = None
                if repre.get('updated_dt_local'):
                    local_updated = \
                        repre.get('updated_dt_local').strftime(
                            "%Y%m%dT%H%M%SZ")

                if repre.get('updated_dt_remote'):
                    remote_updated = \
                        repre.get('updated_dt_remote').strftime(
                            "%Y%m%dT%H%M%SZ")

                remote_progress = lib.convert_progress(
                    repre.get('progress_remote', '0'))
                local_progress = lib.convert_progress(
                    repre.get('progress_local', '0'))

                errors = []
                if repre.get('failed_remote_error'):
                    errors.append(repre.get('failed_remote_error'))
                if repre.get('failed_local_error'):
                    errors.append(repre.get('failed_local_error'))

                item = self.SyncRepresentationDetail(
                    file.get("_id"),
                    os.path.basename(file["path"]),
                    local_updated,
                    remote_updated,
                    local_site,
                    remote_site,
                    local_provider,
                    remote_provider,
                    local_progress,
                    remote_progress,
                    lib.pretty_size(file.get('size', 0)),
                    1,
                    lib.STATUS[repre.get("status", -1)],
                    repre.get("tries"),
                    '\n'.join(errors),
                    file.get('path')

                )
                self._data.append(item)
                self._rec_loaded += 1

    def get_default_query(self, limit=0):
        """
            Gets query that gets used when no extra sorting, filtering or
            projecting is needed.

            Called for basic table view.

            Returns:
                [(dict)] - list with single dict - appropriate for aggregate
                    function for MongoDB
        """
        if limit == 0:
            limit = SyncRepresentationSummaryModel.PAGE_SIZE

        return [
            {"$match": self.get_match_part()},
            {"$unwind": "$files"},
            {'$addFields': {
                'order_remote': {
                    '$filter': {'input': '$files.sites', 'as': 'p',
                                'cond': {'$eq': ['$$p.name', self.remote_site]}
                                }},
                'order_local': {
                    '$filter': {'input': '$files.sites', 'as': 'p',
                                'cond': {'$eq': ['$$p.name', self.local_site]}
                                }}
            }},
            {'$addFields': {
                # prepare progress per file, presence of 'created_dt' denotes
                # successfully finished load/download
                'progress_remote': {'$first': {
                    '$cond': [{'$size': "$order_remote.progress"},
                              "$order_remote.progress",
                              {'$cond': [
                                  {'$size': "$order_remote.created_dt"},
                                  [1],
                                  [0]
                              ]}
                              ]}},
                'progress_local': {'$first': {
                    '$cond': [{'$size': "$order_local.progress"},
                              "$order_local.progress",
                              {'$cond': [
                                  {'$size': "$order_local.created_dt"},
                                  [1],
                                  [0]
                              ]}
                              ]}},
                # file might be successfully created or failed, not both
                'updated_dt_remote': {'$first': {
                    '$cond': [
                        {'$size': "$order_remote.created_dt"},
                        "$order_remote.created_dt",
                        {
                            '$cond': [
                                {'$size': "$order_remote.last_failed_dt"},
                                "$order_remote.last_failed_dt",
                                []
                            ]
                        }
                    ]
                }},
                'updated_dt_local': {'$first': {
                    '$cond': [
                        {'$size': "$order_local.created_dt"},
                        "$order_local.created_dt",
                        {
                            '$cond': [
                                {'$size': "$order_local.last_failed_dt"},
                                "$order_local.last_failed_dt",
                                []
                            ]
                        }
                    ]
                }},
                'paused_remote': {
                    '$cond': [{'$size': "$order_remote.paused"},
                              1,
                              0]},
                'paused_local': {
                    '$cond': [{'$size': "$order_local.paused"},
                              1,
                              0]},
                'failed_remote': {
                    '$cond': [{'$size': "$order_remote.last_failed_dt"},
                              1,
                              0]},
                'failed_local': {
                    '$cond': [{'$size': "$order_local.last_failed_dt"},
                              1,
                              0]},
                'failed_remote_error': {'$first': {
                    '$cond': [{'$size': "$order_remote.error"},
                              "$order_remote.error",
                              [""]]}},
                'failed_local_error': {'$first': {
                    '$cond': [{'$size': "$order_local.error"},
                              "$order_local.error",
                              [""]]}},
                'tries': {'$first': {
                    '$cond': [
                        {'$size': "$order_local.tries"},
                        "$order_local.tries",
                        {'$cond': [
                            {'$size': "$order_remote.tries"},
                            "$order_remote.tries",
                            []
                        ]}
                    ]}}
            }},
            {"$project": self.projection},
            {"$sort": self.sort},
            {
                '$facet': {
                    'paginatedResults': [{'$skip': self._rec_loaded},
                                         {'$limit': limit}],
                    'totalCount': [{'$count': 'count'}]
                }
            }
        ]

    def get_match_part(self):
        """
            Returns different content for 'match' portion if filtering by
            name is present

            Returns:
                (dict)
        """
        if not self.word_filter:
            return {
                "type": "representation",
                "_id": self._id
            }
        else:
            regex_str = '.*{}.*'.format(self.word_filter)
            return {
                "type": "representation",
                "_id": self._id,
                '$or': [{'files.path': {'$regex': regex_str, '$options': 'i'}}]
            }

    def get_default_projection(self):
        """
            Projection part for aggregate query.

            All fields with '1' will be returned, no others.

            Returns:
                (dict)
        """
        return {
            "files": 1,
            'progress_remote': 1,
            'progress_local': 1,
            'updated_dt_remote': 1,
            'updated_dt_local': 1,
            'paused_remote': 1,
            'paused_local': 1,
            'failed_remote_error': 1,
            'failed_local_error': 1,
            'tries': 1,
            'status': {
                '$switch': {
                    'branches': [
                        {
                            'case': {
                                '$or': ['$paused_remote', '$paused_local']},
                            'then': 3  # Paused
                        },
                        {
                            'case': {
                                '$and': [{'$or': ['$failed_remote',
                                                  '$failed_local']},
                                         {'$eq': ['$tries', 3]}]},
                            'then': 1  # Failed (3 tries)
                        },
                        {
                            'case': {
                                '$or': [{'$eq': ['$progress_remote', 0]},
                                        {'$eq': ['$progress_local', 0]}]},
                            'then': 2  # Queued
                        },
                        {
                            'case': {
                                '$or': ['$failed_remote', '$failed_local']},
                            'then': 1  # Failed
                        },
                        {
                            'case': {'$or': [{'$and': [
                                {'$gt': ['$progress_remote', 0]},
                                {'$lt': ['$progress_remote', 1]}
                            ]},
                                {'$and': [
                                    {'$gt': ['$progress_local', 0]},
                                    {'$lt': ['$progress_local', 1]}
                                ]}
                            ]},
                            'then': 0  # In Progress
                        },
                        {
                            'case': {'$and': [
                                {'$eq': ['$progress_remote', 1]},
                                {'$eq': ['$progress_local', 1]}
                            ]},
                            'then': 4  # Synced OK
                        },
                    ],
                    'default': -1
                }
            },
            'data.path': 1
        }
