import os

import pype.api

from pype.vendor import ffmpeg


class ExtractQuicktime(pype.api.Extractor):
    """Extract Quicktime with optimized codec for reviewing."""

    label = "Review"
    hosts = ["nukestudio"]
    families = ["review"]
    optional = True

    def process(self, instance):
        staging_dir = self.staging_dir(instance)
        filename = "{0}".format(instance.name) + ".mov"
        output_path = os.path.join(staging_dir, filename)
        input_path = instance.data["sourcePath"]

        self.log.info("Outputting movie to %s" % output_path)

        # Has to be yuv420p for compatibility with older players and smooth
        # playback. This does come with a sacrifice of more visible banding
        # issues.
        output_options = {
            "pix_fmt": "yuv420p",
            "crf": "18",
            "timecode": "00:00:00:01",
            "vf": "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        }

        try:
            (
                ffmpeg
                .input(input_path)
                .output(output_path, **output_options)
                .run(overwrite_output=True,
                     capture_stdout=True,
                     capture_stderr=True)
            )
        except ffmpeg.Error as e:
            ffmpeg_error = "ffmpeg error: {}".format(e.stderr)
            self.log.error(ffmpeg_error)
            raise RuntimeError(ffmpeg_error)

        # Adding movie representation.
        start_frame = int(
            instance.data["sourceIn"] - (
                instance.data["handleStart"] + instance.data["handles"]
            )
        )
        end_frame = int(
            instance.data["sourceOut"] + (
                instance.data["handleEnd"] + instance.data["handles"]
            )
        )
        representation = {
            "files": os.path.basename(output_path),
            "staging_dir": staging_dir,
            "startFrame": 0,
            "endFrame": end_frame - start_frame,
            "step": 1,
            "frameRate": (
                instance.context.data["activeSequence"].framerate().toFloat()
            ),
            "preview": True,
            "thumbnail": False,
            "name": "preview",
            "ext": "mov",
        }
        instance.data["representations"] = [representation]
        self.log.debug("Adding representation: {}".format(representation))

        # Adding thumbnail representation.
        representation = {
            "files": os.path.basename(
                instance.data["sourcePath"].replace(".mov", ".png")
            ),
            "stagingDir": os.path.dirname(instance.data["sourcePath"]),
            "name": "thumbnail",
            "thumbnail": True,
            "ext": "png"
        }
        instance.data["representations"].append(representation)
        self.log.debug("Adding representation: {}".format(representation))
