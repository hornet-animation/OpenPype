from pype.api import config, Logger

import threading
import asyncio
import concurrent.futures
from concurrent.futures._base import CancelledError

from enum import Enum
from datetime import datetime

from .providers import lib
import os
from avalon import io

from avalon.api import AvalonMongoDB
from .utils import time_function

log = Logger().get_logger("SyncServer")


class SyncStatus(Enum):
    DO_NOTHING = 0
    DO_UPLOAD = 1
    DO_DOWNLOAD = 2


class SyncServer():
    """
       Synchronization server that is syncing published files from local to
       any of implemented providers (like GDrive, S3 etc.)
       Runs in the background and checks all representations, looks for files
       that are marked to be in different location than 'studio' (temporary),
       checks if 'created_dt' field is present denoting successful sync
       with provider destination.
       Sites structure is created during publish and by default it will
       always contain 1 record with "name" ==  self.presets["active_site"] and
       filled "created_dt" AND 1 or multiple records for all defined
       remote sites, where "created_dt" is not present.
       This highlights that file should be uploaded to
       remote destination

       ''' - example of synced file test_Cylinder_lookMain_v010.ma to GDrive
        "files" : [
        {
            "path" : "{root}/Test/Assets/Cylinder/publish/look/lookMain/v010/
                     test_Cylinder_lookMain_v010.ma",
            "_id" : ObjectId("5eeb25e411e06a16209ab78f"),
            "hash" : "test_Cylinder_lookMain_v010,ma|1592468963,24|4822",
            "size" : NumberLong(4822),
            "sites" : [
                {
                    "name": "john_local_XD4345",
                    "created_dt" : ISODate("2020-05-22T08:05:44.000Z")
                },
                {
                    "id" : ObjectId("5eeb25e411e06a16209ab78f"),
                    "name": "gdrive",
                    "created_dt" : ISODate("2020-05-55T08:54:35.833Z")
                ]
            }
        },
        '''
        Each Tray app has assigned its own  self.presets["local_id"]
        used in sites as a name.
        Tray is searching only for records where name matches its
        self.presets["active_site"] + self.presets["remote_site"].
        "active_site" could be storage in studio ('studio'), or specific
        "local_id" when user is working disconnected from home.
        If the local record has its "created_dt" filled, it is a source and
        process will try to upload the file to all defined remote sites.

        Remote files "id" is real id that could be used in appropriate API.
        Local files have "id" too, for conformity, contains just file name.
        It is expected that multiple providers will be implemented in separate
        classes and registered in 'providers.py'.

    """
    # limit querying DB to look for X number of representations that should
    # be sync, we try to run more loops with less records
    # actual number of files synced could be lower as providers can have
    # different limits imposed by its API
    # set 0 to no limit
    REPRESENTATION_LIMIT = 100

    def __init__(self):
        self.qaction = None
        self.failed_icon = None
        self._is_running = False
        self.presets = None
        self.lock = threading.Lock()

        self.connection = AvalonMongoDB()

        try:
            self.presets = config.get_presets()["sync_server"]["config"]

            self.sync_server_thread = SyncServerThread(self)

            self.active_site = self.presets["active_site"]
            self.remote_site = self.presets["remote_site"]

            # try to activate providers, need to have valid credentials
            self.active_sites = []
            for provider in lib.factory.providers.keys():
                for site in lib.factory.providers[provider][0].get_presets(). \
                        keys():
                    handler = lib.factory.get_provider(provider, site)
                    if handler.is_active():
                        self.active_sites.append((provider, site))
        except KeyError:
            log.debug(("There are not set presets for SyncServer."
                       " No credentials provided, no syncing possible").
                      format(str(self.presets)))

    @property
    def active_site(self):
        """
            Returns active 'local' site (could be personal location on user
            laptop or general 'studio' mounted disk.
            Its 'mine' part of synchronization.

        Returns:
            (string)
        """
        return self._active_site

    @active_site.setter
    def active_site(self, value):
        """
            Sets 'mine' part of synchronization process. It is expected only
            single site is active at the time. Active site could be changed
            though on different location (user working in studio has
            'active_site' = 'studio', when user is at home changes
            'active_site' to 'john_doe_local_001'.

        Args:
            value (string): label for site, needs to match representation's
                'files.site'.keys()

        Returns:
            (string)
        """
        self._active_site = value

    @property
    def remote_site(self):
        """
            Remote side of synchronization, where "to synchronize to".
            Currently expected only single remote destination ('gdrive'..),
            but prepared for multiple.
            Denotes 'theirs' side of synchronization.

        Returns:
            (list) of strings (['gdrive'])
        """
        return [self._remote_site]

    @remote_site.setter
    def remote_site(self, value):
        self._remote_site = value

    def get_collections(self):
        """
        Returns:
            (list) of strings with collection names in avalon DB
        """
        return self.connection.database.collection_names(False)

    @time_function
    def get_sync_representations(self, collection, active_site, remote_site):
        """
            Get representations that should be synced, these could be
            recognised by presence of document in 'files.sites', where key is
            a provider (GDrive, S3) and value is empty document or document
            without 'created_dt' field. (Don't put null to 'created_dt'!).

            Querying of 'to-be-synched' files is offloaded to Mongod for
            better performance. Goal is to get as few representations as
            possible.
        Args:
            collection (string): name of collection (in most cases matches
                project name
            active_site (string): identifier of current active site (could be
                'local_0' when working from home, 'studio' when working in the
                studio (default)
            remote_site (string): identifier of remote site I want to sync to

        Returns:
            (list) of dictionaries
        """
        log.debug("Check representations for : {}".format(collection))
        self.connection.Session["AVALON_PROJECT"] = collection
        # retry_cnt - number of attempts to sync specific file before giving up
        retries_arr = self._get_retries_arr()
        active_providers_str = ",".join(remote_site)
        query = {
            "type": "representation",
            "$or": [
                {"$and": [
                    {
                        "files.sites": {
                            "$elemMatch": {
                                "name": active_site,
                                "created_dt": {"$exists": True}
                            }
                        }}, {
                        "files.sites": {
                            "$elemMatch": {
                                "name": {"$in": [active_providers_str]},
                                "created_dt": {"$exists": False},
                                "tries": {"$in": retries_arr}
                            }
                        }
                    }]},
                {"$and": [
                    {
                        "files.sites": {
                            "$elemMatch": {
                                "name": active_site,
                                "created_dt": {"$exists": False},
                                "tries": {"$in": retries_arr}
                            }
                        }}, {
                        "files.sites": {
                            "$elemMatch": {
                                "name": {"$in": [active_providers_str]},
                                "created_dt": {"$exists": True}
                            }
                        }
                    }
                ]}
            ]
        }

        log.debug("get_sync_representations.query: {}".format(query))
        representations = self.connection.find(query)

        return representations

    def check_status(self, file, provider_name):
        """
            Check synchronization status for single 'file' of single
            'representation' by single 'provider'.
            (Eg. check if 'scene.ma' of lookdev.v10 should be synced to GDrive

            Always is comparing local record, eg. site with
            'name' == self.presets["active_site"]

        Args:
            file (dictionary):  of file from representation in Mongo
            provider_name (string):  - gdrive etc.
        Returns:
            (string) - one of SyncStatus
        """
        sites = file.get("sites") or []
        # if isinstance(sites, list):  # temporary, old format of 'sites'
        #     return SyncStatus.DO_NOTHING
        _, provider_rec = self._get_provider_rec(sites, provider_name) or {}
        if provider_rec:  # sync remote target
            created_dt = provider_rec.get("created_dt")
            if not created_dt:
                tries = self._get_tries_count_from_rec(provider_rec)
                # file will be skipped if unsuccessfully tried over threshold
                # error metadata needs to be purged manually in DB to reset
                if tries < self.presets["retry_cnt"]:
                    return SyncStatus.DO_UPLOAD
            else:
                _, local_rec = self._get_provider_rec(
                    sites,
                    self.presets["active_site"]) or {}

                if not local_rec or not local_rec.get("created_dt"):
                    tries = self._get_tries_count_from_rec(local_rec)
                    # file will be skipped if unsuccessfully tried over
                    # threshold times, error metadata needs to be purged
                    # manually in DB to reset
                    if tries < self.presets["retry_cnt"]:
                        return SyncStatus.DO_DOWNLOAD

        return SyncStatus.DO_NOTHING

    async def upload(self, file, representation, provider_name, site_name,
                     tree=None):
        """
            Upload single 'file' of a 'representation' to 'provider'.
            Source url is taken from 'file' portion, where {root} placeholder
            is replaced by 'representation.Context.root'
            Provider could be one of implemented in provider.py.

            Updates MongoDB, fills in id of file from provider (ie. file_id
            from GDrive), 'created_dt' - time of upload

        Args:
            file (dictionary): of file from representation in Mongo
            representation (dictionary): of representation
            provider_name (string): gdrive, gdc etc.
            site_name (string): site on provider, single provider(gdrive) could
                have multiple sites (different accounts, credentials)
            tree (dictionary): injected memory structure for performance

        """
        # create ids sequentially, upload file in parallel later
        with self.lock:
            # this part modifies structure on 'remote_site', only single
            # thread can do that at a time, upload/download to prepared
            # structure should be run in parallel
            handler = lib.factory.get_provider(provider_name, site_name, tree)
            remote_file = self._get_remote_file_path(file,
                                                     handler.get_roots_config()
                                                     )
            local_root = representation.get("context", {}).get("root")
            local_file = self._get_local_file_path(file, local_root)

            target_folder = os.path.dirname(remote_file)
            folder_id = handler.create_folder(target_folder)

            if not folder_id:
                err = "Folder {} wasn't created. Check permissions.".\
                    format(target_folder)
                raise NotADirectoryError(err)

        loop = asyncio.get_running_loop()
        file_id = await loop.run_in_executor(None,
                                             handler.upload_file,
                                             local_file,
                                             remote_file,
                                             True)
        return file_id

    async def download(self, file, representation, provider_name,
                       site_name, tree=None):
        """
            Downloads file to local folder denoted in representation.Context.

        Args:
         file (dictionary) : info about processed file
         representation (dictionary):  repr that 'file' belongs to
         provider_name (string):  'gdrive' etc
         site_name (string): site on provider, single provider(gdrive) could
                have multiple sites (different accounts, credentials)
         tree (dictionary): injected memory structure for performance

        Returns:
            (string) - 'name' of local file
        """
        with self.lock:
            handler = lib.factory.get_provider(provider_name, site_name, tree)
            remote_file = self._get_remote_file_path(file,
                                                     handler.get_roots_config()
                                                     )
            local_root = representation.get("context", {}).get("root")
            local_file = self._get_local_file_path(file, local_root)

            local_folder = os.path.dirname(local_file)
            os.makedirs(local_folder, exist_ok=True)

        loop = asyncio.get_running_loop()
        file_id = await loop.run_in_executor(None,
                                             handler.download_file,
                                             remote_file,
                                             local_file,
                                             False)
        return file_id

    def update_db(self, new_file_id, file, representation, provider_name,
                  error=None):
        """
            Update 'provider' portion of records in DB with success (file_id)
            or error (exception)

        Args:
            new_file_id (string):
            file (dictionary): info about processed file (pulled from DB)
            representation (dictionary): parent repr of file (from DB)
            provider_name (string): label ('gdrive', 'S3')
            error (string): exception message

        Returns:
            None
        """
        representation_id = representation.get("_id")
        file_id = file.get("_id")
        query = {
            "_id": representation_id,
            "files._id": file_id
        }
        file_index, _ = self._get_file_info(representation.get('files', []),
                                            file_id)
        site_index, _ = self._get_provider_rec(file.get('sites', []),
                                               provider_name)
        update = {}
        if new_file_id:
            update["$set"] = self._get_success_dict(file_index, site_index,
                                                    new_file_id)
            # reset previous errors if any
            update["$unset"] = self._get_error_dict(file_index, site_index,
                                                    "", "")
        else:
            tries = self._get_tries_count(file, provider_name)
            tries += 1

            update["$set"] = self._get_error_dict(file_index, site_index,
                                                  error, tries)

        self.connection.update_one(
            query,
            update
        )

        status = 'failed'
        error_str = 'with error {}'.format(error)
        if new_file_id:
            status = 'succeeded with id {}'.format(new_file_id)
            error_str = ''

        source_file = file.get("path", "")
        log.debug("File {source_file} process {status} {error_str}".
                  format(status=status,
                         source_file=source_file,
                         error_str=error_str))

    def tray_start(self):
        """
            Triggered when Tray is started. Checks if configuration presets
            are available and if there is any provider ('gdrive', 'S3') that
            is activated (eg. has valid credentials).
        Returns:
            None
        """
        if self.presets and self.active_sites:
            self.sync_server_thread.start()
        else:
            log.debug("No presets or active providers. " +
                      "Synchronization not possible.")

    def tray_exit(self):
        self.stop()

    def thread_stopped(self):
        self._is_running = False

    @property
    def is_running(self):
        return self.sync_server_thread.is_running

    def stop(self):
        if not self.is_running:
            return
        try:
            log.debug("Stopping sync server server")
            self.sync_server_thread.is_running = False
            self.sync_server_thread.stop()
        except Exception:
            log.warning(
                "Error has happened during Killing sync server",
                exc_info=True
            )

    def _get_file_info(self, files, _id):
        """
            Return record from list of records which name matches to 'provider'
            Could be possibly refactored with '_get_file_info' together.

        Args:
            files (list): of dictionaries with info about published files
            _id (string): _id of specific file

        Returns:
            (int, dictionary): index from list and record with metadata
                               about site (if/when created, errors..)
            OR (-1, None) if not present
        """
        for index, rec in enumerate(files):
            if rec.get("_id") == _id:
                return index, rec

        return -1, None

    def _get_provider_rec(self, sites, provider):
        """
            Return record from list of records which name matches to 'provider'

        Args:
            sites (list): of dictionaries
            provider (string): 'local_XXX', 'gdrive'

        Returns:
            (int, dictionary): index from list and record with metadata
                               about site (if/when created, errors..)
            OR (-1, None) if not present
        """
        for index, rec in enumerate(sites):
            if rec.get("name") == provider:
                return index, rec

        return -1, None

    def reset_provider_for_file(self, collection, representation_id,
                                file_id, site_name):
        """
            Reset information about synchronization for particular 'file_id'
            and provider.
            Useful for testing or forcing file to be reuploaded.
        Args:
            collection (string): name of project (eg. collection) in DB
            representation_id(string): _id of representation
            file_id (string):  file _id in representation
            site_name (string): 'gdrive', 'S3' etc
        Returns:
            None
        """
        # TODO - implement reset for ALL files or ALL sites
        query = {
            "_id": io.ObjectId(representation_id)
        }
        self.connection.Session["AVALON_PROJECT"] = collection
        representation = list(self.connection.find(query))
        if not representation:
            raise ValueError("Representation {} not found in {}".
                             format(representation_id, collection))

        files = representation[0].get('files', [])
        file_index, _ = self._get_file_info(files,
                                            file_id)
        site_index, _ = self._get_provider_rec(files[file_index].
                                               get('sites', []),
                                               site_name)
        if file_index > 0 and site_index > 0:
            elem = {"name": site_name}
            update = {
                "$set": {"files.{}.sites.{}".format(file_index, site_index):
                         elem
                         }
            }

            self.connection.update_one(
                query,
                update
            )

    def get_loop_delay(self):
        """
            Return count of seconds before next synchronization loop starts
            after finish of previous loop.
        Returns:
            (int): in seconds
        """
        return self.presets["loop_delay"]

    def _get_success_dict(self, file_index, site_index, new_file_id):
        """
            Provide success metadata ("id", "created_dt") to be stored in Db.
            Used in $set: "DICT" part of query.
            Sites are array inside of array(file), so real indexes for both
            file and site are needed for upgrade in DB.
        Args:
            file_index: (int) - index of modified file
            site_index: (int) - index of modified site of modified file
            new_file_id: id of created file
        Returns:
            (dictionary)
        """
        val = {"files.{}.sites.{}.id".format(file_index, site_index):
               new_file_id,
               "files.{}.sites.{}.created_dt".format(file_index, site_index):
               datetime.utcnow()}
        return val

    def _get_error_dict(self, file_index, site_index, error="", tries=""):
        """
            Provide error metadata to be stored in Db.
            Used for set (error and tries provided) or unset mode.
        Args:
            file_index: (int) - index of modified file
            site_index: (int) - index of modified site of modified file
            error: (string) - message
            tries: how many times failed
        Returns:
            (dictionary)
        """
        val = {"files.{}.sites.{}.last_failed_dt".
               format(file_index, site_index): datetime.utcnow(),
               "files.{}.sites.{}.error".format(file_index, site_index): error,
               "files.{}.sites.{}.tries".format(file_index, site_index): tries
               }
        return val

    def _get_tries_count_from_rec(self, rec):
        """
            Get number of failed attempts to sync from site record
        Args:
            rec (dictionary): info about specific site record
        Returns:
            (int) - number of failed attempts
        """
        if not rec:
            return 0
        return rec.get("tries", 0)

    def _get_tries_count(self, file, provider):
        """
            Get number of failed attempts to sync
        Args:
            file (dictionary): info about specific file
            provider (string): name of site ('gdrive' or specific user site)
        Returns:
            (int) - number of failed attempts
        """
        _, rec = self._get_provider_rec(file.get("sites", []), provider)
        return rec.get("tries", 0)

    def _get_local_file_path(self, file, local_root):
        """
            Auxiliary function for replacing rootless path with real path

        Args:
            file (dictionary): file info, get 'path' to file with {root}
            local_root (string): value of {root} for local projects

        Returns:
            (string) - absolute path on local system
        """
        if not local_root:
            raise ValueError("Unknown local root for file {}")
        path = file.get("path", "")

        return path.format(**{"root": local_root})

    def _get_remote_file_path(self, file, root_config):
        """
            Auxiliary function for replacing rootless path with real path
        Args:
            file (dictionary): file info, get 'path' to file with {root}
            root_config (dict): value of {root} for remote location

        Returns:
            (string) - absolute path on remote location
        """
        path = file.get("path", "")
        if not root_config.get("root"):
            root_config = {"root": root_config}
        path = path.format(**root_config)
        return path

    def _get_retries_arr(self):
        """
            Returns array with allowed values in 'tries' field. If repre
            contains these values, it means it was tried to be synchronized
            but failed. We try up to 'self.presets["retry_cnt"]' times before
            giving up and skipping representation.
        Returns:
            (list)
        """
        arr = [i for i in range(self.presets["retry_cnt"])]
        arr.append(None)

        return arr


class SyncServerThread(threading.Thread):
    """
        Separate thread running synchronization server with asyncio loop.
        Stopped when tray is closed.
    """
    def __init__(self, module):
        super(SyncServerThread, self).__init__()
        self.module = module
        self.loop = None
        self.is_running = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    def run(self):
        self.is_running = True

        try:
            log.info("Starting Sync Server")
            self.loop = asyncio.new_event_loop()  # create new loop for thread
            asyncio.set_event_loop(self.loop)
            self.loop.set_default_executor(self.executor)

            asyncio.ensure_future(self.check_shutdown(), loop=self.loop)
            asyncio.ensure_future(self.sync_loop(), loop=self.loop)
            self.loop.run_forever()
        except Exception:
            log.warning(
                "Sync Server service has failed", exc_info=True
            )
        finally:
            self.loop.close()  # optional

    async def sync_loop(self):
        """
            Runs permanently, each time:
                - gets list of collections in DB
                - gets list of active remote providers (has configuration,
                    credentials)
                - for each collection it looks for representations that should
                    be synced
                - synchronize found collections
                - update representations - fills error messages for exceptions
                - waits X seconds and repeat
        Returns:

        """
        try:
            while self.is_running:
                import time
                start_time = None
                for collection in self.module.get_collections():
                    start_time = time.time()
                    sync_repres = self.module.get_sync_representations(
                        collection,
                        self.module.active_site,
                        self.module.remote_site
                    )

                    local = self.module.active_site
                    task_files_to_process = []
                    files_processed_info = []
                    # process only unique file paths in one batch
                    # multiple representation could have same file path
                    # (textures),
                    # upload process can find already uploaded file and
                    # reuse same id
                    processed_file_path = set()
                    for active_site in self.module.active_sites:
                        provider, site = active_site
                        handler = lib.factory.get_provider(provider, site)
                        limit = lib.factory.get_provider_batch_limit(provider)
                        # first call to get_provider could be expensive, its
                        # building folder tree structure in memory
                        # call only if needed, eg. DO_UPLOAD or DO_DOWNLOAD
                        for sync in sync_repres:
                            if limit <= 0:
                                continue
                            files = sync.get("files") or []
                            if files:
                                for file in files:
                                    # skip already processed files
                                    file_path = file.get('path', '')
                                    if file_path in processed_file_path:
                                        continue

                                    status = self.module.check_status(file,
                                                                      provider)
                                    if status == SyncStatus.DO_UPLOAD:
                                        tree = handler.get_tree()
                                        limit -= 1
                                        task = asyncio.create_task(
                                            self.module.upload(file,
                                                               sync,
                                                               provider,
                                                               site,
                                                               tree))
                                        task_files_to_process.append(task)
                                        # store info for exception handling
                                        files_processed_info.append((file,
                                                                     sync,
                                                                     site))
                                        processed_file_path.add(file_path)
                                    if status == SyncStatus.DO_DOWNLOAD:
                                        tree = handler.get_tree()
                                        limit -= 1
                                        task = asyncio.create_task(
                                                self.module.download(file,
                                                                     sync,
                                                                     provider,
                                                                     site,
                                                                     tree))
                                        task_files_to_process.append(task)

                                        files_processed_info.append((file,
                                                                     sync,
                                                                     local))
                                        processed_file_path.add(file_path)

                    log.debug("Sync tasks count {}".
                              format(len(task_files_to_process)))
                    files_created = await asyncio.gather(
                        *task_files_to_process,
                        return_exceptions=True)
                    for file_id, info in zip(files_created,
                                             files_processed_info):
                        file, representation, site = info
                        error = None
                        if isinstance(file_id, BaseException):
                            error = str(file_id)
                            file_id = None
                        self.module.update_db(file_id,
                                              file,
                                              representation,
                                              site,
                                              error)

                duration = time.time() - start_time
                log.debug("One loop took {:.2f}s".format(duration))
                await asyncio.sleep(self.module.get_loop_delay())
        except ConnectionResetError:
            log.warning("ConnectionResetError in sync loop, trying next loop",
                        exc_info=True)
        except CancelledError:
            # just stopping server
            pass
        except Exception:
            self.stop()
            log.warning("Unhandled exception in sync loop, stopping server",
                        exc_info=True)

    def stop(self):
        """Sets is_running flag to false, 'check_shutdown' shuts server down"""
        self.is_running = False

    async def check_shutdown(self):
        """ Future that is running and checks if server should be running
            periodically.
        """
        while self.is_running:
            await asyncio.sleep(0.5)
        tasks = [task for task in asyncio.all_tasks() if
                 task is not asyncio.current_task()]
        list(map(lambda task: task.cancel(), tasks))  # cancel all the tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        log.debug(f'Finished awaiting cancelled tasks, results: {results}...')
        await self.loop.shutdown_asyncgens()
        # to really make sure everything else has time to stop
        self.executor.shutdown(wait=True)
        await asyncio.sleep(0.07)
        self.loop.stop()
