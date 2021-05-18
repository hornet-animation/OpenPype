import os


def add_implementation_envs(env):
    """Modify environments to contain all required for implementation."""
    # Set AVALON_UNREAL_PLUGIN required for Unreal implementation
    unreal_plugin_path = os.path.join(
        os.environ["OPENPYPE_REPOS_ROOT"], "repos", "avalon-unreal-integration"
    )
    env["AVALON_UNREAL_PLUGIN"] = unreal_plugin_path

    # Set default environments if are not set via settings
    defaults = {
        "OPENPYPE_LOG_NO_COLORS": "True"
    }
    for key, value in defaults.items():
        if not env.get(key):
            env[key] = value
