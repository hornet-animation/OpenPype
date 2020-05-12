import os
import collections
import uuid

import clique
from pymongo import UpdateOne

from pype.ftrack import BaseAction
from pype.ftrack.lib.io_nonsingleton import DbConnector
from pypeapp import Anatomy

import avalon.pipeline


class DeleteOldVersions(BaseAction):

    identifier = "delete.old.versions"
    label = "Pype Admin"
    variant = "- Delete old versions"
    description = (
        "Delete files from older publishes so project can be"
        " archived with only lates versions."
    )
    role_list = ["Pypeclub", "Project Manager", "Administrator"]
    icon = "{}/ftrack/action_icons/PypeAdmin.svg".format(
        os.environ.get("PYPE_STATICS_SERVER", "")
    )

    dbcon = DbConnector()

    inteface_title = "Choose your preferences"
    splitter_item = {"type": "label", "value": "---"}
    sequence_splitter = "__sequence_splitter__"

    def discover(self, session, entities, event):
        ''' Validation '''
        selection = event["data"].get("selection") or []
        for entity in selection:
            entity_type = (entity.get("entityType") or "").lower()
            if entity_type == "assetversion":
                return True
        return False

    def interface(self, session, entities, event):
        items = []
        root = os.environ.get("AVALON_PROJECTS")
        if not root:
            msg = "Root path to projects is not set."
            items.append({
                "type": "label",
                "value": "<i><b>ERROR:</b> {}</i>".format(msg)
            })
            self.show_interface(
                items=items, title=self.inteface_title, event=event
            )
            return {
                "success": False,
                "message": msg
            }

        if not os.path.exists(root):
            msg = "Root path does not exists \"{}\".".format(str(root))
            items.append({
                "type": "label",
                "value": "<i><b>ERROR:</b> {}</i>".format(msg)
            })
            self.show_interface(
                items=items, title=self.inteface_title, event=event
            )
            return {
                "success": False,
                "message": msg
            }

        values = event["data"].get("values")
        if values:
            versions_count = int(values["last_versions_count"])
            if versions_count >= 1:
                return
            items.append({
                "type": "label",
                "value": (
                    "# You have to keep at least 1 version!"
                )
            })

        items.append({
            "type": "label",
            "value": (
                "<i><b>WARNING:</b> This will remove published files of older"
                " versions from disk so we don't recommend use"
                " this action on \"live\" project.</i>"
            )
        })

        items.append(self.splitter_item)

        # How many versions to keep
        items.append({
            "type": "label",
            "value": "## Choose how many versions you want to keep:"
        })
        items.append({
            "type": "label",
            "value": (
                "<i><b>NOTE:</b> We do recommend to keep 2 versions.</i>"
            )
        })
        items.append({
            "type": "number",
            "name": "last_versions_count",
            "label": "Versions",
            "value": 2
        })

        items.append(self.splitter_item)

        items.append({
            "type": "label",
            "value": (
                "## Remove publish folder even if there"
                " are other than published files:"
            )
        })
        items.append({
            "type": "label",
            "value": (
                "<i><b>WARNING:</b> This may remove more than you want.</i>"
            )
        })
        items.append({
            "type": "boolean",
            "name": "force_delete_publish_folder",
            "label": "Are You sure?",
            "value": False
        })

        return {
            "items": items,
            "title": self.inteface_title
        }

    def launch(self, session, entities, event):
        values = event["data"].get("values")
        if not values:
            return

        versions_count = int(values["last_versions_count"])
        force_to_remove = values["force_delete_publish_folder"]

        _val1 = "OFF"
        if force_to_remove:
            _val1 = "ON"

        _val3 = "s"
        if versions_count == 1:
            _val3 = ""

        self.log.debug((
            "Process started. Force to delete publish folder is set to [{0}]"
            " and will keep {1} latest version{2}."
        ).format(_val1, versions_count, _val3))

        self.dbcon.install()

        project = None
        avalon_asset_names = []
        asset_versions_by_parent_id = collections.defaultdict(list)
        subset_names_by_asset_name = collections.defaultdict(list)

        ftrack_assets_by_name = {}
        for entity in entities:
            ftrack_asset = entity["asset"]

            parent_ent = ftrack_asset["parent"]
            parent_ftrack_id = parent_ent["id"]
            parent_name = parent_ent["name"]

            if parent_name not in avalon_asset_names:
                avalon_asset_names.append(parent_name)

            # Group asset versions by parent entity
            asset_versions_by_parent_id[parent_ftrack_id].append(entity)

            # Get project
            if project is None:
                project = parent_ent["project"]

            # Collect subset names per asset
            subset_name = ftrack_asset["name"]
            subset_names_by_asset_name[parent_name].append(subset_name)

            if subset_name not in ftrack_assets_by_name:
                ftrack_assets_by_name[subset_name] = ftrack_asset

        # Set Mongo collection
        project_name = project["full_name"]
        anatomy = Anatomy(project_name)
        self.dbcon.Session["AVALON_PROJECT"] = project_name
        self.log.debug("Project is set to {}".format(project_name))

        # Get Assets from avalon database
        assets = list(self.dbcon.find({
            "type": "asset",
            "name": {"$in": avalon_asset_names}
        }))
        asset_id_to_name_map = {
            asset["_id"]: asset["name"] for asset in assets
        }
        asset_ids = list(asset_id_to_name_map.keys())

        self.log.debug("Collected assets ({})".format(len(asset_ids)))

        # Get Subsets
        subsets = list(self.dbcon.find({
            "type": "subset",
            "parent": {"$in": asset_ids}
        }))
        subsets_by_id = {}
        subset_ids = []
        for subset in subsets:
            asset_id = subset["parent"]
            asset_name = asset_id_to_name_map[asset_id]
            available_subsets = subset_names_by_asset_name[asset_name]

            if subset["name"] not in available_subsets:
                continue

            subset_ids.append(subset["_id"])
            subsets_by_id[subset["_id"]] = subset

        self.log.debug("Collected subsets ({})".format(len(subset_ids)))

        # Get Versions
        versions = list(self.dbcon.find({
            "type": "version",
            "parent": {"$in": subset_ids}
        }))

        versions_by_parent = collections.defaultdict(list)
        for ent in versions:
            versions_by_parent[ent["parent"]].append(ent)

        def sort_func(ent):
            return int(ent["name"])

        all_last_versions = []
        for parent_id, _versions in versions_by_parent.items():
            for idx, version in enumerate(
                sorted(_versions, key=sort_func, reverse=True)
            ):
                if idx >= versions_count:
                    break
                all_last_versions.append(version)

        self.log.debug("Collected versions ({})".format(len(versions)))

        # Filter latest versions
        for version in all_last_versions:
            versions.remove(version)

        # Update versions_by_parent without filtered versions
        versions_by_parent = collections.defaultdict(list)
        for ent in versions:
            versions_by_parent[ent["parent"]].append(ent)

        # Filter already deleted versions
        versions_to_pop = []
        for version in versions:
            version_tags = version["data"].get("tags")
            if version_tags and "deleted" in version_tags:
                versions_to_pop.append(version)

        for version in versions_to_pop:
            subset = subsets_by_id[version["parent"]]
            asset_id = subset["parent"]
            asset_name = asset_id_to_name_map[asset_id]
            msg = "Asset: \"{}\" | Subset: \"{}\" | Version: \"{}\"".format(
                asset_name, subset["name"], version["name"]
            )
            self.log.warning((
                "Skipping version. Already tagged as `deleted`. < {} >"
            ).format(msg))
            versions.remove(version)

        version_ids = [ent["_id"] for ent in versions]

        self.log.debug(
            "Filtered versions to delete ({})".format(len(version_ids))
        )

        if not version_ids:
            msg = "Skipping processing. Nothing to delete."
            self.log.debug(msg)
            return {
                "success": True,
                "message": msg
            }

        repres = list(self.dbcon.find({
            "type": "representation",
            "parent": {"$in": version_ids}
        }))

        self.log.debug(
            "Collected representations to remove ({})".format(len(repres))
        )

        dir_paths = {}
        file_paths_by_dir = collections.defaultdict(list)
        for repre in repres:
            file_path, seq_path = self.path_from_represenation(repre, anatomy)
            if file_path is None:
                self.log.warning((
                    "Could not format path for represenation \"{}\""
                ).format(str(repre)))
                continue

            dir_path = os.path.dirname(file_path)
            dir_id = None
            for _dir_id, _dir_path in dir_paths.items():
                if _dir_path == dir_path:
                    dir_id = _dir_id
                    break

            if dir_id is None:
                dir_id = uuid.uuid4()
                dir_paths[dir_id] = dir_path

            file_paths_by_dir[dir_id].append([file_path, seq_path])

        dir_ids_to_pop = []
        for dir_id, dir_path in dir_paths.items():
            if os.path.exists(dir_path):
                continue

            dir_ids_to_pop.append(dir_id)

        # Pop dirs from both dictionaries
        for dir_id in dir_ids_to_pop:
            dir_paths.pop(dir_id)
            paths = file_paths_by_dir.pop(dir_id)
            # TODO report of missing directories?
            paths_msg = ", ".join([
                "'{}'".format(path[0].replace("\\", "/")) for path in paths
            ])
            self.log.warning((
                "Folder does not exist. Deleting it's files skipped: {}"
            ).format(paths_msg))

        if force_to_remove:
            self.delete_whole_dir_paths(dir_paths.values())
        else:
            self.delete_only_repre_files(dir_paths, file_paths_by_dir)

        mongo_changes_bulk = []
        for version in versions:
            orig_version_tags = version["data"].get("tags") or []
            version_tags = [tag for tag in orig_version_tags]
            if "deleted" not in version_tags:
                version_tags.append("deleted")

            if version_tags == orig_version_tags:
                continue

            update_query = {"_id": version["_id"]}
            update_data = {"$set": {"data.tags": version_tags}}
            mongo_changes_bulk.append(UpdateOne(update_query, update_data))

        if mongo_changes_bulk:
            self.dbcon.bulk_write(mongo_changes_bulk)

        self.dbcon.uninstall()

        # Set attribute `is_published` to `False` on ftrack AssetVersions
        for subset_id, _versions in versions_by_parent.items():
            subset_name = None
            for subset in subsets:
                if subset["_id"] == subset_id:
                    subset_name = subset["name"]
                    break

            if subset_name is None:
                self.log.warning(
                    "Subset with ID `{}` was not found.".format(str(subset_id))
                )
                continue

            ftrack_asset = ftrack_assets_by_name.get(subset_name)
            if not ftrack_asset:
                self.log.warning((
                    "Could not find Ftrack asset with name `{}`"
                ).format(subset_name))
                continue

            version_numbers = [int(ver["name"]) for ver in _versions]
            for version in ftrack_asset["versions"]:
                if int(version["version"]) in version_numbers:
                    version["is_published"] = False

        try:
            session.commit()

        except Exception:
            msg = (
                "Could not set `is_published` attribute to `False`"
                " for selected AssetVersions."
            )
            self.log.warning(msg, exc_info=True)

            return {
                "success": False,
                "message": msg
            }

        return True

    def delete_whole_dir_paths(self, dir_paths):
        for dir_path in dir_paths:
            # Delete all files and fodlers in dir path
            for root, dirs, files in os.walk(dir_path, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))

                for name in dirs:
                    os.rmdir(os.path.join(root, name))

            # Delete even the folder and it's parents folders if they are empty
            while True:
                if not os.path.exists(dir_path):
                    dir_path = os.path.dirname(dir_path)
                    continue

                if len(os.listdir(dir_path)) != 0:
                    break

                os.rmdir(os.path.join(dir_path))

    def delete_only_repre_files(self, dir_paths, file_paths):
        for dir_id, dir_path in dir_paths.items():
            dir_files = os.listdir(dir_path)
            collections, remainders = clique.assemble(dir_files)
            for file_path, seq_path in file_paths[dir_id]:
                file_path_base = os.path.split(file_path)[1]
                # Just remove file if `frame` key was not in context or
                # filled path is in remainders (single file sequence)
                if not seq_path or file_path_base in remainders:
                    if not os.path.exists(file_path):
                        self.log.warning(
                            "File was not found: {}".format(file_path)
                        )
                        continue
                    os.remove(file_path)
                    self.log.debug("Removed file: {}".format(file_path))
                    remainders.remove(file_path_base)
                    continue

                seq_path_base = os.path.split(seq_path)[1]
                head, tail = seq_path_base.split(self.sequence_splitter)

                final_col = None
                for collection in collections:
                    if head != collection.head or tail != collection.tail:
                        continue
                    final_col = collection
                    break

                if final_col is not None:
                    # Fill full path to head
                    final_col.head = os.path.join(dir_path, final_col.head)
                    for _file_path in final_col:
                        if os.path.exists(_file_path):
                            os.remove(_file_path)
                    _seq_path = final_col.format("{head}{padding}{tail}")
                    self.log.debug("Removed files: {}".format(_seq_path))
                    collections.remove(final_col)

                elif os.path.exists(file_path):
                    os.remove(file_path)
                    self.log.debug("Removed file: {}".format(file_path))

                else:
                    self.log.warning(
                        "File was not found: {}".format(file_path)
                    )

        # Delete as much as possible parent folders
        for dir_path in dir_paths.values():
            while True:
                if not os.path.exists(dir_path):
                    dir_path = os.path.dirname(dir_path)
                    continue

                if len(os.listdir(dir_path)) != 0:
                    break

                self.log.debug("Removed folder: {}".format(dir_path))
                os.rmdir(dir_path)

    def path_from_represenation(self, representation, anatomy):
        try:
            template = representation["data"]["template"]

        except KeyError:
            return (None, None)

        sequence_path = None
        try:
            context = representation["context"]
            context["root"] = anatomy.roots
            path = avalon.pipeline.format_template_with_optional_keys(
                context, template
            )
            if "frame" in context:
                context["frame"] = self.sequence_splitter
                sequence_path = os.path.normpath(
                    avalon.pipeline.format_template_with_optional_keys(
                        context, template
                    )
                )

        except KeyError:
            # Template references unavailable data
            return (None, None)

        return (os.path.normpath(path), sequence_path)


def register(session, plugins_presets={}):
    '''Register plugin. Called when used as an plugin.'''

    DeleteOldVersions(session, plugins_presets).register()
