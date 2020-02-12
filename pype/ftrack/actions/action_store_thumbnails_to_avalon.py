import os
import requests
import errno

from bson.objectid import ObjectId
from pype.ftrack import BaseAction
from pype.ftrack.lib import (
    get_project_from_entity,
    get_avalon_entities_for_assetversion
)
from pypeapp import Anatomy
from pype.ftrack.lib.io_nonsingleton import DbConnector


class StoreThumbnailsToAvalon(BaseAction):
    # Action identifier
    identifier = "store.thubmnail.to.avalon"
    # Action label
    label = "Pype Admin"
    # Action variant
    variant = "- Store Thumbnails to avalon"
    # Action description
    description = 'Test action'
    # roles that are allowed to register this action
    role_list = ["Pypeclub", "Administrator", "Project Manager"]

    icon = '{}/ftrack/action_icons/PypeAdmin.svg'.format(
        os.environ.get('PYPE_STATICS_SERVER', '')
    )

    thumbnail_key = "AVALON_THUMBNAIL_ROOT"
    db_con = DbConnector()

    def discover(self, session, entities, event):
        for entity in entities:
            if entity.entity_type.lower() == "assetversion":
                return True
        return False

    def launch(self, session, entities, event):
        # DEBUG LINE
        # root_path = r"C:\Users\jakub.trllo\Desktop\Tests\ftrack_thumbnails"

        thumbnail_roots = os.environ.get(self.thumbnail_key)
        if not thumbnail_roots:
            return {
                "success": False,
                "message": "`{}` environment is not set".format(
                    self.thumbnail_key
                )
            }

        existing_thumbnail_root = None
        for path in thumbnail_roots.split(os.pathsep):
            if os.path.exists(path):
                existing_thumbnail_root = path
                break

        if existing_thumbnail_root is None:
            return {
                "success": False,
                "message": (
                    "Can't access paths, set in `{}` ({})"
                ).format(self.thumbnail_key, thumbnail_roots)
            }

        project = get_project_from_entity(entities[0])
        project_name = project["full_name"]
        anatomy = Anatomy(project_name)

        if "publish" not in anatomy.templates:
            msg = "Anatomy does not have set publish key!"

            self.log.warning(msg)

            return {
                "success": False,
                "message": msg
            }

        if "thumbnail" not in anatomy.templates["publish"]:
            msg = (
                "There is not set \"thumbnail\""
                " template in Antomy for project \"{}\""
            ).format(project_name)

            self.log.warning(msg)

            return {
                "success": False,
                "message": msg
            }

        example_template_data = {
            "_id": "ID",
            "thumbnail_root": "THUBMNAIL_ROOT",
            "thumbnail_type": "THUMBNAIL_TYPE",
            "ext": ".EXT",
            "project": {
                "name": "PROJECT_NAME",
                "code": "PROJECT_CODE"
            },
            "asset": "ASSET_NAME",
            "subset": "SUBSET_NAME",
            "version": "VERSION_NAME",
            "hierarchy": "HIERARCHY"
        }
        tmp_filled = anatomy.format_all(example_template_data)
        thumbnail_result = tmp_filled["publish"]["thumbnail"]
        if not thumbnail_result.solved:
            missing_keys = thumbnail_result.missing_keys
            invalid_types = thumbnail_result.invalid_types
            submsg = ""
            if missing_keys:
                submsg += "Missing keys: {}".format(", ".join(
                    ["\"{}\"".format(key) for key in missing_keys]
                ))

            if invalid_types:
                items = []
                for key, value in invalid_types.items():
                    items.append("{}{}".format(str(key), str(value)))
                submsg += "Invalid types: {}".format(", ".join(items))

            msg = (
                "Thumbnail Anatomy template expects more keys than action"
                " can offer. {}"
            ).format(submsg)

            self.log.warning(msg)

            return {
                "success": False,
                "message": msg
            }

        thumbnail_template = anatomy.templates["publish"]["thumbnail"]

        self.db_con.install()

        for entity in entities:
            # Skip if entity is not AssetVersion (never should happend, but..)
            if entity.entity_type.lower() != "assetversion":
                continue

            # Skip if AssetVersion don't have thumbnail
            thumbnail_ent = entity["thumbnail"]
            if thumbnail_ent is None:
                self.log.debug((
                    "Skipping. AssetVersion don't "
                    "have set thumbnail. {}"
                ).format(entity["id"]))
                continue

            avalon_ents_result = get_avalon_entities_for_assetversion(
                entity, self.db_con
            )
            version_full_path = (
                "Asset: \"{project_name}/{asset_path}\""
                " | Subset: \"{subset_name}\""
                " | Version: \"{version_name}\""
            ).format(**avalon_ents_result)

            version = avalon_ents_result["version"]
            if not version:
                self.log.warning((
                    "AssetVersion does not have version in avalon. {}"
                ).format(version_full_path))
                continue

            thumbnail_id = version["data"].get("thumbnail_id")
            if thumbnail_id:
                self.log.info((
                    "AssetVersion skipped, already has thubmanil set. {}"
                ).format(version_full_path))
                continue

            # Get thumbnail extension
            file_ext = thumbnail_ent["file_type"]
            if not file_ext.startswith("."):
                file_ext = ".{}".format(file_ext)

            avalon_project = avalon_ents_result["project"]
            avalon_asset = avalon_ents_result["asset"]
            hierarchy = ""
            parents = avalon_asset["data"].get("parents") or []
            if parents:
                hierarchy = "/".join(parents)

            # Prepare anatomy template fill data
            # 1. Create new id for thumbnail entity
            thumbnail_id = ObjectId()

            template_data = {
                "_id": str(thumbnail_id),
                "thumbnail_root": existing_thumbnail_root,
                "thumbnail_type": "thumbnail",
                "ext": file_ext,
                "project": {
                    "name": avalon_project["name"],
                    "code": avalon_project["data"].get("code")
                },
                "asset": avalon_ents_result["asset_name"],
                "subset": avalon_ents_result["subset_name"],
                "version": avalon_ents_result["version_name"],
                "hierarchy": hierarchy
            }

            anatomy_filled = anatomy.format(template_data)
            thumbnail_path = anatomy_filled["publish"]["thumbnail"]
            thumbnail_path = thumbnail_path.replace("..", ".")
            thumbnail_path = os.path.normpath(thumbnail_path)

            downloaded = False
            for loc in (thumbnail_ent.get("component_locations") or []):
                res_id = loc.get("resource_identifier")
                if not res_id:
                    continue

                thubmnail_url = self.get_thumbnail_url(res_id)
                if self.download_file(thubmnail_url, thumbnail_path):
                    downloaded = True
                    break

            if not downloaded:
                self.log.warning(
                    "Could not download thumbnail for {}".format(
                        version_full_path
                    )
                )
                continue

            # Clean template data from keys that are dynamic
            template_data.pop("_id")
            template_data.pop("thumbnail_root")

            thumbnail_entity = {
                "_id": thumbnail_id,
                "type": "thumbnail",
                "schema": "pype:thumbnail-1.0",
                "data": {
                    "template": thumbnail_template,
                    "template_data": template_data
                }
            }

            # Create thumbnail entity
            self.db_con.insert_one(thumbnail_entity)
            self.log.debug(
                "Creating entity in database {}".format(str(thumbnail_entity))
            )

            # Set thumbnail id for version
            self.db_con.update_one(
                {"_id": version["_id"]},
                {"$set": {"data.thumbnail_id": thumbnail_id}}
            )

            self.db_con.update_one(
                {"_id": avalon_asset["_id"]},
                {"$set": {"data.thumbnail_id": thumbnail_id}}
            )

        return True

    def get_thumbnail_url(self, resource_identifier, size=None):
        # TODO use ftrack_api method rather (find way how to use it)
        url_string = (
            u'{url}/component/thumbnail?id={id}&username={username}'
            u'&apiKey={apiKey}'
        )
        url = url_string.format(
            url=self.session.server_url,
            id=resource_identifier,
            username=self.session.api_user,
            apiKey=self.session.api_key
        )
        if size:
            url += u'&size={0}'.format(size)

        return url

    def download_file(self, source_url, dst_file_path):
        dir_path = os.path.dirname(dst_file_path)
        try:
            os.makedirs(dir_path)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                self.log.warning(
                    "Could not create folder: \"{}\"".format(dir_path)
                )
                return False

        self.log.debug(
            "Downloading file \"{}\" -> \"{}\"".format(
                source_url, dst_file_path
            )
        )
        file_open = open(dst_file_path, "wb")
        try:
            file_open.write(requests.get(source_url).content)
        except Exception:
            self.log.warning(
                "Download of image `{}` failed.".format(source_url)
            )
            return False
        finally:
            file_open.close()
        return True


def register(session, plugins_presets={}):
    StoreThumbnailsToAvalon(session, plugins_presets).register()
