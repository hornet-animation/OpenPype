import os
import collections
import re
import copy
import queue
import time
import toml
import atexit
import traceback

from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo import UpdateOne

from avalon import schema

from pype.ftrack.lib import avalon_sync
from pype.ftrack.lib.avalon_sync import (
    cust_attr_id_key, cust_attr_auto_sync, entity_schemas
)
from pype.vendor import ftrack_api
from pype.ftrack import BaseEvent

from pype.ftrack.lib.io_nonsingleton import DbConnector


class SyncToAvalonEvent(BaseEvent):

    dbcon = DbConnector()

    ignore_entTypes = [
        "socialfeed", "socialnotification", "note",
        "assetversion", "job", "user", "reviewsessionobject", "timer",
        "timelog", "auth_userrole"
    ]
    ignore_ent_types = ["Milestone"]
    ignore_keys = ["statusid"]

    project_query = (
        "select full_name, name, custom_attributes"
        ", project_schema._task_type_schema.types.name"
        " from Project where id is \"{}\""
    )

    entities_query_by_id = (
        "select id, name, parent_id, link, custom_attributes from TypedContext"
        " where project_id is \"{}\" and id in ({})"
    )
    entities_name_query_by_name = (
        "select id, name from TypedContext"
        " where project_id is \"{}\" and name in ({})"
    )
    created_entities = []

    def __init__(self, session, plugins_presets={}):
        '''Expects a ftrack_api.Session instance'''
        self.set_process_session(session)
        super().__init__(session, plugins_presets)

    @property
    def cur_project(self):
        if self._cur_project is None:
            found_id = None
            for ent_info in self._cur_event["data"]["entities"]:
                if found_id is not None:
                    break
                parents = ent_info.get("parents") or []
                for parent in parents:
                    if parent.get("entityType") == "show":
                        found_id = parent.get("entityId")
                        break
            if found_id:
                self._cur_project = self.process_session.query(
                    self.project_query.format(found_id)
                ).one()
        return self._cur_project

    @property
    def avalon_cust_attrs(self):
        if self._avalon_cust_attrs is None:
            self._avalon_cust_attrs = avalon_sync.get_avalon_attr(
                self.process_session
            )
        return self._avalon_cust_attrs

    @property
    def avalon_entities(self):
        if self._avalon_ents is None:
            self.dbcon.install()
            self.dbcon.Session["AVALON_PROJECT"] = (
                self.cur_project["full_name"]
            )
            avalon_project = self.dbcon.find_one({"type": "project"})
            avalon_entities = list(self.dbcon.find({"type": "asset"}))
            self._avalon_ents = (avalon_project, avalon_entities)
        return self._avalon_ents

    @property
    def avalon_ents_by_name(self):
        if self._avalon_ents_by_name is None:
            self._avalon_ents_by_name = {}
            proj, ents = self.avalon_entities
            for ent in ents:
                self._avalon_ents_by_name[ent["name"]] = ent
        return self._avalon_ents_by_name

    @property
    def avalon_ents_by_id(self):
        if self._avalon_ents_by_id is None:
            self._avalon_ents_by_id = {}
            proj, ents = self.avalon_entities
            self._avalon_ents_by_id[proj["_id"]] = proj
            for ent in ents:
                self._avalon_ents_by_id[ent["_id"]] = ent
        return self._avalon_ents_by_id

    @property
    def avalon_ents_by_parent_id(self):
        if self._avalon_ents_by_parent_id is None:
            self._avalon_ents_by_parent_id = collections.defaultdict(list)
            proj, ents = self.avalon_entities
            for ent in ents:
                vis_par = ent["data"]["visualParent"]
                if vis_par is None:
                    vis_par = proj["_id"]
                self._avalon_ents_by_parent_id[vis_par].append(ent)
        return self._avalon_ents_by_parent_id

    @property
    def avalon_ents_by_ftrack_id(self):
        if self._avalon_ents_by_ftrack_id is None:
            self._avalon_ents_by_ftrack_id = {}
            proj, ents = self.avalon_entities
            ftrack_id = proj["data"]["ftrackId"]
            self._avalon_ents_by_ftrack_id[ftrack_id] = proj
            for ent in ents:
                ftrack_id = ent["data"]["ftrackId"]
                self._avalon_ents_by_ftrack_id[ftrack_id] = ent
        return self._avalon_ents_by_ftrack_id

    @property
    def avalon_subsets_by_parents(self):
        if self._avalon_subsets_by_parents is None:
            self._avalon_subsets_by_parents = collections.defaultdict(list)
            self.dbcon.install()
            self.dbcon.Session["AVALON_PROJECT"] = (
                self.cur_project["full_name"]
            )
            for subset in self.dbcon.find({"type": "subset"}):
                self._avalon_subsets_by_parents[subset["parent"]].append(
                    subset
                )
        return self._avalon_subsets_by_parents

    @property
    def avalon_archived_by_id(self):
        if self._avalon_archived_by_id is None:
            self._avalon_archived_by_id = {}
            self.dbcon.install()
            self.dbcon.Session["AVALON_PROJECT"] = (
                self.cur_project["full_name"]
            )
            for asset in self.dbcon.find({"type": "archived_asset"}):
                self._avalon_archived_by_id[asset["_id"]] = asset
        return self._avalon_archived_by_id

    @property
    def avalon_archived_by_name(self):
        if self._avalon_archived_by_name is None:
            self._avalon_archived_by_name = {}
            for asset in self.avalon_archived_by_id.values():
                self._avalon_archived_by_name[asset["name"]] = asset
        return self._avalon_archived_by_name

    @property
    def changeability_by_mongo_id(self):
        """Return info about changeability of entity and it's parents."""
        if self._changeability_by_mongo_id is None:
            self._changeability_by_mongo_id = collections.defaultdict(
                lambda: True
            )
            avalon_project, avalon_entities = self.avalon_entities
            self._changeability_by_mongo_id[avalon_project["_id"]] = False
            self._bubble_changeability(
                list(self.avalon_subsets_by_parents.keys())
            )

        return self._changeability_by_mongo_id

    @property
    def avalon_custom_attributes(self):
        """Return info about changeability of entity and it's parents."""
        if self._avalon_custom_attributes is None:
            self._avalon_custom_attributes = avalon_sync.get_avalon_attr(
                self.process_session
            )
        return self._avalon_custom_attributes

    def remove_cached_by_key(self, key, values):
        if self._avalon_ents is None:
            return

        if not isinstance(values, (list, tuple)):
            values = [values]

        def get_found_data(entity):
            if not entity:
                return None
            return {
                "ftrack_id": entity["data"]["ftrackId"],
                "parent_id": entity["data"]["visualParent"],
                "_id": entity["_id"],
                "name": entity["name"],
                "entity": entity
            }

        if key == "id":
            key = "_id"
        elif key == "ftrack_id":
            key = "data.ftrackId"

        found_data = {}
        project, entities = self._avalon_ents
        key_items = key.split(".")
        for value in values:
            ent = None
            if key == "_id":
                if self._avalon_ents_by_id is not None:
                    ent = self._avalon_ents_by_id.get(value)

            elif key == "name":
                if self._avalon_ents_by_name is not None:
                    ent = self._avalon_ents_by_name.get(value)

            elif key == "data.ftrackId":
                if self._avalon_ents_by_ftrack_id is not None:
                    ent = self._avalon_ents_by_ftrack_id.get(value)

            if ent is None:
                for _ent in entities:
                    _temp = _ent
                    for item in key_items:
                        _temp = _temp[item]

                    if _temp == value:
                        ent = _ent
                        break

            found_data[value] = get_found_data(ent)

        for value in values:
            data = found_data[value]
            if not data:
                # TODO logging
                self.log.warning(
                    "Didn't found entity by key/value \"{}\" / \"{}\"".format(
                        key, value
                    )
                )
                continue

            ftrack_id = data["ftrack_id"]
            parent_id = data["parent_id"]
            mongo_id = data["_id"]
            name = data["name"]
            entity = data["entity"]

            project, ents = self._avalon_ents
            ents.remove(entity)
            self._avalon_ents = project, ents

            if self._avalon_ents_by_ftrack_id is not None:
                self._avalon_ents_by_ftrack_id.pop(ftrack_id, None)

            if self._avalon_ents_by_parent_id is not None:
                self._avalon_ents_by_parent_id[parent_id].remove(entity)

            if self._avalon_ents_by_id is not None:
                self._avalon_ents_by_id.pop(mongo_id, None)

            if self._avalon_ents_by_name is not None:
                self._avalon_ents_by_name.pop(name, None)

            if self._avalon_archived_by_id is not None:
                self._avalon_archived_by_id[mongo_id] = entity

            if mongo_id in self.task_changes_by_avalon_id:
                self.task_changes_by_avalon_id.pop(mongo_id)

    def _bubble_changeability(self, unchangeable_ids):
        unchangeable_queue = queue.Queue()
        for entity_id in unchangeable_ids:
            unchangeable_queue.put((entity_id, False))

        processed_parents_ids = []
        while not unchangeable_queue.empty():
            entity_id, child_is_archived = unchangeable_queue.get()
            # skip if already processed
            if entity_id in processed_parents_ids:
                continue

            entity = self.avalon_ents_by_id.get(entity_id)
            # if entity is not archived but unchageable child was then skip
            # - archived entities should not affect not archived?
            if entity and child_is_archived:
                continue

            # set changeability of current entity to False
            self._changeability_by_mongo_id[entity_id] = False
            processed_parents_ids.append(entity_id)
            # if not entity then is probably archived
            if not entity:
                entity = self.avalon_archived_by_id.get(entity_id)
                child_is_archived = True

            if not entity:
                # if entity is not found then it is subset without parent
                if entity_id in unchangeable_ids:
                    _subset_ids = [
                        str(sub["_id"]) for sub in
                        self.avalon_subsets_by_parents[entity_id]
                    ]
                    joined_subset_ids = "| ".join(_subset_ids)
                    self.log.warning((
                        "Parent <{}> for subsets <{}> does not exist"
                    ).format(str(entity_id), joined_subset_ids))
                else:
                    self.log.warning((
                        "In avalon are entities without valid parents that"
                        " lead to Project (should not cause errors)"
                        " - MongoId <{}>"
                    ).format(str(entity_id)))
                continue

            # skip if parent is project
            parent_id = entity["data"]["visualParent"]
            if parent_id is None:
                continue
            unchangeable_queue.put((parent_id, child_is_archived))

    def reset_variables(self):
        """Reset variables so each event callback has clear env."""
        self._cur_project = None

        self._avalon_cust_attrs = None

        self._avalon_ents = None
        self._avalon_ents_by_id = None
        self._avalon_ents_by_parent_id = None
        self._avalon_ents_by_ftrack_id = None
        self._avalon_ents_by_name = None
        self._avalon_subsets_by_parents = None
        self._changeability_by_mongo_id = None
        self._avalon_archived_by_id = None
        self._avalon_archived_by_name = None

        self.task_changes_by_avalon_id = {}

        self._avalon_custom_attributes = None
        self._ent_types_by_name = None

        self.ftrack_ents_by_id = {}
        self.obj_id_ent_type_map = {}
        self.ftrack_recreated_mapping = {}

        self.ftrack_added = {}
        self.ftrack_moved = {}
        self.ftrack_renamed = {}
        self.ftrack_updated = {}
        self.ftrack_removed = {}

        self.moved_in_avalon = []
        self.renamed_in_avalon = []
        self.hier_cust_attrs_changes = collections.defaultdict(list)

        self.duplicated = []
        self.regex_fail = []

        self.regex_schemas = {}
        self.updates = collections.defaultdict(dict)

        self.report_items = {
            "info": collections.defaultdict(list),
            "warning": collections.defaultdict(list),
            "error": collections.defaultdict(list)
        }

    def set_process_session(self, session):
        try:
            self.process_session.close()
        except Exception:
            pass
        self.process_session = ftrack_api.Session(
            server_url=session.server_url,
            api_key=session.api_key,
            api_user=session.api_user,
            auto_connect_event_hub=True
        )
        atexit.register(lambda: self.process_session.close())

    def filter_updated(self, updates):
        filtered_updates = {}
        for ftrack_id, ent_info in updates.items():
            changed_keys = [k for k in (ent_info.get("keys") or [])]
            changes = {
                k: v for k, v in (ent_info.get("changes") or {}).items()
            }

            entity_type = ent_info["entity_type"]
            if entity_type == "Task":
                if "name" in changed_keys:
                    ent_info["keys"] = ["name"]
                    ent_info["changes"] = {"name": changes.pop("name")}
                    filtered_updates[ftrack_id] = ent_info
                continue

            for _key in self.ignore_keys:
                if _key in changed_keys:
                    changed_keys.remove(_key)
                    changes.pop(_key, None)

            if not changed_keys:
                continue

            # Remove custom attributes starting with `avalon_` from changes
            # - these custom attributes are not synchronized
            avalon_keys = []
            for key in changes:
                if key.startswith("avalon_"):
                    avalon_keys.append(key)

            for _key in avalon_keys:
                changed_keys.remove(_key)
                changes.pop(_key, None)

            if not changed_keys:
                continue

            ent_info["keys"] = changed_keys
            ent_info["changes"] = changes
            filtered_updates[ftrack_id] = ent_info

        return filtered_updates

    def get_ent_path(self, ftrack_id):
        entity = self.ftrack_ents_by_id.get(ftrack_id)
        if not entity:
            entity = self.process_session.query(
                self.entities_query_by_id.format(
                    self.cur_project["id"], ftrack_id
                )
            ).one()
            self.ftrack_ents_by_id[ftrack_id] = entity
        return "/".join([ent["name"] for ent in entity["link"]])

    def launch(self, session, event):
        # Try to commit and if any error happen then recreate session
        try:
            self.process_session.commit()
        except Exception:
            self.set_process_session(session)

        # Reset object values for each launch
        self.reset_variables()
        self._cur_event = event

        entities_by_action = {
            "remove": {},
            "update": {},
            "move": {},
            "add": {}
        }
        self.log.debug("Starting event")
        entities_info = event["data"]["entities"]
        found_actions = set()
        for ent_info in entities_info:
            entityType = ent_info["entityType"]
            if entityType in self.ignore_entTypes:
                continue

            entity_type = ent_info.get("entity_type")
            if not entity_type or entity_type in self.ignore_ent_types:
                continue

            action = ent_info["action"]
            ftrack_id = ent_info["entityId"]
            if action == "move":
                ent_keys = ent_info["keys"]
                # Seprate update info from move action
                if len(ent_keys) > 1:
                    _ent_info = ent_info.copy()
                    for ent_key in ent_keys:
                        if ent_key == "parent_id":
                            _ent_info["changes"].pop(ent_key, None)
                            _ent_info["keys"].remove(ent_key)
                        else:
                            ent_info["changes"].pop(ent_key, None)
                            ent_info["keys"].remove(ent_key)

                    entities_by_action["update"][ftrack_id] = _ent_info

            found_actions.add(action)
            entities_by_action[action][ftrack_id] = ent_info

        found_actions = list(found_actions)
        if not found_actions:
            self.log.debug("There are not actions to do")
            return True

        # Check if auto sync was turned on/off
        updated = entities_by_action["update"]
        for ftrack_id, ent_info in updated.items():
            # filter project
            if ent_info["entityType"] != "show":
                continue

            changes = ent_info["changes"]
            if cust_attr_auto_sync not in changes:
                continue

            auto_sync = changes[cust_attr_auto_sync]["new"]
            if auto_sync == "1":
                # Trigger sync to avalon action if auto sync was turned on
                ft_project = self.cur_project
                self.log.debug((
                    "Auto sync was turned on for project <{}>."
                    " Triggering syncToAvalon action."
                ).format(ft_project["full_name"]))
                selection = [{
                    "entityId": ft_project["id"],
                    "entityType": "show"
                }]
                self.trigger_action(
                    action_name="sync.to.avalon.server",
                    event=event,
                    selection=selection
                )
            # Exit for both cases
            return True

        # Filter updated data by changed keys
        updated = self.filter_updated(updated)

        # skip most of events where nothing has changed for avalon
        if (
            len(found_actions) == 1 and
            found_actions[0] == "update" and
            not updated
        ):
            self.log.debug("There are not actions to process after filtering")
            return True

        ft_project = self.cur_project
        # Check if auto-sync custom attribute exists
        if cust_attr_auto_sync not in ft_project["custom_attributes"]:
            # TODO should we sent message to someone?
            # TODO report
            self.log.error((
                "Custom attribute \"{}\" is not created or user \"{}\" used"
                " for Event server don't have permissions to access it!"
            ).format(cust_attr_auto_sync, self.session.api_user))
            return True

        # Skip if auto-sync is not set
        auto_sync = ft_project["custom_attributes"][cust_attr_auto_sync]
        if auto_sync is not True:
            self.log.debug("Auto sync is not turned on")
            return True

        # Get ftrack entities - find all ftrack ids first
        ftrack_ids = []
        for ftrack_id in updated:
            ftrack_ids.append(ftrack_id)

        for action, ftrack_ids in entities_by_action.items():
            # skip updated (already prepared) and removed (not exist in ftrack)
            if action in ["update", "remove"]:
                continue

            for ftrack_id in ftrack_ids:
                if ftrack_id not in ftrack_ids:
                    ftrack_ids.append(ftrack_id)

        if ftrack_ids:
            joined_ids = ", ".join(["\"{}\"".format(id) for id in ftrack_ids])
            ftrack_entities = self.process_session.query(
                self.entities_query_by_id.format(ft_project["id"], joined_ids)
            ).all()
            for entity in ftrack_entities:
                self.ftrack_ents_by_id[entity["id"]] = entity

        # Filter updates where name is changing
        for ftrack_id, ent_info in updated.items():
            ent_keys = ent_info["keys"]
            # Seprate update info from rename
            if "name" not in ent_keys:
                continue

            _ent_info = copy.deepcopy(ent_info)
            for ent_key in ent_keys:
                if ent_key == "name":
                    ent_info["changes"].pop(ent_key, None)
                    ent_info["keys"].remove(ent_key)
                else:
                    _ent_info["changes"].pop(ent_key, None)
                    _ent_info["keys"].remove(ent_key)

            self.ftrack_renamed[ftrack_id] = _ent_info

        self.ftrack_removed = entities_by_action["remove"]
        self.ftrack_moved = entities_by_action["move"]
        self.ftrack_added = entities_by_action["add"]
        self.ftrack_updated = updated

        self.log.debug("Main process started")
        time_1 = time.time()
        # 1.) Process removed - may affect all other actions
        self.process_removed()
        time_2 = time.time()
        # 2.) Process renamed - may affect added
        self.process_renamed()
        time_3 = time.time()
        # 3.) Process added - moved entity may be moved to new entity
        self.process_added()
        time_4 = time.time()
        # 4.) Process moved
        self.process_moved()
        time_5 = time.time()
        # 5.) Process updated
        self.process_updated()
        time_6 = time.time()
        # 6.) Process changes in hierarchy or hier custom attribues
        self.process_hier_cleanup()
        time_7 = time.time()

        self.log.debug("Main process finished")
        print(time_2 - time_1)
        print(time_3 - time_2)
        print(time_4 - time_3)
        print(time_5 - time_4)
        print(time_6 - time_5)
        print(time_7 - time_6)

        return True

    def process_removed(self):
        if not self.ftrack_removed:
            return
        ent_infos = self.ftrack_removed
        removable_ids = []
        recreate_ents = []
        removed_names = []
        for ftrack_id, removed in ent_infos.items():
            entity_type = removed["entity_type"]
            parent_id = removed["parentId"]
            removed_name = removed["changes"]["name"]["old"]
            if entity_type == "Task":
                avalon_ent = self.avalon_ents_by_ftrack_id.get(parent_id)
                if not avalon_ent:
                    self.log.debug((
                        "Parent entity of task was not found in avalon <{}>"
                    ).format(self.get_ent_path(ftrack_id)))
                    continue

                mongo_id = avalon_ent["_id"]
                if mongo_id not in self.task_changes_by_avalon_id:
                    self.task_changes_by_avalon_id[mongo_id] = (
                        avalon_ent["data"]["tasks"]
                    )

                if removed_name in self.task_changes_by_avalon_id[mongo_id]:
                    self.task_changes_by_avalon_id[mongo_id].remove(
                        removed_name
                    )

                continue

            avalon_ent = self.avalon_ents_by_ftrack_id.get(ftrack_id)
            if not avalon_ent:
                continue
            mongo_id = avalon_ent["_id"]
            if self.changeability_by_mongo_id[mongo_id]:
                removable_ids.append(mongo_id)
                removed_names.append(removed_name)
            else:
                recreate_ents.append(avalon_ent)

        if removable_ids:
            self.dbcon.update_many(
                {"_id": {"$in": removable_ids}, "type": "asset"},
                {"$set": {"type": "archived_asset"}}
            )
            self.remove_cached_by_key("id", removable_ids)

        if recreate_ents:
            # sort removed entities by parents len
            # - length of parents determine hierarchy level
            recreate_ents = sorted(
                recreate_ents.items(),
                key=(lambda line: len(
                    (line[1].get("data", {}).get("parents") or [])
                ))
            )

            proj, ents = self.avalon_entities
            for avalon_entity in recreate_ents:
                old_ftrack_id = avalon_entity["data"]["ftrackId"]
                vis_par = avalon_entity["data"]["visualParent"]
                if vis_par is None:
                    vis_par = proj["_id"]
                parent_ent = self.avalon_ents_by_id[vis_par]
                parent_ftrack_id = parent_ent["data"]["ftrackId"]
                parent_ftrack_ent = self.ftrack_ents_by_id.get(
                    parent_ftrack_id
                )
                if not parent_ftrack_ent:
                    if parent_ent["type"].lower() == "project":
                        parent_ftrack_ent = self.cur_project
                    else:
                        parent_ftrack_ent = self.process_session.query(
                            self.entities_query_by_id.format(
                                self.cur_project["id"], parent_ftrack_id
                            )
                        ).one()
                entity_type = avalon_entity["data"]["entityType"]
                new_entity = self.process_session.create(entity_type, {
                    "name": avalon_entity["name"],
                    "parent": parent_ftrack_ent
                })
                try:
                    self.process_session.commit()
                except Exception:
                    # TODO logging
                    # TODO report
                    self.process_session.rolback()
                    continue

                new_entity_id = new_entity["id"]
                avalon_entity["data"]["ftrackId"] = new_entity_id

                for key, val in avalon_entity["data"].items():
                    if not val:
                        continue
                    if key not in new_entity["custom_attributes"]:
                        continue

                    new_entity["custom_attributes"][key] = val

                new_entity["custom_attributes"][cust_attr_id_key] = (
                    str(avalon_entity["_id"])
                )
                try:
                    self.process_session.commit()
                except Exception:
                    # TODO logging
                    # TODO report
                    self.process_session.rolback()
                    self.log.warning(
                        "Process session commit failed!",
                        exc_info=True
                    )
                    continue

                self.ftrack_recreated_mapping[old_ftrack_id] = new_entity_id
                self.process_session.commit()

                found_idx = None
                for idx, _entity in enumerate(self._avalon_ents):
                    if _entity["_id"] == avalon_entity["_id"]:
                        found_idx = idx
                        break

                if found_idx is None:
                    continue

                # Prepare updates dict for mongo update
                if "data" not in self.updates[avalon_entity["_id"]]:
                    self.updates[avalon_entity["_id"]]["data"] = {}

                self.updates[avalon_entity["_id"]]["data"]["ftrackId"] = (
                    new_entity_id
                )
                # Update cached entities
                self._avalon_ents[found_idx] = avalon_entity

                if self._avalon_ents_by_id is not None:
                    mongo_id = avalon_entity["_id"]
                    self._avalon_ents_by_id[mongo_id] = avalon_entity

                if self._avalon_ents_by_parent_id is not None:
                    vis_par = avalon_entity["data"]["visualParent"]
                    children = self._avalon_ents_by_parent_id[vis_par]
                    found_idx = None
                    for idx, _entity in enumerate(children):
                        if _entity["_id"] == avalon_entity["_id"]:
                            found_idx = idx
                            break
                    children[found_idx] = avalon_entity
                    self._avalon_ents_by_parent_id[vis_par] = children

                if self._avalon_ents_by_ftrack_id is not None:
                    self._avalon_ents_by_ftrack_id.pop(old_ftrack_id)
                    self._avalon_ents_by_ftrack_id[new_entity_id] = (
                        avalon_entity
                    )

                if self._avalon_ents_by_name is not None:
                    name = avalon_entity["name"]
                    self._avalon_ents_by_name[name] = avalon_entity

        # Check if entities with same name can be synchronized
        if not removed_names:
            return

        self.check_names_synchronizable(removed_names)

    def check_names_synchronizable(self, names):
        """Check if entities with specific names are importable.

        This check should happend after removing entity or renaming entity.
        When entity was removed or renamed then it's name is possible to sync.
        """
        joined_passed_names = ", ".join(
            ["\"{}\"".format(name) for name in names]
        )
        same_name_entities = self.process_session.query(
            self.entities_name_query_by_name.format(
                self.cur_project["id"], joined_passed_names
            )
        ).all()
        if not same_name_entities:
            return

        entities_by_name = collections.defaultdict(list)
        for entity in same_name_entities:
            entities_by_name[entity["name"]].append(entity)

        synchronizable_ents = []
        self.log.debug((
            "Deleting of entities should allow to synchronize another entities"
            " with same name."
        ))
        for name, ents in entities_by_name.items():
            if len(ents) != 1:
                self.log.debug((
                    "Name \"{}\" still have more than one entity <{}>"
                ).format(
                    name, "| ".join(
                        [self.get_ent_path(ent["id"]) for ent in ents]
                    )
                ))
                continue

            entity = ents[0]
            self.log.debug("Checking if can synchronize entity <{}>".format(
                self.get_ent_path(entity["id"])
            ))
            # skip if already synchronized
            ftrack_id = entity["id"]
            if ftrack_id in self.avalon_ents_by_ftrack_id:
                self.log.debug("Entity is already synchronized")
                continue

            parent_id = entity["parent_id"]
            if parent_id not in self.avalon_ents_by_ftrack_id:
                self.log.debug(
                    "Entity's parent entity doesn't seems to be synchronized."
                )
                continue

            synchronizable_ents.append(entity)

        if not synchronizable_ents:
            return

        synchronizable_ents = sorted(
            synchronizable_ents,
            key=(lambda entity: len(entity["link"]))
        )

        children_queue = queue.Queue()
        for entity in synchronizable_ents:
            parent_avalon_ent = self.avalon_ents_by_ftrack_id[
                entity["parent_id"]
            ]
            self.create_entity_in_avalon(entity, parent_avalon_ent)

            for child in entity["children"]:
                if child.entity_type.lower() == "task":
                    continue
                children_queue.put(child)

        while not children_queue.empty():
            entity = children_queue.get()
            ftrack_id = entity["id"]
            name = entity["name"]
            ent_by_ftrack_id = self.avalon_ents_by_ftrack_id.get(ftrack_id)
            if ent_by_ftrack_id:
                raise Exception((
                    "This is bug, parent was just synchronized to avalon"
                    " but entity is already in database {}"
                ).format(dict(entity)))

            # Entity has duplicated name with another entity
            # - may be renamed: in that case renaming method will handle that
            duplicate_ent = self.avalon_ents_by_name.get(name)
            if duplicate_ent:
                continue

            passed_regex = avalon_sync.check_regex(
                name, "asset", schema_patterns=self.regex_schemas
            )
            if not passed_regex:
                continue

            parent_id = entity["parent_id"]
            parent_avalon_ent = self.avalon_ents_by_ftrack_id[parent_id]

            self.create_entity_in_avalon(entity, parent_avalon_ent)

            for child in entity["children"]:
                if child.entity_type.lower() == "task":
                    continue
                children_queue.put(child)

    def create_entity_in_avalon(self, ftrack_ent, parent_avalon):
        proj, ents = self.avalon_entities

        # Parents, Hierarchy
        ent_path_items = [ent["name"] for ent in ftrack_ent["link"]]
        parents = ent_path_items[1:len(ent_path_items)-1:]
        hierarchy = ""
        if len(parents) > 0:
            hierarchy = os.path.sep.join(parents)

        # Tasks
        tasks = []
        for child in ftrack_ent["children"]:
            if child.entity_type.lower() != "task":
                continue
            tasks.append(child["name"])

        # Visual Parent
        vis_par = None
        if parent_avalon["type"].lower() != "project":
            vis_par = parent_avalon["_id"]

        mongo_id = ObjectId()
        name = ftrack_ent["name"]
        final_entity = {
            "_id": mongo_id,
            "name": name,
            "type": "asset",
            "schema": entity_schemas["asset"],
            "parent": proj["_id"],
            "data": {
                "ftrackId": ftrack_ent["id"],
                "entityType": ftrack_ent.entity_type,
                "parents": parents,
                "hierarchy": hierarchy,
                "tasks": tasks,
                "visualParent": vis_par
            }
        }
        cust_attrs = self.get_cust_attr_values(ftrack_ent)
        for key, val in cust_attrs.items():
            final_entity["data"][key] = val

        test_queue = queue.Queue()
        test_queue.put(final_entity)
        while not test_queue.empty():
            in_dict = test_queue.get()
            for key, val in in_dict.items():
                if isinstance(val, dict):
                    test_queue.put(val)
                    continue

        schema.validate(final_entity)

        replaced = False
        archived = self.avalon_archived_by_name.get(name)
        if archived:
            archived_id = archived["_id"]
            if (
                archived["data"]["parents"] == parents or
                self.changeability_by_mongo_id[archived_id]
            ):
                mongo_id = archived_id
                final_entity["_id"] = mongo_id
                self.dbcon.replace_one({"_id": mongo_id}, final_entity)
                replaced = True

        if not replaced:
            self.dbcon.insert_one(final_entity)

        ftrack_ent["custom_attributes"][cust_attr_id_key] = str(mongo_id)
        try:
            self.process_session.commit()
        except Exception:
            self.process_session.rolback()
            # TODO logging
            # TODO report

        # modify cached data
        # Skip if self._avalon_ents is not set(maybe never happen)
        if self._avalon_ents is None:
            return final_entity

        if self._avalon_ents is not None:
            proj, ents = self._avalon_ents
            ents.append(final_entity)
            self._avalon_ents = (proj, ents)

        if self._avalon_ents_by_id is not None:
            self._avalon_ents_by_id[mongo_id] = final_entity

        if self._avalon_ents_by_parent_id is not None:
            self._avalon_ents_by_parent_id[vis_par].append(final_entity)

        if self._avalon_ents_by_ftrack_id is not None:
            self._avalon_ents_by_ftrack_id[ftrack_ent["id"]] = final_entity

        if self._avalon_ents_by_name is not None:
            self._avalon_ents_by_name[ftrack_ent["name"]] = final_entity

        return final_entity

    def get_cust_attr_values(self, entity, keys=None):
        output = {}
        custom_attrs, hier_attrs = self.avalon_custom_attributes
        not_processed_keys = True
        if keys:
            not_processed_keys = [k for k in keys]
        # Notmal custom attributes
        processed_keys = []
        for attr in custom_attrs:
            if not not_processed_keys:
                break
            key = attr["key"]
            if key in processed_keys:
                continue
            if key.startswith("avalon_"):
                continue

            if key not in entity["custom_attributes"]:
                continue

            if keys:
                if key not in keys:
                    continue
                else:
                    not_processed_keys.remove(key)

            output[key] = entity["custom_attributes"][key]
            processed_keys.append(key)

        if not not_processed_keys:
            return output

        # Hierarchical cust attrs
        hier_keys = []
        defaults = {}
        for attr in hier_attrs:
            key = attr["key"]
            if key.startswith("avalon_"):
                continue

            if keys and key not in keys:
                continue
            hier_keys.append(key)
            defaults[key] = attr["default"]

        hier_values = avalon_sync.get_hierarchical_attributes(
            self.process_session, entity, hier_keys, defaults
        )
        for key, val in hier_values.items():
            output[key] = val

        return output

    def process_renamed(self):
        if not self.ftrack_renamed:
            return

        ent_infos = self.ftrack_renamed
        renamed_tasks = {}
        not_found = {}
        changeable_queue = queue.Queue()
        for ftrack_id, ent_info in ent_infos.items():
            entity_type = ent_info["entity_type"]
            new_name = ent_info["changes"]["name"]["new"]
            old_name = ent_info["changes"]["name"]["old"]
            if entity_type == "Task":
                parent_id = ent_info["parentId"]
                renamed_tasks[parent_id] = {
                    "new": new_name,
                    "old": old_name,
                    "ent_info": ent_info
                }
                continue

            avalon_ent = self.avalon_ents_by_ftrack_id.get(ftrack_id)
            if not avalon_ent:
                not_found[ftrack_id] = ent_info
                continue

            if new_name == avalon_ent["name"]:
                continue

            mongo_id = avalon_ent["_id"]
            if self.changeability_by_mongo_id[mongo_id]:
                changeable_queue.put((ftrack_id, avalon_ent, new_name))
            else:
                ftrack_ent = self.ftrack_ents_by_id[ftrack_id]
                ftrack_ent["name"] = avalon_ent["name"]
                try:
                    self.process_session.commit()
                except Exception:
                    self.process_session.rollback()
                    # TODO report
                    # TODO logging
                    self.log.warning(
                        "Process session commit failed!",
                        exc_info=True
                    )

        old_names = []
        # Process renaming in Avalon DB
        while not changeable_queue.empty():
            ftrack_id, avalon_ent, new_name = changeable_queue.get()
            mongo_id = avalon_ent["_id"]
            old_name = avalon_ent["name"]

            _entity_type = "asset"
            if entity_type == "Project":
                _entity_type = "project"

            passed_regex = avalon_sync.check_regex(
                new_name, _entity_type, schema_patterns=self.regex_schemas
            )
            ent_path = self.get_ent_path(ftrack_id)
            if not passed_regex:
                # TODO report
                # TODO logging
                # new name does not match regex (letters numbers and _)
                # TODO move this to special report method
                self.log.warning(
                    "Entity name contain invalid symbols <{}>".format(ent_path)
                )
                continue

            # if avalon does not have same name then can be changed
            same_name_avalon_ent = self.avalon_ents_by_name.get(new_name)
            if not same_name_avalon_ent:
                old_val = self._avalon_ents_by_name.pop(old_name)
                old_val["name"] = new_name
                self._avalon_ents_by_name[new_name] = old_val
                self.updates[mongo_id] = {"name": new_name}
                self.renamed_in_avalon.append(mongo_id)

                old_names.append(old_name)
                if new_name in old_names:
                    old_names.remove(new_name)

                # TODO report
                # TODO logging
                self.log.debug(
                    "Name of entity will be changed to \"{}\" <{}>".format(
                        new_name, ent_path
                    )
                )
                continue

            # Check if same name is in changable_queue
            # - it's name may be changed in next iteration
            same_name_ftrack_id = same_name_avalon_ent["data"]["ftrackId"]
            same_is_unprocessed = False
            for item in list(changeable_queue.queue):
                if same_name_ftrack_id == item[0]:
                    same_is_unprocessed = True
                    break

            if same_is_unprocessed:
                changeable_queue.put((ftrack_id, avalon_ent, new_name))
                continue

            # TODO report
            # TODO logging
            # Duplicated entity name
            # TODO move this to special report method
            self.log.warning(
                "Entity name is duplicated in the project <{}>".format(
                    ent_path
                )
            )

        if old_names:
            self.check_names_synchronizable(old_names)

        for parent_id, task_change in renamed_tasks.items():
            avalon_ent = self.avalon_ents_by_ftrack_id.get(parent_id)
            ent_info = task_change["ent_info"]
            if not avalon_ent:
                not_found[ent_info["entityId"]] = ent_info
                continue

            mongo_id = avalon_ent["_id"]
            if mongo_id not in self.task_changes_by_avalon_id:
                self.task_changes_by_avalon_id[mongo_id] = (
                    avalon_ent["data"]["tasks"]
                )

            new_name = task_change["new"]
            old_name = task_change["old"]
            passed_regex = avalon_sync.check_regex(
                new_name, "task", schema_patterns=self.regex_schemas
            )
            if not passed_regex:
                # TODO report
                # TODO logging
                ftrack_id = ent_info["enityId"]
                ent_path = self.get_ent_path(ftrack_id)
                self.log.warning((
                    "Name of renamed entity <{}> contain invalid symbols"
                ).format(ent_path))
                # TODO should we rename back to previous name?
                # entity = self.ftrack_ents_by_id[ftrack_id]
                # entity["name"] = old_name
                # try:
                #     self.process_session.commit()
                #     # TODO report
                #     # TODO logging
                # except Exception:
                #     self.process_session.rollback()
                #     # TODO report
                #     # TODO logging
                #     self.log.warning(
                #         "Process session commit failed!",
                #         exc_info=True
                #     )

                continue

            if old_name in self.task_changes_by_avalon_id[mongo_id]:
                self.task_changes_by_avalon_id[mongo_id].remove(old_name)

            if new_name not in self.task_changes_by_avalon_id[mongo_id]:
                self.task_changes_by_avalon_id[mongo_id].append(new_name)

        # not_found are not processed since all not found are not found
        # because they are not synchronizable

    def process_added(self):
        ent_infos = self.ftrack_added
        if not ent_infos:
            return

        # Skip if already exit in avalon db or tasks entities
        # - happen when was created by any sync event/action
        pop_out_ents = []
        new_tasks_by_parent = collections.defaultdict(list)
        _new_ent_infos = {}
        for ftrack_id, ent_info in ent_infos.items():
            if self.avalon_ents_by_ftrack_id.get(ftrack_id):
                pop_out_ents.append(ftrack_id)
                continue

            if ent_info["entity_type"] == "Task":
                parent_id = ent_info["parentId"]
                new_tasks_by_parent[parent_id].append(ent_info)
                pop_out_ents.append(ftrack_id)

        for ftrack_id in pop_out_ents:
            ent_infos.pop(ftrack_id)

        # sort by parents length (same as by hierarchy level)
        _ent_infos = sorted(
            ent_infos.values(),
            key=(lambda ent_info: len(ent_info.get("parents", [])))
        )
        to_sync_by_id = collections.OrderedDict()
        for ent_info in _ent_infos:
            ft_id = ent_info["entityId"]
            to_sync_by_id[ft_id] = self.ftrack_ents_by_id[ft_id]

        # cache regex success (for tasks)
        duplicated = []
        regex_failed = []
        for ftrack_id, entity in to_sync_by_id.items():
            if entity.entity_type.lower() == "project":
                raise Exception((
                    "Project can't be created with event handler!"
                    "This is a bug"
                ))
            parent_id = entity["parent_id"]
            parent_avalon = self.avalon_ents_by_ftrack_id.get(parent_id)
            if not parent_avalon:
                continue

            is_synchonizable = True
            name = entity["name"]
            passed_regex = avalon_sync.check_regex(
                name, "asset", schema_patterns=self.regex_schemas
            )
            if not passed_regex:
                regex_failed.append(ftrack_id)
                is_synchonizable = False

            if name in self.avalon_ents_by_name:
                duplicated.append(ftrack_id)
                is_synchonizable = False

            if not is_synchonizable:
                continue

            self.create_entity_in_avalon(entity, parent_avalon)

        for parent_id, ent_infos in new_tasks_by_parent.items():
            avalon_ent = self.avalon_ents_by_ftrack_id.get(parent_id)
            if not avalon_ent:
                continue

            mongo_id = avalon_ent["_id"]
            if mongo_id not in self.task_changes_by_avalon_id:
                self.task_changes_by_avalon_id[mongo_id] = (
                    avalon_ent["data"]["tasks"]
                )

            for ent_info in ent_infos:
                new_name = ent_info["changes"]["name"]["new"]
                if new_name not in self.task_changes_by_avalon_id[mongo_id]:
                    self.task_changes_by_avalon_id[mongo_id].append(new_name)

        # TODO process duplicates and regex failed entities

    def process_moved(self):
        if not self.ftrack_moved:
            return

        ftrack_moved = {k: v for k, v in sorted(
            self.ftrack_moved.items(),
            key=(lambda line: len(
                (line[1].get("data", {}).get("parents") or [])
            ))
        )}

        for ftrack_id, ent_info in ftrack_moved.items():
            avalon_ent = self.avalon_ents_by_ftrack_id.get(ftrack_id)
            if not avalon_ent:
                continue

            new_parent_id = ent_info["changes"]["parent_id"]["new"]
            old_parent_id = ent_info["changes"]["parent_id"]["old"]

            mongo_id = avalon_ent["_id"]
            if self.changeability_by_mongo_id[mongo_id]:
                par_av_ent = self.avalon_ents_by_ftrack_id.get(new_parent_id)
                if not par_av_ent:
                    # TODO logging
                    # TODO report
                    ent_path_items = [self.cur_project["full_name"]]
                    ent_path_items.extend(avalon_ent["data"]["parents"])
                    ent_path = "/".join(ent_path_items)
                    self.log.warning((
                        "Parent of moved entity <{}> does not exist"
                    ).format(ent_path))
                    continue
                # THIS MUST HAPPEND AFTER CREATING NEW ENTITIES !!!!
                # - because may be moved to new created entity
                if "data" not in self.updates[mongo_id]:
                    self.updates[mongo_id]["data"] = {}
                self.updates[mongo_id]["data"]["visualParent"] = (
                    par_av_ent["_id"]
                )
                self.moved_in_avalon.append(mongo_id)

            else:
                if old_parent_id in self.ftrack_recreated_mapping:
                    old_parent_id = (
                        self.ftrack_recreated_mapping[old_parent_id]
                    )
                ftrack_ent = self.ftrack_ents_by_id[ftrack_id]
                ftrack_ent["parent_id"] = old_parent_id
                try:
                    self.process_session.commit()
                except Exception:
                    self.process_session.rollback()
                    # TODO logging
                    # TODO report
                    self.log.warning(
                        "Process session commit failed!",
                        exc_info=True
                    )

    def process_updated(self):
        # Only custom attributes changes should get here
        if not self.ftrack_updated:
            return

        ent_infos = self.ftrack_updated
        ftrack_mongo_mapping = {}
        not_found_ids = []
        for ftrack_id, ent_info in ent_infos.items():
            avalon_ent = self.avalon_ents_by_ftrack_id.get(ftrack_id)
            if not avalon_ent:
                not_found_ids.append(ftrack_id)
                continue

            ftrack_mongo_mapping[ftrack_id] = avalon_ent["_id"]

        for ftrack_id in not_found_ids:
            ent_infos.pop(ftrack_id)

        if not ent_infos:
            return

        cust_attrs, hier_attrs = self.avalon_cust_attrs
        cust_attrs_by_obj_id = collections.defaultdict(dict)
        for cust_attr in cust_attrs:
            key = cust_attr["key"]
            if key.startswith("avalon_"):
                continue

            ca_ent_type = cust_attr["entity_type"]

            if ca_ent_type == "show":
                cust_attrs_by_obj_id[ca_ent_type][key] = cust_attr
            else:
                obj_id = cust_attr["object_type_id"]
                cust_attrs_by_obj_id[obj_id][key] = cust_attr

        hier_attrs_keys = [attr["key"] for attr in hier_attrs]

        for ftrack_id, ent_info in ent_infos.items():
            mongo_id = ftrack_mongo_mapping[ftrack_id]
            entType = ent_info["entityType"]
            if entType == "show":
                ent_cust_attrs = cust_attrs_by_obj_id.get("show")
            else:
                obj_type_id = ent_info["objectTypeId"]
                ent_cust_attrs = cust_attrs_by_obj_id.get(obj_type_id)

            for key, values in ent_info["changes"].items():
                if key in hier_attrs_keys:
                    self.hier_cust_attrs_changes[key].append(ftrack_id)
                    continue

                if key not in ent_cust_attrs:
                    continue

                if "data" not in self.updates[mongo_id]:
                    self.updates[mongo_id]["data"] = {}
                value = values["new"]
                self.updates[mongo_id]["data"][key] = value

    def process_hier_cleanup(self):
        if (
            not self.moved_in_avalon and
            not self.renamed_in_avalon and
            not self.hier_cust_attrs_changes and
            not self.task_changes_by_avalon_id
        ):
            return

        cust_attrs, hier_attrs = self.avalon_cust_attrs

        parent_changes = []
        hier_cust_attrs_ids = []
        hier_cust_attrs_keys = []
        all_keys = False
        for mongo_id in self.moved_in_avalon:
            parent_changes.append(mongo_id)
            hier_cust_attrs_ids.append(mongo_id)
            all_keys = True

        for mongo_id in self.renamed_in_avalon:
            if mongo_id not in parent_changes:
                parent_changes.append(mongo_id)

        for key, ftrack_ids in self.hier_cust_attrs_changes.items():
            if key.startswith("avalon_"):
                continue
            for ftrack_id in ftrack_ids:
                avalon_ent = self.avalon_ents_by_ftrack_id[ftrack_id]
                mongo_id = avalon_ent["_id"]
                if mongo_id in hier_cust_attrs_ids:
                    continue
                hier_cust_attrs_ids.append(mongo_id)
                if not all_keys and key not in hier_cust_attrs_keys:
                    hier_cust_attrs_keys.append(key)

        # Tasks preparation ****
        for mongo_id, tasks in self.task_changes_by_avalon_id.items():
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            if "data" not in self.updates[mongo_id]:
                self.updates[mongo_id]["data"] = {}

            self.updates[mongo_id]["data"]["tasks"] = tasks

        # Parents preparation ***
        mongo_to_ftrack_parents = {}
        for mongo_id in parent_changes:
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            ftrack_id = avalon_ent["data"]["ftrackId"]
            ftrack_ent = self.ftrack_ents_by_id[ftrack_id]
            mongo_to_ftrack_parents[mongo_id] = len(ftrack_ent["link"])

        stored_parents_by_mongo = {}
        # sort by hierarchy level
        mongo_to_ftrack_parents = [k for k, v in sorted(
            mongo_to_ftrack_parents.items(),
            key=(lambda item: item[1])
        )]
        for mongo_id in mongo_to_ftrack_parents:
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            vis_par = avalon_ent["data"]["visualParent"]
            if vis_par in stored_parents_by_mongo:
                parents = [par for par in stored_parents_by_mongo[vis_par]]
                if vis_par is not None:
                    parent_ent = self.avalon_ents_by_id[vis_par]
                    parents.append(parent_ent["name"])
                stored_parents_by_mongo[mongo_id] = parents
                continue

            ftrack_id = avalon_ent["data"]["ftrackId"]
            ftrack_ent = self.ftrack_ents_by_id[ftrack_id]
            ent_path_items = [ent["name"] for ent in ftrack_ent["link"]]
            parents = ent_path_items[1:len(ent_path_items)-1:]
            stored_parents_by_mongo[mongo_id] = parents

        for mongo_id, parents in stored_parents_by_mongo.items():
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            cur_par = avalon_ent["data"]["parents"]
            if cur_par == parents:
                continue

            hierarchy = ""
            if len(parents) > 0:
                hierarchy = os.path.sep.join(parents)

            if "data" not in self.updates[mongo_id]:
                self.updates[mongo_id]["data"] = {}
            self.updates[mongo_id]["data"]["parents"] = parents
            self.updates[mongo_id]["data"]["hierarchy"] = hierarchy

        # Skip custom attributes if didn't change
        if not hier_cust_attrs_ids:
            self.update_entities()
            return

        # Hierarchical custom attributes preparation ***
        if all_keys:
            hier_cust_attrs_keys = [
                attr["key"] for attr in hier_attrs if (
                    not attr["key"].startswith("avalon_")
                )
            ]

        mongo_ftrack_mapping = {}
        cust_attrs_ftrack_ids = []
        # ftrack_parenting = collections.defaultdict(list)
        entities_dict = collections.defaultdict(dict)

        children_queue = queue.Queue()
        parent_queue = queue.Queue()

        for mongo_id in hier_cust_attrs_ids:
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            parent_queue.put(avalon_ent)
            ftrack_id = avalon_ent["data"]["ftrackId"]
            if ftrack_id not in entities_dict:
                entities_dict[ftrack_id] = {
                    "children": [],
                    "parent_id": None,
                    "hier_attrs": {}
                }

            mongo_ftrack_mapping[mongo_id] = ftrack_id
            cust_attrs_ftrack_ids.append(ftrack_id)
            children_ents = self.avalon_ents_by_parent_id.get(mongo_id) or []
            for children_ent in children_ents:
                _ftrack_id = children_ent["data"]["ftrackId"]
                if _ftrack_id in entities_dict:
                    continue

                entities_dict[_ftrack_id] = {
                    "children": [],
                    "parent_id": None,
                    "hier_attrs": {}
                }
                # if _ftrack_id not in ftrack_parenting[ftrack_id]:
                #     ftrack_parenting[ftrack_id].append(_ftrack_id)
                entities_dict[_ftrack_id]["parent_id"] = ftrack_id
                if _ftrack_id not in entities_dict[ftrack_id]["children"]:
                    entities_dict[ftrack_id]["children"].append(_ftrack_id)
                children_queue.put(children_ent)

        while not children_queue.empty():
            avalon_ent = children_queue.get()
            mongo_id = avalon_ent["_id"]
            ftrack_id = avalon_ent["data"]["ftrackId"]
            if ftrack_id in cust_attrs_ftrack_ids:
                continue

            mongo_ftrack_mapping[mongo_id] = ftrack_id
            cust_attrs_ftrack_ids.append(ftrack_id)

            children_ents = self.avalon_ents_by_parent_id.get(mongo_id) or []
            for children_ent in children_ents:
                _ftrack_id = children_ent["data"]["ftrackId"]
                if _ftrack_id in entities_dict:
                    continue

                entities_dict[_ftrack_id] = {
                    "children": [],
                    "parent_id": None,
                    "hier_attrs": {}
                }
                entities_dict[_ftrack_id]["parent_id"] = ftrack_id
                if _ftrack_id not in entities_dict[ftrack_id]["children"]:
                    entities_dict[ftrack_id]["children"].append(_ftrack_id)
                children_queue.put(children_ent)

        while not parent_queue.empty():
            avalon_ent = parent_queue.get()
            if avalon_ent["type"].lower() == "project":
                continue

            ftrack_id = avalon_ent["data"]["ftrackId"]

            vis_par = avalon_ent["data"]["visualParent"]
            if vis_par is None:
                vis_par = avalon_ent["parent"]

            parent_ent = self.avalon_ents_by_id[vis_par]
            parent_ftrack_id = parent_ent["data"]["ftrackId"]
            if parent_ftrack_id not in entities_dict:
                entities_dict[parent_ftrack_id] = {
                    "children": [],
                    "parent_id": None,
                    "hier_attrs": {}
                }

            if ftrack_id not in entities_dict[parent_ftrack_id]["children"]:
                entities_dict[parent_ftrack_id]["children"].append(ftrack_id)

            entities_dict[ftrack_id]["parent_id"] = parent_ftrack_id

            if parent_ftrack_id in cust_attrs_ftrack_ids:
                continue
            mongo_ftrack_mapping[vis_par] = parent_ftrack_id
            cust_attrs_ftrack_ids.append(parent_ftrack_id)
            # if ftrack_id not in ftrack_parenting[parent_ftrack_id]:
            #     ftrack_parenting[parent_ftrack_id].append(ftrack_id)

            parent_queue.put(parent_ent)

        # Prepare values to query
        entity_ids_joined = ", ".join([
            "\"{}\"".format(id) for id in cust_attrs_ftrack_ids
        ])
        attributes_joined = ", ".join([
            "\"{}\"".format(name) for name in hier_cust_attrs_keys
        ])
        [values] = self.process_session._call([{
            "action": "query",
            "expression": (
                "select value, entity_id from CustomAttributeValue "
                "where entity_id in ({}) and configuration.key in ({})"
            ).format(entity_ids_joined, attributes_joined)
        }])
        ftrack_project_id = self.cur_project["id"]

        for attr in hier_attrs:
            key = attr["key"]
            if key not in hier_cust_attrs_keys:
                continue
            entities_dict[ftrack_project_id]["hier_attrs"][key] = (
                attr["default"]
            )

        # PREPARE DATA BEFORE THIS
        avalon_hier = []
        for value in values["data"]:
            if value["value"] is None:
                continue
            entity_id = value["entity_id"]
            key = value["configuration"]["key"]
            entities_dict[entity_id]["hier_attrs"][key] = value["value"]

        # Get dictionary with not None hierarchical values to pull to childs
        project_values = {}
        for key, value in (
            entities_dict[ftrack_project_id]["hier_attrs"].items()
        ):
            if value is not None:
                project_values[key] = value

        for key in avalon_hier:
            value = entities_dict[ftrack_project_id]["avalon_attrs"][key]
            if value is not None:
                project_values[key] = value

        hier_down_queue = queue.Queue()
        hier_down_queue.put((project_values, ftrack_project_id))

        while not hier_down_queue.empty():
            hier_values, parent_id = hier_down_queue.get()
            for child_id in entities_dict[parent_id]["children"]:
                _hier_values = hier_values.copy()
                for name in hier_cust_attrs_keys:
                    value = entities_dict[child_id]["hier_attrs"].get(name)
                    if value is not None:
                        _hier_values[name] = value

                entities_dict[child_id]["hier_attrs"].update(_hier_values)
                hier_down_queue.put((_hier_values, child_id))

        ftrack_mongo_mapping = {}
        for mongo_id, ftrack_id in mongo_ftrack_mapping.items():
            ftrack_mongo_mapping[ftrack_id] = mongo_id

        for ftrack_id, data in entities_dict.items():
            mongo_id = ftrack_mongo_mapping[ftrack_id]
            avalon_ent = self.avalon_ents_by_id[mongo_id]
            for key, value in data["hier_attrs"].items():
                if (
                    key in avalon_ent["data"] and
                    avalon_ent["data"][key] == value
                ):
                    continue

                if "data" not in self.updates[mongo_id]:
                    self.updates[mongo_id]["data"] = {}

                self.updates[mongo_id]["data"][key] = value

        self.update_entities()

    def update_entities(self):
        mongo_changes_bulk = []
        for mongo_id, changes in self.updates.items():
            filter = {"_id": mongo_id}
            change_data = avalon_sync.from_dict_to_set(changes)
            mongo_changes_bulk.append(UpdateOne(filter, change_data))

        if not mongo_changes_bulk:
            # TODO logging
            return
        self.dbcon.bulk_write(mongo_changes_bulk)


def register(session, plugins_presets):
    '''Register plugin. Called when used as an plugin.'''
    SyncToAvalonEvent(session, plugins_presets).register()
