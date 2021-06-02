import os
import glob
import contextlib
import clique
import capture

from openpype.hosts.maya.api import lib
import openpype.api

from maya import cmds
import pymel.core as pm


class ExtractPlayblast(openpype.api.Extractor):
    """Extract viewport playblast.

    Takes review camera and creates review Quicktime video based on viewport
    capture.

    """

    label = "Extract Playblast"
    hosts = ["maya"]
    families = ["review"]
    optional = True
    capture_preset = {}

    def process(self, instance):
        self.log.info("Extracting capture..")

        # get scene fps
        fps = instance.data.get("fps") or instance.context.data.get("fps")

        # if start and end frames cannot be determined, get them
        # from Maya timeline
        start = instance.data.get("frameStartFtrack")
        end = instance.data.get("frameEndFtrack")
        if start is None:
            start = cmds.playbackOptions(query=True, animationStartTime=True)
        if end is None:
            end = cmds.playbackOptions(query=True, animationEndTime=True)

        self.log.info("start: {}, end: {}".format(start, end))

        # get cameras
        camera = instance.data['review_camera']

        preset = lib.load_capture_preset(data=self.capture_preset)


        preset['camera'] = camera
        preset['start_frame'] = start
        preset['end_frame'] = end
        camera_option = preset.get("camera_option", {})
        camera_option["depthOfField"] = cmds.getAttr(
            "{0}.depthOfField".format(camera))

        stagingdir = self.staging_dir(instance)
        filename = "{0}".format(instance.name)
        path = os.path.join(stagingdir, filename)

        self.log.info("Outputting images to %s" % path)

        preset['filename'] = path
        preset['overwrite'] = True

        pm.refresh(f=True)

        refreshFrameInt = int(pm.playbackOptions(q=True, minTime=True))
        pm.currentTime(refreshFrameInt - 1, edit=True)
        pm.currentTime(refreshFrameInt, edit=True)

        # Isolate view is requested by having objects in the set besides a
        # camera.
        if preset.pop("isolate_view", False) or instance.data.get("isolate"):
            preset["isolate"] = instance.data["setMembers"]

        # Show/Hide image planes on request.
        image_plane = instance.data.get("imagePlane", True)
        if "viewport_options" in preset:
            preset["viewport_options"]["imagePlane"] = image_plane
        else:
            preset["viewport_options"] = {"imagePlane": image_plane}

        with maintained_time():
            filename = preset.get("filename", "%TEMP%")

            # Force viewer to False in call to capture because we have our own
            # viewer opening call to allow a signal to trigger between
            # playblast and viewer
            preset['viewer'] = False

            self.log.info('using viewport preset: {}'.format(preset))

            path = capture.capture(**preset)

        self.log.debug("playblast path  {}".format(path))

        collected_files = os.listdir(stagingdir)
        collections, remainder = clique.assemble(collected_files)

        self.log.debug("filename {}".format(filename))
        frame_collection = None
        for collection in collections:
            filebase = collection.format('{head}').rstrip(".")
            self.log.debug("collection head {}".format(filebase))
            if filebase in filename:
                frame_collection = collection
                self.log.info(
                    "we found collection of interest {}".format(
                        str(frame_collection)))

        if "representations" not in instance.data:
            instance.data["representations"] = []

        tags = ["review"]
        if not instance.data.get("keepImages"):
            tags.append("delete")

        # Add camera node name to representation data
        camera_node_name = pm.ls(camera)[0].getTransform().name()

        representation = {
            'name': 'png',
            'ext': 'png',
            'files': list(frame_collection),
            "stagingDir": stagingdir,
            "frameStart": start,
            "frameEnd": end,
            'fps': fps,
            'preview': True,
            'tags': tags,
            'camera_name': camera_node_name
        }
        instance.data["representations"].append(representation)


@contextlib.contextmanager
def maintained_time():
    ct = cmds.currentTime(query=True)
    try:
        yield
    finally:
        cmds.currentTime(ct, edit=True)
