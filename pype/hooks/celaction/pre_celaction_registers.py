import os
import shutil
import winreg
from pype.lib import PreLaunchHook
from pype.hosts import celaction


class CelactionPrelaunchHook(PreLaunchHook):
    """
    This hook will check if current workfile path has Unreal
    project inside. IF not, it initialize it and finally it pass
    path to the project by environment variable to Unreal launcher
    shell script.
    """
    workfile_ext = "scn"
    app_groups = ["celaction"]
    platforms = ["windows"]

    def execute(self):
        # Add workfile path to launch arguments
        workfile_path = self.workfile_path()
        if workfile_path:
            self.launch_context.launch_args.append(
                "\"{}\"".format(workfile_path)
            )

        project_name = self.data["project_name"]
        asset_name = self.data["asset_name"]
        task_name = self.data["task_name"]

        # get publish version of celaction
        app = "celaction_publish"

        # setting output parameters
        path = r"Software\CelAction\CelAction2D\User Settings"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
        hKey = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\CelAction\\CelAction2D\\User Settings", 0,
            winreg.KEY_ALL_ACCESS)

        # TODO: change to root path and pyblish standalone to premiere way
        pype_root_path = os.getenv("PYPE_SETUP_PATH")
        path = os.path.join(pype_root_path, "pype.bat")

        winreg.SetValueEx(hKey, "SubmitAppTitle", 0, winreg.REG_SZ, path)

        parameters = [
            "launch",
            f"--app {app}",
            f"--project {project_name}",
            f"--asset {asset_name}",
            f"--task {task_name}",
            "--currentFile \\\"\"*SCENE*\"\\\"",
            "--chunk 10",
            "--frameStart *START*",
            "--frameEnd *END*",
            "--resolutionWidth *X*",
            "--resolutionHeight *Y*",
            # "--programDir \"'*PROGPATH*'\""
        ]
        winreg.SetValueEx(hKey, "SubmitParametersTitle", 0, winreg.REG_SZ,
                          " ".join(parameters))

        # setting resolution parameters
        path = r"Software\CelAction\CelAction2D\User Settings\Dialogs"
        path += r"\SubmitOutput"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
        hKey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                              winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(hKey, "SaveScene", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(hKey, "CustomX", 0, winreg.REG_DWORD, 1920)
        winreg.SetValueEx(hKey, "CustomY", 0, winreg.REG_DWORD, 1080)

        # making sure message dialogs don't appear when overwriting
        path = r"Software\CelAction\CelAction2D\User Settings\Messages"
        path += r"\OverwriteScene"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
        hKey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                              winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(hKey, "Result", 0, winreg.REG_DWORD, 6)
        winreg.SetValueEx(hKey, "Valid", 0, winreg.REG_DWORD, 1)

        path = r"Software\CelAction\CelAction2D\User Settings\Messages"
        path += r"\SceneSaved"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
        hKey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                              winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(hKey, "Result", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(hKey, "Valid", 0, winreg.REG_DWORD, 1)

    def workfile_path(self):
        workfile_path = self.data["last_workfile_path"]

        # copy workfile from template if doesnt exist any on path
        if not os.path.exists(workfile_path):
            # TODO add ability to set different template workfile path via
            # settings
            pype_celaction_dir = os.path.dirname(
                os.path.abspath(celaction.__file__)
            )
            template_path = os.path.join(
                pype_celaction_dir,
                "celaction_template_scene.scn"
            )

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
