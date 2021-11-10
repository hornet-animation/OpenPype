"""
Requires:
    CollectPublishedFiles
    CollectModules

Provides:
    workfilePath - Path to tvpaint workfile
    sceneData - Scene data loaded from the workfile
    groupsData -
    layersData
    layersExposureFrames
    layersPrePostBehavior
"""
import os
import uuid
import shutil
import pyblish.api
from openpype.lib.plugin_tools import parse_json
from openpype.hosts.tvpaint.worker import (
    SenderTVPaintCommands,
    CollectSceneData
)


class CollectTVPaintWorkfileData(pyblish.api.InstancePlugin):
    label = "Collect TVPaint Workfile data"
    order = pyblish.api.CollectorOrder
    hosts = ["webpublisher"]
    targets = ["tvpaint"]

    def process(self, context):
        # Get JobQueue module
        modules = context.context.data["openPypeModules"]
        job_queue_module = modules["job_queue"]

        context_staging_dir = self._create_context_staging_dir(
            context, job_queue_module
        )
        workfile_path = self._extract_workfile_path(
            context, context_staging_dir
        )
        context.data["contextStagingDir"] = context_staging_dir
        context.data["workfilePath"] = workfile_path

        # Prepare tvpaint command
        collect_scene_data_command = CollectSceneData()
        # Create TVPaint sender commands
        commands = SenderTVPaintCommands(workfile_path, job_queue_module)
        commands.add_command(collect_scene_data_command)

        # Send job and wait for answer
        commands.send_job_and_wait()

        collected_data = collect_scene_data_command.result()
        layers_data = collected_data["layers_data"]
        groups_data = collected_data["groups_data"]
        scene_data = collected_data["scene_data"]
        exposure_frames_by_layer_id = (
            collected_data["exposure_frames_by_layer_id"]
        )
        pre_post_beh_by_layer_id = (
            collected_data["pre_post_beh_by_layer_id"]
        )

        # Store results
        # scene data store the same way as TVPaint collector
        context.data["sceneData"] = {
            "sceneWidth": scene_data["width"],
            "sceneHeight": scene_data["height"],
            "scenePixelAspect": scene_data["pixel_aspect"],
            "sceneFps": scene_data["fps"],
            "sceneFieldOrder": scene_data["field_order"],
            "sceneMarkIn": scene_data["mark_in"],
            # scene_data["mark_in_state"],
            "sceneMarkInState": scene_data["mark_in_set"],
            "sceneMarkOut": scene_data["mark_out"],
            # scene_data["mark_out_state"],
            "sceneMarkOutState": scene_data["mark_out_set"],
            "sceneStartFrame": scene_data["start_frame"],
            "sceneBgColor": scene_data["bg_color"]
        }
        # Store only raw data
        context.data["groupsData"] = groups_data
        context.data["layersData"] = layers_data
        context.data["layersExposureFrames"] = exposure_frames_by_layer_id
        context.data["layersPrePostBehavior"] = pre_post_beh_by_layer_id

    def _create_context_staging_dir(self, context, job_queue_module):
        work_root = job_queue_module.get_work_root()
        if not work_root:
            raise ValueError("Work root in JobQueue module is not set.")

        if not os.path.exists(work_root):
            os.makedirs(work_root)

        random_folder_name = str(uuid.uuid4())
        full_path = os.path.join(work_root, random_folder_name)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        return full_path

    def _extract_workfile_path(self, context, context_staging_dir):
        """Find first TVPaint file in tasks and use it."""
        batch_dir = context.data["batchDir"]
        batch_data = context.data["batchData"]
        src_workfile_path = None
        for task_id in batch_data["tasks"]:
            if src_workfile_path is not None:
                break
            task_dir = os.path.join(batch_dir, task_id)
            task_manifest_path = os.path.join(task_dir, "manifest.json")
            task_data = parse_json(task_manifest_path)
            task_files = task_data["files"]
            for filename in task_files:
                _, ext = os.path.splitext(filename)
                if ext.lower() == ".tvpp":
                    src_workfile_path = os.path.join(task_dir, filename)
                    break

        # Copy workfile to job queue work root
        new_workfile_path = os.path.join(
            context_staging_dir, os.path.basename(src_workfile_path)
        )
        shutil.copy(src_workfile_path, new_workfile_path)

        return new_workfile_path
