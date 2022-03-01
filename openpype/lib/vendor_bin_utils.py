import os
import logging
import json
import platform
import subprocess

log = logging.getLogger("Vendor utils")


def find_executable(executable):
    """Find full path to executable.

    Also tries additional extensions if passed executable does not contain one.

    Paths where it is looked for executable is defined by 'PATH' environment
    variable, 'os.confstr("CS_PATH")' or 'os.defpath'.

    Args:
        executable(str): Name of executable with or without extension. Can be
            path to file.

    Returns:
        str: Full path to executable with extension (is file).
        None: When the executable was not found.
    """
    if os.path.isfile(executable):
        return executable

    low_platform = platform.system().lower()
    _, ext = os.path.splitext(executable)
    variants = [executable]
    if not ext:
        if low_platform == "windows":
            exts = [".exe", ".ps1", ".bat"]
            for ext in os.getenv("PATHEXT", "").split(os.pathsep):
                ext = ext.lower()
                if ext and ext not in exts:
                    exts.append(ext)
        else:
            exts = [".sh"]

        for ext in exts:
            variant = executable + ext
            if os.path.isfile(variant):
                return variant
            variants.append(variant)

    path_str = os.environ.get("PATH", None)
    if path_str is None:
        if hasattr(os, "confstr"):
            path_str = os.confstr("CS_PATH")
        elif hasattr(os, "defpath"):
            path_str = os.defpath

    if not path_str:
        return None

    paths = path_str.split(os.pathsep)
    for path in paths:
        for variant in variants:
            filepath = os.path.abspath(os.path.join(path, variant))
            if os.path.isfile(filepath):
                return filepath
    return None


def get_vendor_bin_path(bin_app):
    """Path to OpenPype vendorized binaries.

    Vendorized executables are expected in specific hierarchy inside build or
    in code source.

    "{OPENPYPE_ROOT}/vendor/bin/{name of vendorized app}/{platform}"

    Args:
        bin_app (str): Name of vendorized application.

    Returns:
        str: Path to vendorized binaries folder.
    """
    return os.path.join(
        os.environ["OPENPYPE_ROOT"],
        "vendor",
        "bin",
        bin_app,
        platform.system().lower()
    )


def get_oiio_tools_path(tool="oiiotool"):
    """Path to vendorized OpenImageIO tool executables.

    On Window it adds .exe extension if missing from tool argument.

    Args:
        tool (string): Tool name (oiiotool, maketx, ...).
            Default is "oiiotool".
    """
    oiio_dir = get_vendor_bin_path("oiio")
    return find_executable(os.path.join(oiio_dir, tool))


def get_ffmpeg_tool_path(tool="ffmpeg"):
    """Path to vendorized FFmpeg executable.

    Args:
        tool (string): Tool name (ffmpeg, ffprobe, ...).
            Default is "ffmpeg".

    Returns:
        str: Full path to ffmpeg executable.
    """
    ffmpeg_dir = get_vendor_bin_path("ffmpeg")
    if platform.system().lower() == "windows":
        ffmpeg_dir = os.path.join(ffmpeg_dir, "bin")
    return find_executable(os.path.join(ffmpeg_dir, tool))


def ffprobe_streams(path_to_file, logger=None):
    """Load streams from entered filepath via ffprobe.

    Args:
        path_to_file (str): absolute path
        logger (logging.getLogger): injected logger, if empty new is created

    """
    if not logger:
        logger = log
    logger.info(
        "Getting information about input \"{}\".".format(path_to_file)
    )
    args = [
        get_ffmpeg_tool_path("ffprobe"),
        "-hide_banner",
        "-loglevel", "fatal",
        "-show_error",
        "-show_format",
        "-show_streams",
        "-show_programs",
        "-show_chapters",
        "-show_private_data",
        "-print_format", "json",
        path_to_file
    ]

    logger.debug("FFprobe command: {}".format(
        subprocess.list2cmdline(args)
    ))
    popen = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    popen_stdout, popen_stderr = popen.communicate()
    if popen_stdout:
        logger.debug("FFprobe stdout:\n{}".format(
            popen_stdout.decode("utf-8")
        ))

    if popen_stderr:
        logger.warning("FFprobe stderr:\n{}".format(
            popen_stderr.decode("utf-8")
        ))

    return json.loads(popen_stdout)["streams"]


def is_oiio_supported():
    """Checks if oiiotool is configured for this platform.

    Returns:
        bool: OIIO tool executable is available.
    """
    loaded_path = oiio_path = get_oiio_tools_path()
    if oiio_path:
        oiio_path = find_executable(oiio_path)

    if not oiio_path:
        log.debug("OIIOTool is not configured or not present at {}".format(
            loaded_path
        ))
        return False
    return True
