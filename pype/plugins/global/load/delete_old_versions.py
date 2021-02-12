import traceback
import collections
import os
import uuid

import clique
from pymongo import UpdateOne
import ftrack_api

from avalon import api, style
from avalon.vendor.Qt import QtWidgets, QtCore
from avalon.tools.libraryloader import app
import avalon.pipeline
from pype.api import Anatomy


class Dialog(QtWidgets.QDialog):

    def __init__(self, label):
        super(Dialog, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.settings = {
            "run": False,
            "versions": None,
            "publish": None
        }
        self.widgets = {
            "title": QtWidgets.QWidget(),
            "titleLabel": QtWidgets.QLabel(label),
            "calculate": QtWidgets.QWidget(),
            "calculateLabel": QtWidgets.QLabel("Calculate only:"),
            "calculateValue": QtWidgets.QCheckBox(),
            "versions": QtWidgets.QWidget(),
            "versionsLabel": QtWidgets.QLabel("Versions to keep:"),
            "versionsValue": QtWidgets.QSpinBox(),
            "publish": QtWidgets.QWidget(),
            "publishLabel": QtWidgets.QLabel("Remove publish folder:"),
            "publishValue": QtWidgets.QCheckBox(),
            "buttons": QtWidgets.QWidget(),
            "okButton": QtWidgets.QPushButton("Ok"),
            "cancelButton": QtWidgets.QPushButton("Cancel"),
        }

        # Build title.
        layout = QtWidgets.QHBoxLayout(self.widgets["title"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widgets["titleLabel"])

        # Build calculate.
        layout = QtWidgets.QHBoxLayout(self.widgets["calculate"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widgets["calculateLabel"])
        layout.addWidget(self.widgets["calculateValue"])

        # Build versions.
        self.widgets["versionsValue"].setValue(2)
        self.widgets["versionsValue"].setMinimum(1)
        self.widgets["versionsValue"].setMaximum(9999)
        layout = QtWidgets.QHBoxLayout(self.widgets["versions"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widgets["versionsLabel"])
        layout.addWidget(self.widgets["versionsValue"])

        # Build publish.
        layout = QtWidgets.QHBoxLayout(self.widgets["publish"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widgets["publishLabel"])
        layout.addWidget(self.widgets["publishValue"])

        # Build buttons.
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widgets["okButton"])
        layout.addWidget(self.widgets["cancelButton"])

        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["title"])
        layout.addWidget(self.widgets["calculate"])
        layout.addWidget(self.widgets["versions"])
        layout.addWidget(self.widgets["publish"])
        layout.addWidget(self.widgets["buttons"])

        # Build connections.
        self.widgets["okButton"].pressed.connect(self.on_ok_pressed)
        self.widgets["cancelButton"].pressed.connect(self.on_cancel_pressed)

    def on_ok_pressed(self):
        self.settings.update({
            "run": True,
            "calculate": self.widgets["calculateValue"].checkState(),
            "versions": self.widgets["versionsValue"].value(),
            "publish": self.widgets["publishValue"].checkState()
        })
        self.close()

    def on_cancel_pressed(self):
        self.close()

    def get_settings(self):
        return self.settings


class DeleteOldVersions(api.Loader):

    representations = ["*"]
    families = ["*"]

    label = "Delete Old Versions"
    icon = "trash"
    color = "#d8d8d8"

    sequence_splitter = "__sequence_splitter__"

    def sizeof_fmt(self, num, suffix='B'):
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def delete_whole_dir_paths(self, dir_paths, delete=True):
        size = 0

        for dir_path in dir_paths:
            # Delete all files and fodlers in dir path
            for root, dirs, files in os.walk(dir_path, topdown=False):
                for name in files:
                    file_path = os.path.join(root, name)
                    size += os.path.getsize(file_path)
                    if delete:
                        os.remove(file_path)
                        print("Removed file: {}".format(file_path))

                for name in dirs:
                    if delete:
                        os.rmdir(os.path.join(root, name))

            if not delete:
                continue

            # Delete even the folder and it's parents folders if they are empty
            while True:
                if not os.path.exists(dir_path):
                    dir_path = os.path.dirname(dir_path)
                    continue

                if len(os.listdir(dir_path)) != 0:
                    break

                os.rmdir(os.path.join(dir_path))

        return size

    def path_from_representation(self, representation, anatomy):
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

    def delete_only_repre_files(self, dir_paths, file_paths, delete=True):
        size = 0

        for dir_id, dir_path in dir_paths.items():
            dir_files = os.listdir(dir_path)
            collections, remainders = clique.assemble(dir_files)
            for file_path, seq_path in file_paths[dir_id]:
                file_path_base = os.path.split(file_path)[1]
                # Just remove file if `frame` key was not in context or
                # filled path is in remainders (single file sequence)
                if not seq_path or file_path_base in remainders:
                    if not os.path.exists(file_path):
                        print(
                            "File was not found: {}".format(file_path)
                        )
                        continue

                    size += os.path.getsize(file_path)

                    if delete:
                        os.remove(file_path)
                        print("Removed file: {}".format(file_path))

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

                            size += os.path.getsize(_file_path)

                            if delete:
                                os.remove(_file_path)
                                print(
                                    "Removed file: {}".format(_file_path)
                                )

                    _seq_path = final_col.format("{head}{padding}{tail}")
                    print("Removed files: {}".format(_seq_path))
                    collections.remove(final_col)

                elif os.path.exists(file_path):
                    size += os.path.getsize(file_path)

                    if delete:
                        os.remove(file_path)
                        print("Removed file: {}".format(file_path))
                else:
                    print(
                        "File was not found: {}".format(file_path)
                    )

        # Delete as much as possible parent folders
        if not delete:
            return size

        for dir_path in dir_paths.values():
            while True:
                if not os.path.exists(dir_path):
                    dir_path = os.path.dirname(dir_path)
                    continue

                if len(os.listdir(dir_path)) != 0:
                    break

                self.log.debug("Removed folder: {}".format(dir_path))
                os.rmdir(dir_path)

        return size

    def main(self, context):
        subset = context["subset"]
        asset = context["asset"]
        anatomy = Anatomy(context["project"]["name"])
        self.dbcon = app.window.dbcon
        label = "_".join([asset["name"], subset["name"]])

        dialog = Dialog(label)
        dialog.setStyleSheet(style.load_stylesheet())
        dialog.exec_()
        settings = dialog.get_settings()
        versions_count = settings["versions"]

        versions = list(
            self.dbcon.find({
                "type": "version",
                "parent": {"$in": [subset["_id"]]}
            })
        )

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

        print("Collected versions ({})".format(len(versions)))

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
            msg = "Asset: \"{}\" | Subset: \"{}\" | Version: \"{}\"".format(
                asset["name"], subset["name"], version["name"]
            )
            print((
                "Skipping version. Already tagged as `deleted`. < {} >"
            ).format(msg))
            versions.remove(version)

        version_ids = [ent["_id"] for ent in versions]

        print(
            "Filtered versions to delete ({})".format(len(version_ids))
        )

        if not version_ids:
            msg = "Skipping processing. Nothing to delete."
            print(msg)
            return {
                "success": True,
                "message": msg
            }

        repres = list(self.dbcon.find({
            "type": "representation",
            "parent": {"$in": version_ids}
        }))

        print(
            "Collected representations to remove ({})".format(len(repres))
        )

        dir_paths = {}
        file_paths_by_dir = collections.defaultdict(list)
        for repre in repres:
            file_path, seq_path = self.path_from_representation(repre, anatomy)
            if file_path is None:
                print((
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
            print((
                "Folder does not exist. Deleting it's files skipped: {}"
            ).format(paths_msg))

        # Size of files.
        size = 0

        if settings["calculate"]:
            if settings["publish"]:
                size = self.delete_whole_dir_paths(
                    dir_paths.values(), delete=False
                )
            else:
                size = self.delete_only_repre_files(
                    dir_paths, file_paths_by_dir, delete=False
                )

            msg = "Total size of files: " + self.sizeof_fmt(size)
            print(msg)
            return

        if settings["publish"]:
            size = self.delete_whole_dir_paths(dir_paths.values())
        else:
            size = self.delete_only_repre_files(dir_paths, file_paths_by_dir)

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
        session = ftrack_api.Session()
        query = (
            "AssetVersion where asset.parent.id is \"{}\""
            " and asset.name is \"{}\""
            " and version is \"{}\""
        )
        for v in versions:
            try:
                ftrack_version = session.query(
                    query.format(
                        asset["data"]["ftrackId"], subset["name"], v["name"]
                    )
                ).one()
            except ftrack_api.exception.NoResultFoundError:
                continue

            ftrack_version["is_published"] = False

        try:
            session.commit()

        except Exception:
            msg = (
                "Could not set `is_published` attribute to `False`"
                " for selected AssetVersions."
            )
            print(msg, exc_info=True)

        msg = "Total size of files deleted: " + self.sizeof_fmt(size)
        print(msg)

    def load(self, context, name=None, namespace=None, data=None):
        try:
            self.main(context)
        except Exception:
            print(traceback.format_exc())
