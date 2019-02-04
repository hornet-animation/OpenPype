import os
import contextlib

import capture_gui
import clique

import pype.maya.lib as lib
import pype.api

from maya import cmds, mel
import pymel.core as pm
from pype.vendor import ffmpeg
reload(ffmpeg)


# TODO: move codec settings to presets
class ExtractQuicktime(pype.api.Extractor):
    """Extract Quicktime from viewport capture.

    Takes review camera and creates review Quicktime video based on viewport
    capture.

    """

    label = "Quicktime"
    hosts = ["maya"]
    families = ["review"]
    optional = True

    def process(self, instance):
        self.log.info("Extracting capture..")

        # get scene fps
        fps = mel.eval('currentTimeUnitToFPS()')

        # if start and end frames cannot be determined, get them
        # from Maya timeline
        start = instance.data.get("startFrame")
        end = instance.data.get("endFrame")
        if start is None:
            start = cmds.playbackOptions(query=True, animationStartTime=True)
        if end is None:
            end = cmds.playbackOptions(query=True, animationEndTime=True)
        self.log.info("start: {}, end: {}".format(start, end))
        handles = instance.data.get("handles", 0)
        if handles:
            start -= handles
            end += handles

        # get cameras
        camera = instance.data['review_camera']
        capture_preset = ""
        try:
            preset = lib.load_capture_preset(capture_preset)
        except:
            preset = {}
        self.log.info('using viewport preset: {}'.format(capture_preset))

        preset['camera'] = camera
        preset['format'] = "image"
        # preset['compression'] = "qt"
        preset['quality'] = 50
        preset['compression'] = "jpg"
        preset['start_frame'] = start
        preset['end_frame'] = end
        preset['camera_options'] = {
            "displayGateMask": False,
            "displayResolution": False,
            "displayFilmGate": False,
            "displayFieldChart": False,
            "displaySafeAction": False,
            "displaySafeTitle": False,
            "displayFilmPivot": False,
            "displayFilmOrigin": False,
            "overscan": 1.0,
            "depthOfField": cmds.getAttr("{0}.depthOfField".format(camera)),
        }

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

        with maintained_time():
            playblast = capture_gui.lib.capture_scene(preset)

        self.log.info("file list  {}".format(playblast))
        # self.log.info("Calculating HUD data overlay")

        collected_frames = os.listdir(stagingdir)
        collections, remainder = clique.assemble(collected_frames)
        input_path = os.path.join(
            stagingdir, collections[0].format('{head}{padding}{tail}'))
        self.log.info("input {}".format(input_path))

        movieFile = filename + ".mov"
        full_movie_path = os.path.join(stagingdir, movieFile)
        self.log.info("output {}".format(full_movie_path))

        try:
            (
                ffmpeg
                .input(input_path, framerate=fps, start_number=int(start))
                .output(full_movie_path)
                .run(overwrite_output=True,
                     capture_stdout=True,
                     capture_stderr=True)
            )
        except ffmpeg.Error as e:
            ffmpeg_error = 'ffmpeg error: {}'.format(e.stderr.decode())
            self.log.error(ffmpeg_error)
            raise Exception(ffmpeg_error)

        if "files" not in instance.data:
            instance.data["files"] = list()
        instance.data["files"].append(movieFile)


@contextlib.contextmanager
def maintained_time():
    ct = cmds.currentTime(query=True)
    try:
        yield
    finally:
        cmds.currentTime(ct, edit=True)
