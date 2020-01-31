import os
import glob
import contextlib
import clique
import capture
#
import pype.maya.lib as lib
import pype.api
#
from maya import cmds, mel
import pymel.core as pm


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
        start = instance.data.get("startFrameReview")
        end = instance.data.get("endFrameReview")
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
        capture_preset = instance.context.data['presets']['maya']['capture']

        try:
            preset = lib.load_capture_preset(data=capture_preset)
        except:
            preset = {}
        self.log.info('using viewport preset: {}'.format(preset))

        preset['camera'] = camera
        preset['format'] = "image"
        # preset['compression'] = "qt"
        preset['quality'] = 95
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
            filename = preset.get("filename", "%TEMP%")

            # Force viewer to False in call to capture because we have our own
            # viewer opening call to allow a signal to trigger between playblast
            # and viewer
            preset['viewer'] = False

            # Remove panel key since it's internal value to capture_gui
            preset.pop("panel", None)

            path = capture.capture(**preset)
            playblast = self._fix_playblast_output_path(path)

        self.log.info("file list  {}".format(playblast))

        collected_frames = os.listdir(stagingdir)
        collections, remainder = clique.assemble(collected_frames)
        input_path = os.path.join(
            stagingdir, collections[0].format('{head}{padding}{tail}'))
        self.log.info("input {}".format(input_path))

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'mov',
            'ext': 'mov',
            'files': collected_frames,
            "stagingDir": stagingdir,
            "frameStart": start,
            "frameEnd": end,
            'fps': fps,
            'preview': True,
            'tags': ['review', 'delete']
        }
        instance.data["representations"].append(representation)

    def _fix_playblast_output_path(self, filepath):
        """Workaround a bug in maya.cmds.playblast to return correct filepath.

        When the `viewer` argument is set to False and maya.cmds.playblast
        does not automatically open the playblasted file the returned
        filepath does not have the file's extension added correctly.

        To workaround this we just glob.glob() for any file extensions and
         assume the latest modified file is the correct file and return it.

        """
        # Catch cancelled playblast
        if filepath is None:
            self.log.warning("Playblast did not result in output path. "
                             "Playblast is probably interrupted.")
            return None

        # Fix: playblast not returning correct filename (with extension)
        # Lets assume the most recently modified file is the correct one.
        if not os.path.exists(filepath):
            directory = os.path.dirname(filepath)
            filename = os.path.basename(filepath)
            # check if the filepath is has frame based filename
            # example : capture.####.png
            parts = filename.split(".")
            if len(parts) == 3:
                query = os.path.join(directory, "{}.*.{}".format(parts[0],
                                                                 parts[-1]))
                files = glob.glob(query)
            else:
                files = glob.glob("{}.*".format(filepath))

            if not files:
                raise RuntimeError("Couldn't find playblast from: "
                                   "{0}".format(filepath))
            filepath = max(files, key=os.path.getmtime)

        return filepath



@contextlib.contextmanager
def maintained_time():
    ct = cmds.currentTime(query=True)
    try:
        yield
    finally:
        cmds.currentTime(ct, edit=True)
