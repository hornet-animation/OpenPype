"""
Requires:
    CollectPublishedFiles
    CollectModules

Provides:
    Instance
"""
import pyblish.api
from openpype.hosts.tvpaint.worker import (
    TVPaintCommands,
    CollectSceneData
)
from avalon.tvpaint import CommunicationWrapper


class CollectTVPaintWorkfileData(pyblish.api.InstancePlugin):
    label = "Collect TVPaint Workfile data"
    order = pyblish.api.CollectorOrder + 0.1
    hosts = ["webpublisher"]
    # TODO add families filter

    def process(self, instance):
        # TODO change 'tvpaint_workfile' this is just dummy access
        workfile = instance.data["tvpaint_workfile"]
        # Get JobQueue module
        modules = instance.context.data["openPypeModules"]
        job_queue_module = modules["job_queue"]

        # Prepare tvpaint command
        commands = TVPaintCommands(workfile, CommunicationWrapper.communicator)
        commands.append(CollectSceneData())

        # Send job data to job queue server
        job_data = commands.to_job_data()
        job_id = job_queue_module.send_job("tvpaint", job_data)
        # Wait for job to be finished
        while True:
            job_status = job_queue_module.get_job_status(job_id)
            if job_status["done"]:
                break

        # Check if job state is done
        if job_status["state"] != "done":
            message = job_status["message"] or "Unknown issue"
            raise ValueError(
                "Job didn't finish properly."
                " Job state: \"{}\" | Job message: \"{}\"".format(
                    job_status["state"],
                    message
                )
            )
        instance.data["sceneData"] = job_status["result"]
