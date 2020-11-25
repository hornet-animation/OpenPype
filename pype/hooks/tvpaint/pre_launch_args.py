import os
import shutil

from pype.hosts import tvpaint
from pype.lib import PreLaunchHook

import avalon


class TvpaintPrelaunchHook(PreLaunchHook):
    """Launch arguments preparation.

    Hook add python executable and script path to tvpaint implementation before
    tvpaint executable and add last workfile path to launch arguments.

    Existence of last workfile is checked. If workfile does not exists tries
    to copy templated workfile from predefined path.
    """
    hosts = ["tvpaint"]

    def execute(self):
        # Pop tvpaint executable
        tvpaint_executable = self.launch_context.launch_args.pop(0)

        # Pop rest of launch arguments - There should not be other arguments!
        remainders = []
        while self.launch_context.launch_args:
            remainders.append(self.launch_context.launch_args.pop(0))

        new_launch_args = [
            self.main_executable(),
            self.launch_script_path(),
            tvpaint_executable
        ]

        # Add workfile to launch arguments
        workfile_path = self.workfile_path()
        if workfile_path:
            new_launch_args.append(
                "\"{}\"".format(workfile_path)
            )

        # How to create new command line
        # if platform.system().lower() == "windows":
        #     new_launch_args = [
        #         "cmd.exe",
        #         "/c",
        #         "Call cmd.exe /k",
        #         *new_launch_args
        #     ]

        # Append as whole list as these areguments should not be separated
        self.launch_context.launch_args.append(new_launch_args)

        if remainders:
            self.log.warning((
                "There are unexpected launch arguments in TVPaint launch. {}"
            ).format(str(remainders)))
            self.launch_context.launch_args.extend(remainders)

    def main_executable(self):
        """Should lead to python executable."""
        # TODO change in Pype 3
        return os.path.normpath(os.environ["PYPE_PYTHON_EXE"])

    def launch_script_path(self):
        avalon_dir = os.path.dirname(os.path.abspath(avalon.__file__))
        script_path = os.path.join(
            avalon_dir,
            "tvpaint",
            "launch_script.py"
        )
        return script_path

    def workfile_path(self):
        workfile_path = self.data["last_workfile_path"]

        # copy workfile from template if doesnt exist any on path
        if not os.path.exists(workfile_path):
            # TODO add ability to set different template workfile path via
            # settings
            pype_dir = os.path.dirname(os.path.abspath(tvpaint.__file__))
            template_path = os.path.join(pype_dir, "template.tvpp")

            if not os.path.exists(template_path):
                self.log.warning(
                    "Couldn't find workfile template file in {}".format(
                        template_path
                    )
                )
                return

            self.log.info(
                f"Creating workfile from template: \"{template_path}\""
            )

            # Copy template workfile to new destinantion
            shutil.copy2(
                os.path.normpath(template_path),
                os.path.normpath(workfile_path)
            )

        self.log.info(f"Workfile to open: \"{workfile_path}\"")

        return workfile_path
