import collections
from pype.modules.ftrack import BaseEvent


class TaskToVersionStatus(BaseEvent):
    """Changes status of task's latest AssetVersions on its status change."""

    # Attribute for caching session user id
    _cached_user_id = None

    # TODO remove `join_query_keys` as it should be in `BaseHandler`
    @staticmethod
    def join_query_keys(keys):
        """Helper to join keys to query."""
        return ",".join(["\"{}\"".format(key) for key in keys])

    def is_event_invalid(self, session, event):
        # Cache user id of currently running session
        if self._cached_user_id is None:
            session_user_entity = session.query(
                "User where username is \"{}\"".format(session.api_user)
            ).first()
            if not session_user_entity:
                self.log.warning(
                    "Couldn't query Ftrack user with username \"{}\"".format(
                        session.api_user
                    )
                )
                return False
            self._cached_user_id = session_user_entity["id"]

        # Skip processing if current session user was the user who created
        # the event
        user_info = event["source"].get("user") or {}
        user_id = user_info.get("id")

        # Mark as invalid if user is unknown
        if user_id is None:
            return True
        return user_id == self._cached_user_id

    def filter_event_entities(self, event):
        """Filter if event contain relevant data.

        Event cares only about changes of `statusid` on `entity_type` "Task".
        """

        entities_info = event["data"].get("entities")
        if not entities_info:
            return

        filtered_entity_info = collections.defaultdict(list)
        for entity_info in entities_info:
            # Care only about tasks
            if entity_info.get("entity_type") != "Task":
                continue

            # Care only about changes of status
            changes = entity_info.get("changes") or {}
            statusid_changes = changes.get("statusid") or {}
            if (
                statusid_changes.get("new") is None
                or statusid_changes.get("old") is None
            ):
                continue

            # Get project id from entity info
            project_id = None
            for parent_item in reversed(entity_info["parents"]):
                if parent_item["entityType"] == "show":
                    project_id = parent_item["entityId"]
                    break

            if project_id:
                filtered_entity_info[project_id].append(entity_info)

        return filtered_entity_info

    def _get_ent_path(self, entity):
        return "/".join(
            [ent["name"] for ent in entity["link"]]
        )

    def launch(self, session, event):
        '''Propagates status from version to task when changed'''
        if self.is_event_invalid(session, event):
            return

        filtered_entity_infos = self.filter_event_entities(event)
        if not filtered_entity_infos:
            return

        task_ids = [
            entity_info["entityId"]
            for entity_info in filtered_entity_infos
        ]
        joined_ids = ",".join(
            ["\"{}\"".format(entity_id) for entity_id in task_ids]
        )

        # Query tasks' AssetVersions
        asset_versions = session.query((
            "AssetVersion where task_id in ({}) order by version descending"
        ).format(joined_ids)).all()

        last_asset_version_by_task_id = (
            self.last_asset_version_by_task_id(asset_versions, task_ids)
        )
        if not last_asset_version_by_task_id:
            return

        # Query Task entities for last asset versions
        joined_filtered_ids = ",".join([
            "\"{}\"".format(entity_id)
            for entity_id in last_asset_version_by_task_id.keys()
        ])
        task_entities = session.query(
            "Task where id in ({})".format(joined_filtered_ids)
        ).all()
        if not task_entities:
            return

        # Final process of changing statuses
        av_statuses_by_low_name = self.asset_version_statuses(task_entities[0])
        for task_entity in task_entities:
            task_id = task_entity["id"]
            task_path = self._get_ent_path(task_entity)
            task_status_name = task_entity["status"]["name"]
            task_status_name_low = task_status_name.lower()

            last_asset_versions = last_asset_version_by_task_id[task_id]
            for last_asset_version in last_asset_versions:
                self.log.debug((
                    "Trying to change status of last AssetVersion {}"
                    " for task \"{}\""
                ).format(last_asset_version["version"], task_path))

                new_asset_version_status = av_statuses_by_low_name.get(
                    task_status_name_low
                )
                # Skip if tasks status is not available to AssetVersion
                if not new_asset_version_status:
                    self.log.debug((
                        "AssetVersion does not have matching status to \"{}\""
                    ).format(task_status_name))
                    continue

                av_ent_path = task_path + " Asset {} AssetVersion {}".format(
                    last_asset_version["asset"]["name"],
                    last_asset_version["version"]
                )

                # Skip if current AssetVersion's status is same
                current_status_name = last_asset_version["status"]["name"]
                if current_status_name.lower() == task_status_name_low:
                    self.log.debug((
                        "AssetVersion already has set status \"{}\". \"{}\""
                    ).format(current_status_name, av_ent_path))
                    continue

                # Change the status
                try:
                    last_asset_version["status"] = new_asset_version_status
                    session.commit()
                    self.log.info("[ {} ] Status updated to [ {} ]".format(
                        av_ent_path, new_asset_version_status["name"]
                    ))
                except Exception:
                    session.rollback()
                    self.log.warning(
                        "[ {} ]Status couldn't be set to \"{}\"".format(
                            av_ent_path, new_asset_version_status["name"]
                        ),
                        exc_info=True
                    )

    def get_asset_version_statuses(self, project_entity):
        """Status entities for AssetVersion from project's schema.

        Load statuses from project's schema and store them by id and name.

        Args:
            project_entity (ftrack_api.Entity): Entity of ftrack's project.

        Returns:
            tuple: 2 items are returned first are statuses by name
                second are statuses by id.
        """
        project_schema = project_entity["project_schema"]
        # Get all available statuses for Task
        statuses = project_schema.get_statuses("AssetVersion")
        # map lowered status name with it's object
        av_statuses_by_low_name = {}
        av_statuses_by_id = {}
        for status in statuses:
            av_statuses_by_low_name[status["name"].lower()] = status
            av_statuses_by_id[status["id"]] = status

        return av_statuses_by_low_name, av_statuses_by_id

    def find_last_asset_versions_for_task_ids(
        self, session, task_ids, asset_types_filter
    ):
        """Find latest AssetVersion entities for task.

        Find first latest AssetVersion for task and all AssetVersions with
        same version for the task.

        Args:
            asset_versions (list): AssetVersion entities sorted by "version".
            task_ids (list): Task ids.
            asset_types_filter (list): Asset types short names that will be
                used to filter AssetVersions. Filtering is skipped if entered
                value is empty list.
        """

        # Allow event only on specific asset type names
        asset_query_part = ""
        if asset_types_filter:
            # Query all AssetTypes
            asset_types = session.query(
                "select id, short from AssetType"
            ).all()
            # Store AssetTypes by id
            asset_type_short_by_id = {
                asset_type["id"]: asset_type["short"]
                for asset_type in asset_types
            }

            # Lower asset types from settings
            # WARNING: not sure if is good idea to lower names as Ftrack may
            #   contain asset type with name "Scene" and "scene"!
            asset_types_filter_low = set(
                asset_types_name.lower()
                for asset_types_name in asset_types_filter
            )
            asset_type_ids = []
            for type_id, short in asset_type_short_by_id.items():
                # TODO log if asset type name is not found
                if short.lower() in asset_types_filter_low:
                    asset_type_ids.append(type_id)

            # TODO log that none of asset type names were found in ftrack
            if asset_type_ids:
                asset_query_part = " and asset.type_id in ({})".format(
                    self.join_query_keys(asset_type_ids)
                )

        # Query tasks' AssetVersions
        asset_versions = session.query(
            (
               "select status_id, version, task_id, asset_id"
               " from AssetVersion where task_id in ({}){}}"
               " order by version descending"
            ).format(self.join_query_keys(task_ids), asset_query_part)
        ).all()

        last_asset_versions_by_task_id = collections.defaultdict(list)
        last_version_by_task_id = {}
        not_finished_task_ids = set(task_ids)
        for asset_version in asset_versions:
            task_id = asset_version["task_id"]
            # Check if task id is still in `not_finished_task_ids`
            if task_id not in not_finished_task_ids:
                continue

            version = asset_version["version"]

            # Find last version in `last_version_by_task_id`
            last_version = last_version_by_task_id.get(task_id)
            if last_version is None:
                # If task id does not have version set yet then it's first
                # AssetVersion for this task
                last_version_by_task_id[task_id] = version

            elif last_version > version:
                # Skip processing if version is lower than last version
                # and pop task id from `not_finished_task_ids`
                not_finished_task_ids.remove(task_id)
                continue

            # Add AssetVersion entity to output dictionary
            last_asset_versions_by_task_id[task_id].append(asset_version)

        return last_asset_versions_by_task_id


def register(session, plugins_presets):
    TaskToVersionStatus(session, plugins_presets).register()
