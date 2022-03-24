import os
import logging
import sys
import copy
import clique
import errno
import six

from bson.objectid import ObjectId
from pymongo import DeleteOne, InsertOne, UpdateOne
import pyblish.api
from avalon import io
import openpype.api
from datetime import datetime
from openpype.lib.profiles_filtering import filter_profiles
from openpype.lib import (
    prepare_template_data,
    create_hard_link,
    StringTemplate,
    TemplateUnsolved
)

# this is needed until speedcopy for linux is fixed
if sys.platform == "win32":
    from speedcopy import copyfile
else:
    from shutil import copyfile

log = logging.getLogger(__name__)


def get_frame_padded(frame, padding):
    """Return frame number as string with `padding` amount of padded zeros"""
    return "{frame:0{padding}d}".format(padding=padding, frame=frame)


def get_first_frame_padded(collection):
    """Return first frame as padded number from `clique.Collection`"""
    start_frame = next(iter(collection.indexes))
    return get_frame_padded(start_frame, padding=collection.padding)


class FileTransaction(object):
    """

    The file transaction is a three step process.

    1) Rename any existing files to a "temporary backup" during `process()`
    2) Copy the files to final destination during `process()`
    3) Remove any backed up files (*no rollback possible!) during `finalize()`

    Step 3 is done during `finalize()`. If not called the .bak files will
    remain on disk.

    These steps try to ensure that we don't overwrite half of any existing
    files e.g. if they are currently in use.

    Note:
        A regular filesystem is *not* a transactional file system and even
        though this implementation tries to produce a 'safe copy' with a
        potential rollback do keep in mind that it's inherently unsafe due
        to how filesystem works and a myriad of things could happen during
        the transaction that break the logic. A file storage could go down,
        permissions could be changed, other machines could be moving or writing
        files. A lot can happen.

    Warning:
        Any folders created during the transfer will not be removed.

    """

    MODE_COPY = 0
    MODE_HARDLINK = 1

    def __init__(self, log=None):

        if log is None:
            log = logging.getLogger("FileTransaction")

        self.log = log

        # The transfer queue
        # todo: make this an actual FIFO queue?
        self._transfers = {}

        # Destination file paths that a file was transferred to
        self._transferred = []

        # Backup file location mapping to original locations
        self._backup_to_original = {}

    def add(self, src, dst, mode=MODE_COPY):
        """Add a new file to transfer queue"""
        opts = {"mode": mode}

        src = os.path.normpath(src)
        dst = os.path.normpath(dst)

        if dst in self._transfers:
            queued_src = self._transfers[dst][0]
            if src == queued_src:
                self.log.debug("File transfer was already "
                               "in queue: {} -> {}".format(src, dst))
                return
            else:
                self.log.warning("File transfer in queue replaced..")
                self.log.debug("Removed from queue: "
                               "{} -> {}".format(queued_src, dst))
                self.log.debug("Added to queue: {} -> {}".format(src, dst))

        self._transfers[dst] = (src, opts)

    def process(self):

        # Backup any existing files
        for dst in self._transfers.keys():
            if os.path.exists(dst):
                # Backup original file
                # todo: add timestamp or uuid to ensure unique
                backup = dst + ".bak"
                self._backup_to_original[backup] = dst
                self.log.debug("Backup existing file: "
                               "{} -> {}".format(dst, backup))
                os.rename(dst, backup)

        # Copy the files to transfer
        for dst, (src, opts) in self._transfers.items():
            self._create_folder_for_file(dst)

            if opts["mode"] == self.MODE_COPY:
                self.log.debug("Copying file ... {} -> {}".format(src, dst))
                copyfile(src, dst)
            elif opts["mode"] == self.MODE_HARDLINK:
                self.log.debug("Hardlinking file ... {} -> {}".format(src,
                                                                      dst))
                create_hard_link(src, dst)

            self._transferred.append(dst)

    def finalize(self):
        # Delete any backed up files
        for backup in self._backup_to_original.keys():
            try:
                os.remove(backup)
            except OSError:
                self.log.error("Failed to remove backup file: "
                               "{}".format(backup),
                               exc_info=True)

    def rollback(self):

        errors = 0

        # Rollback any transferred files
        for path in self._transferred:
            try:
                os.remove(path)
            except OSError:
                errors += 1
                self.log.error("Failed to rollback created file: "
                               "{}".format(path),
                               exc_info=True)

        # Rollback the backups
        for backup, original in self._backup_to_original.items():
            try:
                os.rename(backup, original)
            except OSError:
                errors += 1
                self.log.error("Failed to restore original file: "
                               "{} -> {}".format(backup, original),
                               exc_info=True)

        if errors:
            self.log.error("{} errors occurred during "
                           "rollback.".format(errors), exc_info=True)
            six.reraise(*sys.exc_info())

    @property
    def transferred(self):
        """Return the processed transfers destination paths"""
        return list(self._transferred)

    @property
    def backups(self):
        """Return the backup file paths"""
        return list(self._backup_to_original.keys())

    def _create_folder_for_file(self, path):
        dirname = os.path.dirname(path)
        try:
            os.makedirs(dirname)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                self.log.critical("An unexpected error occurred.")
                six.reraise(*sys.exc_info())


class IntegrateAssetNew(pyblish.api.InstancePlugin):
    """Resolve any dependency issues

    This plug-in resolves any paths which, if not updated might break
    the published file.

    The order of families is important, when working with lookdev you want to
    first publish the texture, update the texture paths in the nodes and then
    publish the shading network. Same goes for file dependent assets.

    Requirements for instance to be correctly integrated

    instance.data['representations'] - must be a list and each member
    must be a dictionary with following data:
        'files': list of filenames for sequence, string for single file.
                 Only the filename is allowed, without the folder path.
        'stagingDir': "path/to/folder/with/files"
        'name': representation name (usually the same as extension)
        'ext': file extension
    optional data
        "frameStart"
        "frameEnd"
        'fps'
        "data": additional metadata for each representation.
    """

    label = "Integrate Asset New"
    order = pyblish.api.IntegratorOrder
    families = ["workfile",
                "pointcache",
                "camera",
                "animation",
                "model",
                "mayaAscii",
                "mayaScene",
                "setdress",
                "layout",
                "ass",
                "vdbcache",
                "scene",
                "vrayproxy",
                "vrayscene_layer",
                "render",
                "prerender",
                "imagesequence",
                "review",
                "rendersetup",
                "rig",
                "plate",
                "look",
                "audio",
                "yetiRig",
                "yeticache",
                "nukenodes",
                "gizmo",
                "source",
                "matchmove",
                "image",
                "source",
                "assembly",
                "fbx",
                "textures",
                "action",
                "harmony.template",
                "harmony.palette",
                "editorial",
                "background",
                "camerarig",
                "redshiftproxy",
                "effect",
                "xgen",
                "hda",
                "usd"
                ]
    exclude_families = ["clip"]
    db_representation_context_keys = [
        "project", "asset", "task", "subset", "version", "representation",
        "family", "hierarchy", "task", "username", "frame"
    ]
    default_template_name = "publish"

    # Attributes set by settings
    template_name_profiles = None
    subset_grouping_profiles = None

    def process(self, instance):

        # Exclude instances that also contain families from exclude families
        families = set(self._get_instance_families(instance))
        if families & set(self.exclude_families):
            return

        # TODO: Avoid the need to do any adjustments to anatomy data
        #       Best case scenario that's all handled by collectors
        self.prepare_anatomy(instance)

        file_transactions = FileTransaction(log=self.log)
        try:
            self.register(instance, file_transactions)
        except Exception:
            # clean destination
            # todo: rollback any registered entities? (or how safe are we?)
            file_transactions.rollback()
            self.log.critical("Error when registering", exc_info=True)
            six.reraise(*sys.exc_info())

        # Finalizing can't rollback safely so no use for moving it to
        # the try, except.
        file_transactions.finalize()

    def prepare_anatomy(self, instance):
        """Prepare anatomy data used to define representation destinations"""
        # TODO: This logic should move to CollectAnatomyContextData
        intent_value = instance.context.data.get("intent")
        if intent_value and isinstance(intent_value, dict):
            intent_value = intent_value.get("value")
            if intent_value:
                instance.data["anatomyData"]["intent"] = intent_value

    def get_profile_filter_criteria(self, instance):
        """Return filter criteria for `filter_profiles`"""
        # Anatomy data is pre-filled by Collectors
        anatomy_data = instance.data["anatomyData"]

        # Task can be optional in anatomy data
        task = anatomy_data.get("task", {})

        # Return filter criteria
        return {
            "families": anatomy_data["family"],
            "tasks": task.get("name"),
            "hosts": anatomy_data["app"],
            "task_types": task.get("type")
        }

    def register(self, instance, file_transactions):

        instance_stagingdir = instance.data.get("stagingDir")
        if not instance_stagingdir:
            self.log.info((
                "{0} is missing reference to staging directory."
                " Will try to get it from representation."
            ).format(instance))

        else:
            self.log.debug(
                "Establishing staging directory "
                "@ {0}".format(instance_stagingdir)
            )

        # Ensure at least one file is set up for transfer in staging dir.
        repres = instance.data.get("representations")
        assert repres, "Instance has no files to transfer"
        assert isinstance(repres, (list, tuple)), (
            "Instance 'files' must be a list, got: {0} {1}".format(
                str(type(repres)), str(repres)
            )
        )

        # Define publish template name from profiles
        filter_criteria = self.get_profile_filter_criteria(instance)
        profile = filter_profiles(self.template_name_profiles,
                                  filter_criteria,
                                  logger=self.log)
        template_name = "publish"
        if profile:
            template_name = profile["template_name"]

        subset = self.register_subset(instance)

        version = self.register_version(instance, subset)
        instance.data["versionEntity"] = version

        archived_repres = list(io.find({
            "parent": version["_id"],
            "type": "archived_representation"
        }))

        # Prepare all representations
        prepared_representations = []
        for repre in instance.data["representations"]:

            if "delete" in repre.get("tags", []):
                self.log.debug("Skipping representation marked for deletion: "
                               "{}".format(repre))
                continue

            # todo: reduce/simplify what is returned from this function
            prepared = self.prepare_representation(repre,
                                                   template_name,
                                                   archived_repres,
                                                   version,
                                                   instance_stagingdir,
                                                   instance)

            for src, dst in prepared["transfers"]:
                # todo: add support for hardlink transfers
                file_transactions.add(src, dst)

            prepared_representations.append(prepared)

        # Each instance can also have pre-defined transfers not explicitly
        # part of a representation - like texture resources used by a
        # .ma representation. Those destination paths are pre-defined, etc.
        # todo: should we move or simplify this logic?
        for src, dst in instance.data.get("transfers", []):
            file_transactions.add(src, dst, mode=FileTransaction.MODE_COPY)
        for src, dst in instance.data.get("hardlinks", []):
            file_transactions.add(src, dst, mode=FileTransaction.MODE_HARDLINK)

        # Process all file transfers of all integrations now
        self.log.debug("Integrating source files to destination ...")
        file_transactions.process()
        self.log.debug("Backup files "
                       "{}".format(file_transactions.backups))
        self.log.debug("Integrated files "
                       "{}".format(file_transactions.transferred))

        # Finalize the representations now the published files are integrated
        # Get 'files' info for representations and its attached resources
        self.log.debug("Retrieving Representation files information ...")
        sites = self.compute_resource_sync_sites(instance)
        anatomy = instance.context.data["anatomy"]
        representations = []
        for prepared in prepared_representations:
            transfers = prepared["transfers"]
            representation = prepared["representation"]
            representation["files"] = self.get_files_info(
                transfers, sites, anatomy
            )
            representations.append(representation)

        # Remove all archived representations
        if archived_repres:
            repre_ids_to_remove = [repre["_id"] for repre in archived_repres]
            io.delete_many({"_id": {"$in": repre_ids_to_remove}})

        # Write the new representations to the database
        io.insert_many(representations)

        # Backwards compatibility
        # todo: can we avoid the need to store this?
        instance.data["published_representations"] = {
            p["representation"]["_id"]: p for p in prepared_representations
        }

        self.log.info("Registered {} representations"
                      "".format(len(representations)))

    def register_version(self, instance, subset):

        version_number = instance.data["version"]
        self.log.debug("Version: v{0:03d}".format(version_number))

        version = {
            "schema": "openpype:version-3.0",
            "type": "version",
            "parent": subset["_id"],
            "name": version_number,
            "data": self.create_version_data(instance)
        }

        existing_version = io.find_one({
            'type': 'version',
            'parent': subset["_id"],
            'name': version_number
        })

        bulk_writes = []
        if existing_version is None:
            self.log.debug("Creating new version ...")
            version["_id"] = ObjectId()
            bulk_writes.append(InsertOne(version))
        else:
            self.log.debug("Updating existing version ...")
            # Check if instance have set `append` mode which cause that
            # only replicated representations are set to archive
            append_repres = instance.data.get("append", False)

            # Update version data
            version_id = existing_version['_id']
            bulk_writes.append(UpdateOne({
                '_id': version_id
            }, {
                '$set': version
            }))

            # Instead of directly writing and querying we reproduce what
            # the resulting version would look like so we can hold off making
            # changes to the database to avoid the need for 'rollback'
            version = copy.deepcopy(version)
            version["_id"] = existing_version["_id"]

            # Find representations of existing version and archive them
            repres = instance.data.get("representations", [])
            new_repre_names_low = [_repre["name"].lower() for _repre in repres]
            current_repres = io.find({
                "type": "representation",
                "parent": version_id
            })
            for repre in current_repres:
                if append_repres:
                    # archive only duplicated representations
                    if repre["name"].lower() not in new_repre_names_low:
                        continue
                # Representation must change type,
                # `_id` must be stored to other key and replaced with new
                # - that is because new representations should have same ID
                repre_id = repre["_id"]
                bulk_writes.append(DeleteOne({"_id": repre_id}))

                repre["orig_id"] = repre_id
                repre["_id"] = ObjectId()
                repre["type"] = "archived_representation"
                bulk_writes.append(InsertOne(repre))

        # bulk updates
        # todo: Try to avoid writing already until after we've prepared
        #       representations to allow easier rollback?
        io._database[io.Session["AVALON_PROJECT"]].bulk_write(
            bulk_writes
        )

        self.log.info("Registered version: v{0:03d}".format(version["name"]))

        return version

    def prepare_representation(self, repre,
                               template_name,
                               archived_repres,
                               version,
                               instance_stagingdir,
                               instance):

        # pre-flight validations
        if repre["ext"].startswith("."):
            raise ValueError("Extension must not start with a dot '.': "
                             "{}".format(repre["ext"]))

        if repre.get("transfers"):
            raise ValueError("Representation is not allowed to have transfers"
                             "data before integration. They are computed in "
                             "the integrator"
                             "Got: {}".format(repre["transfers"]))

        # create template data for Anatomy
        template_data = copy.deepcopy(instance.data["anatomyData"])

        # required representation keys
        files = repre['files']
        template_data["representation"] = repre["name"]
        template_data["ext"] = repre["ext"]

        # optionals
        # retrieve additional anatomy data from representation if exists
        for representation_key, anatomy_key in {
            # Representation Key: Anatomy data key
            "resolutionWidth": "resolution_width",
            "resolutionHeight": "resolution_height",
            "fps": "fps",
            "outputName": "output",
        }.items():
            value = repre.get(representation_key)
            if value:
                template_data[anatomy_key] = value

        if repre.get('stagingDir'):
            stagingdir = repre['stagingDir']
        else:
            # Fall back to instance staging dir if not explicitly
            # set for representation in the instance
            self.log.debug("Representation uses instance staging dir: "
                           "{}".format(instance_stagingdir))
            stagingdir = instance_stagingdir
        if not stagingdir:
            raise ValueError("No staging directory set for representation: "
                             "{}".format(repre))

        self.log.debug("Anatomy template name: {}".format(template_name))
        anatomy = instance.context.data['anatomy']
        template = os.path.normpath(anatomy.templates[template_name]["path"])

        is_sequence_representation = isinstance(files, (list, tuple))
        if is_sequence_representation:
            # Collection of files (sequence)
            # Get the sequence as a collection. The files must be of a single
            # sequence and have no remainder outside of the collections.
            collections, remainder = clique.assemble(files,
                                                     minimum_items=1)
            if not collections:
                raise ValueError("No collections found in files: "
                                 "{}".format(files))
            if remainder:
                raise ValueError("Files found not detected as part"
                                 " of a sequence: {}".format(remainder))
            if len(collections) > 1:
                raise ValueError("Files in sequence are not part of a"
                                 " single sequence collection: "
                                 "{}".format(collections))
            src_collection = collections[0]

            # If the representation has `frameStart` set it renumbers the
            # frame indices of the published collection. It will start from
            # that `frameStart` index instead. Thus if that frame start
            # differs from the collection we want to shift the destination
            # frame indices from the source collection.
            destination_indexes = list(src_collection.indexes)
            destination_padding = len(get_first_frame_padded(src_collection))
            if repre.get("frameStart") is not None:
                index_frame_start = int(repre.get("frameStart"))

                # TODO use frame padding from right template group
                render_template = anatomy.templates["render"]
                frame_start_padding = int(
                    render_template.get(
                        "frame_padding",
                        render_template.get("padding")
                    )
                )

                # Shift destination sequence to the start frame
                src_start_frame = next(iter(src_collection.indexes))
                shift = index_frame_start - src_start_frame
                if shift:
                    destination_indexes = [
                        frame + shift for frame in destination_indexes
                    ]
                destination_padding = frame_start_padding

            # To construct the destination template with anatomy we require
            # a Frame or UDIM tile set for the template data. We use the first
            # index of the destination for that because that could've shifted
            # from the source indexes, etc.
            first_index_padded = get_frame_padded(frame=destination_indexes[0],
                                                  padding=destination_padding)
            if repre.get("udim"):
                # UDIM representations handle ranges in a different manner
                template_data["udim"] = first_index_padded
            else:
                template_data["frame"] = first_index_padded

            # Construct destination collection from template
            anatomy_filled = anatomy.format(template_data)
            template_filled = anatomy_filled[template_name]["path"]
            repre_context = template_filled.used_values
            self.log.debug("Template filled: {}".format(str(template_filled)))
            dst_collections, _remainder = clique.assemble(
                [os.path.normpath(template_filled)], minimum_items=1
            )
            assert not _remainder, "This is a bug"
            assert len(dst_collections) == 1, "This is a bug"
            dst_collection = dst_collections[0]

            # Update the destination indexes and padding
            dst_collection.indexes = destination_indexes
            dst_collection.padding = destination_padding
            assert len(src_collection) == len(dst_collection), "This is a bug"

            # Multiple file transfers
            transfers = []
            for src_file_name, dst in zip(src_collection, dst_collection):
                src = os.path.join(stagingdir, src_file_name)
                transfers.append((src, dst))

        else:
            # Single file
            template_data.pop("frame", None)
            fname = files
            assert not os.path.isabs(fname), (
                "Given file name is a full path"
            )
            # Store used frame value to template data
            if repre.get("udim"):
                template_data["udim"] = repre["udim"][0]
            src = os.path.join(stagingdir, fname)
            anatomy_filled = anatomy.format(template_data)
            template_filled = anatomy_filled[template_name]["path"]
            repre_context = template_filled.used_values
            dst = os.path.normpath(template_filled)

            # Single file transfer
            transfers = [(src, dst)]

        for key in self.db_representation_context_keys:
            value = template_data.get(key)
            if not value:
                continue
            repre_context[key] = template_data[key]

        # Explicitly store the full list even though template data might
        # have a different value
        if repre.get("udim"):
            repre_context["udim"] = repre.get("udim")  # store list

        # Define representation id
        repre_id = ObjectId()

        # Use previous representation's id if there is a name match
        repre_name_lower = repre["name"].lower()
        for _archived_repres in archived_repres:
            if repre_name_lower == _archived_repres["name"].lower():
                repre_id = _archived_repres["orig_id"]
                break

        # Backwards compatibility:
        # Store first transferred destination as published path data
        # todo: can we remove this?
        published_path = transfers[0][1]

        # todo: `repre` is not the actual `representation` entity
        #       we should simplify/clarify difference between data above
        #       and the actual representation entity for the database
        data = repre.get("data") or {}
        data.update({'path': published_path, 'template': template})
        representation = {
            "_id": repre_id,
            "schema": "openpype:representation-2.0",
            "type": "representation",
            "parent": version["_id"],
            "name": repre['name'],
            "data": data,
            "dependencies": instance.data.get("dependencies", "").split(),

            # Imprint shortcut to context for performance reasons.
            "context": repre_context
        }

        # todo: simplify/streamline which additional data makes its way into
        #       the representation context
        if repre.get("outputName"):
            representation["context"]["output"] = repre['outputName']

        if is_sequence_representation and repre.get("frameStart") is not None:
            representation['context']['frame'] = template_data["frame"]

        return {
            "representation": representation,
            "anatomy_data": template_data,
            "transfers": transfers,
            # todo: avoid the need for 'published_files' used by Integrate Hero
            # backwards compatibility
            "published_files": [transfer[1] for transfer in transfers]
        }

    def _get_instance_families(self, instance):
        """Get all families of the instance"""
        # todo: move this to lib?
        family = instance.data.get("family")
        families = []
        if family:
            families.append(family)

        for _family in (instance.data.get("families") or []):
            if _family not in families:
                families.append(_family)

        return families

    def register_subset(self, instance):
        asset = instance.data.get("assetEntity")
        subset_name = instance.data["subset"]
        self.log.debug("Subset: {}".format(subset_name))

        subset = io.find_one({
            "type": "subset",
            "parent": asset["_id"],
            "name": subset_name
        })

        families = self._get_instance_families(instance)
        if subset is None:
            self.log.info("Subset '%s' not found, creating ..." % subset_name)

            _id = io.insert_one({
                "schema": "openpype:subset-3.0",
                "type": "subset",
                "name": subset_name,
                "data": {
                    "families": families
                },
                "parent": asset["_id"]
            }).inserted_id

            subset = io.find_one({"_id": _id})

        # Update subset group
        self._set_subset_group(instance, subset["_id"])

        # Update families on subset.
        io.update_many(
            {"type": "subset", "_id": ObjectId(subset["_id"])},
            {"$set": {"data.families": families}}
        )

        self.log.info("Registered subset: {}".format(subset_name))

        return subset

    def _set_subset_group(self, instance, subset_id):
        """
            Mark subset as belonging to group in DB.

            Uses Settings > Global > Publish plugins > IntegrateAssetNew

            Args:
                instance (dict): processed instance
                subset_id (str): DB's subset _id

        """
        # Fist look into instance data
        subset_group = instance.data.get("subsetGroup")
        if not subset_group:
            subset_group = self._get_subset_group(instance)

        if subset_group:
            io.update_many({
                'type': 'subset',
                '_id': ObjectId(subset_id)
            }, {'$set': {'data.subsetGroup': subset_group}})

    def _get_subset_group(self, instance):
        """Look into subset group profiles set by settings.

        Attribute 'subset_grouping_profiles' is defined by OpenPype settings.
        """
        # TODO: This logic is better suited for a Collector to just store
        #       instance.data["subsetGroup"]
        # Skip if 'subset_grouping_profiles' is empty
        if not self.subset_grouping_profiles:
            return None

        # Skip if there is no matching profile
        filter_criteria = self.get_profile_filter_criteria(instance)
        profile = filter_profiles(self.subset_grouping_profiles,
                                  filter_criteria,
                                  logger=self.log)
        if not profile:
            return None

        template = profile["template"]

        fill_pairs = prepare_template_data({
            "family": filter_criteria["families"],
            "task": filter_criteria["tasks"],
            "host": filter_criteria["hosts"],
            "subset": instance.data["subset"],
            "renderlayer": instance.data.get("renderlayer")
        })

        filled_template = None
        try:
            filled_template = StringTemplate.format_strict_template(
                template, fill_pairs
            )
        except (KeyError, TemplateUnsolved):
            keys = fill_pairs.keys()
            msg = "Subset grouping failed. " \
                  "Only {} are expected in Settings".format(','.join(keys))
            self.log.warning(msg)

        return filled_template

    def create_version_data(self, instance):
        """Create the data collection for the version

        Args:
            instance: the current instance being published

        Returns:
            dict: the required information with instance.data as key
        """

        context = instance.context

        # create relative source path for DB
        if "source" in instance.data:
            source = instance.data["source"]
        else:
            source = context.data["currentFile"]
            anatomy = instance.context.data["anatomy"]
            source = self.get_rootless_path(anatomy, source)
        self.log.debug("Source: {}".format(source))

        version_data = {
            "families": self._get_instance_families(instance),
            "time": context.data["time"],
            "author": context.data["user"],
            "source": source,
            "comment": context.data.get("comment"),
            "machine": context.data.get("machine"),
            "fps": context.data.get(
                "fps", instance.data.get("fps")
            )
        }

        intent_value = context.data.get("intent")
        if intent_value and isinstance(intent_value, dict):
            intent_value = intent_value.get("value")

        if intent_value:
            version_data["intent"] = intent_value

        # Include optional data if present in
        optionals = [
            "frameStart", "frameEnd", "step", "handles",
            "handleEnd", "handleStart", "sourceHashes"
        ]
        for key in optionals:
            if key in instance.data:
                version_data[key] = instance.data[key]

        # Include instance.data[versionData] directly
        version_data_instance = instance.data.get('versionData')
        if version_data_instance:
            version_data.update(version_data_instance)

        return version_data

    def main_family_from_instance(self, instance):
        """Returns main family of entered instance."""
        return self._get_instance_families(instance)[0]

    def get_rootless_path(self, anatomy, path):
        """  Returns, if possible, path without absolute portion from host
             (eg. 'c:\' or '/opt/..')
             This information is host dependent and shouldn't be captured.
             Example:
                 'c:/projects/MyProject1/Assets/publish...' >
                 '{root}/MyProject1/Assets...'

        Args:
                anatomy: anatomy part from instance
                path: path (absolute)
        Returns:
                path: modified path if possible, or unmodified path
                + warning logged
        """
        success, rootless_path = (
            anatomy.find_root_template_from_path(path)
        )
        if success:
            path = rootless_path
        else:
            self.log.warning((
                "Could not find root path for remapping \"{}\"."
                " This may cause issues on farm."
            ).format(path))
        return path

    def get_files_info(self, transfers, sites, anatomy):
        """ Prepare 'files' portion for attached resources and main asset.
            Combining records from 'transfers' and 'hardlinks' parts from
            instance.
            All attached resources should be added, currently without
            Context info.

        Arguments:
            instance: the current instance being published
            integrated_file_sizes: dictionary of destination path (absolute)
            and its file size
        Returns:
            output_resources: array of dictionaries to be added to 'files' key
            in representation
        """
        file_infos = []
        for _src, dest in transfers:
            file_info = self.prepare_file_info(dest, anatomy, sites=sites)
            file_infos.append(file_info)

        return file_infos

    def prepare_file_info(self, path, anatomy, sites):
        """ Prepare information for one file (asset or resource)

        Arguments:
            path: destination url of published file (rootless)
            size(optional): size of file in bytes
            file_hash(optional): hash of file for synchronization validation
            sites(optional): array of published locations,
                            [ {'name':'studio', 'created_dt':date} by default
                                keys expected ['studio', 'site1', 'gdrive1']
        Returns:
            rec: dictionary with filled info
        """
        file_hash = openpype.api.source_hash(path)

        return {
            "_id": ObjectId(),
            "path": self.get_rootless_path(anatomy, path),
            "size": os.path.getsize(path),
            "hash": file_hash,
            "sites": sites
        }

    # region sync sites
    def compute_resource_sync_sites(self, instance):
        """Get available resource sync sites"""
        # Sync server logic
        # TODO: Clean up sync settings
        local_site = 'studio'  # default
        remote_site = None
        always_accessible = []
        sync_project_presets = None

        system_sync_server_presets = (
            instance.context.data["system_settings"]
                                 ["modules"]
                                 ["sync_server"])
        log.debug("system_sett:: {}".format(system_sync_server_presets))

        if system_sync_server_presets["enabled"]:
            sync_project_presets = (
                instance.context.data["project_settings"]
                                     ["global"]
                                     ["sync_server"])

        if sync_project_presets and sync_project_presets["enabled"]:
            local_site, remote_site = self._get_sites(sync_project_presets)
            always_accessible = sync_project_presets["config"]. \
                get("always_accessible_on", [])

        already_attached_sites = {}
        meta = {"name": local_site, "created_dt": datetime.now()}
        sites = [meta]
        already_attached_sites[meta["name"]] = meta["created_dt"]

        if sync_project_presets and sync_project_presets["enabled"]:
            if remote_site and \
                    remote_site not in already_attached_sites.keys():
                # add remote
                meta = {"name": remote_site.strip()}
                sites.append(meta)
                already_attached_sites[meta["name"]] = None

            # add skeleton for site where it should be always synced to
            for always_on_site in always_accessible:
                if always_on_site not in already_attached_sites.keys():
                    meta = {"name": always_on_site.strip()}
                    sites.append(meta)
                    already_attached_sites[meta["name"]] = None

            # add alternative sites
            alt = self._add_alternative_sites(system_sync_server_presets,
                                              already_attached_sites)
            sites.extend(alt)

        log.debug("final sites:: {}".format(sites))

        return sites

    def _get_sites(self, sync_project_presets):
        """Returns tuple (local_site, remote_site)"""
        local_site_id = openpype.api.get_local_site_id()
        local_site = sync_project_presets["config"]. \
            get("active_site", "studio").strip()

        if local_site == 'local':
            local_site = local_site_id

        remote_site = sync_project_presets["config"].get("remote_site")

        if remote_site == 'local':
            remote_site = local_site_id

        return local_site, remote_site

    def _add_alternative_sites(self,
                               system_sync_server_presets,
                               already_attached_sites):
        """Loop through all configured sites and add alternatives.

            See SyncServerModule.handle_alternate_site
        """
        conf_sites = system_sync_server_presets.get("sites", {})

        alternative_sites = []
        for site_name, site_info in conf_sites.items():
            alt_sites = set(site_info.get("alternative_sites", []))
            already_attached_keys = list(already_attached_sites.keys())
            for added_site in already_attached_keys:
                if added_site in alt_sites:
                    if site_name in already_attached_keys:
                        continue
                    meta = {"name": site_name}
                    real_created = already_attached_sites[added_site]
                    # alt site inherits state of 'created_dt'
                    if real_created:
                        meta["created_dt"] = real_created
                    alternative_sites.append(meta)
                    already_attached_sites[meta["name"]] = real_created

        return alternative_sites
    # endregion
