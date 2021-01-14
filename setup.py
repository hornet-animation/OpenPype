# -*- coding: utf-8 -*-
"""Setup info for building Pype 3.0."""
import os
import sys
from pathlib import Path

from cx_Freeze import setup, Executable
from sphinx.setup_command import BuildDoc

version = {}

pype_root = Path(os.path.dirname(__file__))

with open(pype_root / "pype" / "version.py") as fp:
    exec(fp.read(), version)
__version__ = version["__version__"]

base = None
if sys.platform == "win32":
    base = "Win32GUI"

# -----------------------------------------------------------------------
# build_exe
# Build options for cx_Freeze. Manually add/exclude packages and binaries

install_requires = [
    "appdirs",
    "cx_Freeze",
    "keyring",
    "clique",
    "jsonschema",
    "opentimelineio",
    "pathlib2",
    "pkg_resources",
    "PIL",
    "pymongo",
    "pynput",
    "jinxed",
    "blessed",
    "Qt",
    "speedcopy",
    "googleapiclient",
    "httplib2"
]

includes = []
excludes = []
bin_includes = []
include_files = [
    "igniter",
    "pype",
    "repos",
    "schema",
    "setup",
    "vendor",
    "LICENSE",
    "README.md",
    "pype/version.py"
]

if sys.platform == "win32":
    install_requires.append("win32ctypes")

build_options = dict(
    packages=install_requires,
    includes=includes,
    excludes=excludes,
    bin_includes=bin_includes,
    include_files=include_files
)

icon_path = pype_root / "igniter" / "pype.ico"

executables = [
    Executable("start.py", base=None,
               target_name="pype_console", icon=icon_path.as_posix()),
    Executable("start.py", base=base,
               target_name="pype", icon=icon_path.as_posix())
]

setup(
    name="pype",
    version=__version__,
    description="Ultimate pipeline",
    cmdclass={"build_sphinx": BuildDoc},
    options={
        "build_exe": build_options,
        "build_sphinx": {
            "project": "Pype",
            "version": __version__,
            "release": __version__,
            "source_dir": (pype_root / "docs" / "source").as_posix(),
            "build_dir": (pype_root / "docs" / "build").as_posix()
        }
    },
    executables=executables
)
