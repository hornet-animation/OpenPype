"""Collect global context Anatomy data.

Requires:
    context -> anatomy
    context -> projectEntity
    context -> assetEntity
    context -> username
    context -> datetimeData
    session -> AVALON_TASK

Provides:
    context -> anatomyData
"""

import os
import json

from openpype.settings import (
    get_system_settings
)
from avalon import api
import pyblish.api


class CollectAnatomyContextData(pyblish.api.ContextPlugin):
    """Collect Anatomy Context data.

    Example:
    context.data["anatomyData"] = {
        "project": {
            "name": "MyProject",
            "code": "myproj"
        },
        "asset": "AssetName",
        "hierarchy": "path/to/asset",
        "task": "Working",
        "username": "MeDespicable",

        *** OPTIONAL ***
        "app": "maya"       # Current application base name
        + mutliple keys from `datetimeData`         # see it's collector
    }
    """

    order = pyblish.api.CollectorOrder + 0.002
    label = "Collect Anatomy Context Data"

    def process(self, context):
        system_settings = get_system_settings()
        studio_name = system_settings["general"]["studio_name"]
        studio_code = system_settings["general"]["studio_code"]

        task_name = api.Session["AVALON_TASK"]

        project_entity = context.data["projectEntity"]
        asset_entity = context.data["assetEntity"]

        asset_tasks = asset_entity["data"]["tasks"]
        task_type = asset_tasks.get(task_name, {}).get("type")

        project_task_types = project_entity["config"]["tasks"]
        task_code = project_task_types.get(task_type, {}).get("short_name")

        asset_parents = asset_entity["data"]["parents"]
        hierarchy = "/".join(asset_parents)

        parent_name = project_entity["name"]
        if asset_parents:
            parent_name = asset_parents[-1]

        context_data = {
            "project": {
                "name": project_entity["name"],
                "code": project_entity["data"].get("code")
            },
            "asset": asset_entity["name"],
            "parent": parent_name,
            "hierarchy": hierarchy,
            "task": {
                "name": task_name,
                "type": task_type,
                "short": task_code,
            },
            "username": context.data["user"],
            "app": context.data["hostName"],
            "studio": {
                "name": studio_name,
                "code": studio_code
            }
        }

        datetime_data = context.data.get("datetimeData") or {}
        context_data.update(datetime_data)

        context.data["anatomyData"] = context_data

        self.log.info("Global anatomy Data collected")
        self.log.debug(json.dumps(context_data, indent=4))
