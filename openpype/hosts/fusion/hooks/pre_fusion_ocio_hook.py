import os
import platform

from openpype.lib import PreLaunchHook, ApplicationLaunchFailed


class FusionPreLaunchOCIO(PreLaunchHook):
    """Set OCIO environment variable for Fusion"""
    app_groups = ["fusion"]

    def execute(self):
        """Hook entry method."""

        # get image io
        project_anatomy = self.data["anatomy"]

        # make sure anatomy settings are having flame key
        imageio_fusion = project_anatomy["imageio"].get("fusion")
        if not imageio_fusion:
            raise ApplicationLaunchFailed((
                "Anatomy project settings are missing `fusion` key. "
                "Please make sure you remove project overrides on "
                "Anatomy ImageIO")
            )

        ocio = imageio_fusion.get("ocio")
        enabled = ocio.get("enabled", False)
        if not enabled:
            return

        platform_key = platform.system().lower()
        ocio_path = ocio["configFilePath"][platform_key]
        if not ocio_path:
            raise ApplicationLaunchFailed(
                "Fusion OCIO is enabled in project settings but no OCIO config"
                f"path is set for your current platform: {platform_key}"
            )

        self.log.info(f"Setting OCIO config path: {ocio_path}")
        self.launch_context.env["OCIO"] = os.pathsep.join(ocio_path)
