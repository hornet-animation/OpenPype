# -*- coding: utf-8 -*-
"""Pype module API."""

from .terminal import Terminal
from .execute import execute
from .log import PypeLogger, timeit
from .mongo import (
    decompose_url,
    compose_url,
    get_default_components,
    PypeMongoConnection
)
from .anatomy import (
    merge_dict,
    Anatomy
)

from .config import get_datetime_data

from .env_tools import (
    env_value_to_bool,
    get_paths_from_environ
)

from .python_module_tools import (
    modules_from_path,
    recursive_bases_from_class,
    classes_from_module
)

from .avalon_context import (
    is_latest,
    any_outdated,
    get_asset,
    get_hierarchy,
    get_linked_assets,
    get_latest_version,

    get_workdir_data,
    get_workdir,
    get_workdir_with_workdir_data,

    create_workfile_doc,
    save_workfile_data_to_doc,
    get_workfile_doc,

    BuildWorkfile
)

from .applications import (
    ApplicationLaunchFailed,
    ApplictionExecutableNotFound,
    ApplicationNotFound,
    ApplicationManager,
    PreLaunchHook,
    PostLaunchHook,
    _subprocess
)

from .plugin_tools import (
    filter_pyblish_plugins,
    source_hash,
    get_unique_layer_name,
    get_background_layers,
    oiio_supported,
    decompress,
    get_decompress_dir,
    should_decompress
)

from .user_settings import (
    IniSettingRegistry,
    JSONSettingRegistry,
    PypeSettingsRegistry
)

from .path_tools import (
    version_up,
    get_version_from_path,
    get_last_version_from_path
)

from .ffmpeg_utils import (
    get_ffmpeg_tool_path,
    ffprobe_streams
)

from .editorial import (
    is_overlapping_otio_ranges,
    otio_range_to_frame_range,
    otio_range_with_handles,
    convert_to_padded_path,
    trim_media_range,
    range_from_frames,
    frames_to_secons,
    make_sequence_collection
)

terminal = Terminal

__all__ = [
    "env_value_to_bool",
    "get_paths_from_environ",

    "modules_from_path",
    "recursive_bases_from_class",
    "classes_from_module",

    "is_latest",
    "any_outdated",
    "get_asset",
    "get_hierarchy",
    "get_linked_assets",
    "get_latest_version",

    "get_workdir_data",
    "get_workdir",
    "get_workdir_with_workdir_data",

    "create_workfile_doc",
    "save_workfile_data_to_doc",
    "get_workfile_doc",

    "BuildWorkfile",

    "ApplicationLaunchFailed",
    "ApplictionExecutableNotFound",
    "ApplicationNotFound",
    "ApplicationManager",
    "PreLaunchHook",
    "PostLaunchHook",

    "filter_pyblish_plugins",
    "source_hash",
    "get_unique_layer_name",
    "get_background_layers",
    "oiio_supported",
    "decompress",
    "get_decompress_dir",
    "should_decompress",

    "version_up",
    "get_version_from_path",
    "get_last_version_from_path",

    "ffprobe_streams",
    "get_ffmpeg_tool_path",

    "_subprocess",

    "terminal",

    "merge_dict",
    "Anatomy",

    "get_datetime_data",

    "execute",
    "PypeLogger",
    "decompose_url",
    "compose_url",
    "get_default_components",
    "PypeMongoConnection",

    "IniSettingRegistry",
    "JSONSettingRegistry",
    "PypeSettingsRegistry",
    "timeit",

    "is_overlapping_otio_ranges",
    "otio_range_with_handles",
    "convert_to_padded_path",
    "otio_range_to_frame_range",
    "trim_media_range",
    "range_from_frames",
    "frames_to_secons",
    "make_sequence_collection"
]
