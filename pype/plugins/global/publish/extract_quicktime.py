import os
import pyblish.api
import subprocess
from pype.vendor import clique


class ExtractQuicktimeEXR(pyblish.api.InstancePlugin):
    """Resolve any dependency issies

    This plug-in resolves any paths which, if not updated might break
    the published file.

    The order of families is important, when working with lookdev you want to
    first publish the texture, update the texture paths in the nodes and then
    publish the shading network. Same goes for file dependent assets.
    """

    label = "Extract Quicktime EXR"
    order = pyblish.api.ExtractorOrder
    families = ["imagesequence", "render", "write", "source"]
    host = ["shell"]

    def process(self, instance):
        fps = instance.data.get("fps")
        start = instance.data.get("startFrame")
        stagingdir = os.path.normpath(instance.data.get("stagingDir"))

        collected_frames = os.listdir(stagingdir)
        collections, remainder = clique.assemble(collected_frames)

        full_input_path = os.path.join(
            stagingdir, collections[0].format('{head}{padding}{tail}')
        )
        self.log.info("input {}".format(full_input_path))

        filename = collections[0].format('{head}')
        if not filename.endswith('.'):
            filename += "."
        movFile = filename + "mov"
        full_output_path = os.path.join(stagingdir, movFile)

        self.log.info("output {}".format(full_output_path))

        input_args = [
            "-y -gamma 2.2",
            "-i {}".format(full_input_path),
            "-framerate {}".format(fps),
            "-start_number {}".format(start)
        ]
        output_args = [
            "-c:v libx264",
            "-vf colormatrix=bt601:bt709",
            full_output_path
        ]

        mov_args = [
            "ffmpeg",
            " ".join(input_args),
            " ".join(output_args)
        ]
        subprocess_mov = " ".join(mov_args)
        subprocess.Popen(subprocess_mov)

        if "files" not in instance.data:
            instance.data["files"] = list()
        instance.data["files"].append(movFile)
