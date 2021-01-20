# -*- coding: utf-8 -*-
"""Main entry point for Pype command.

Bootstrapping process of Pype is as follows:

`PYPE_PATH` is checked for existence - either one from environment or
from user settings. Precedence takes the one set by environment.

On this path we try to find pype in directories version string in their names.
For example: `pype-v3.0.1-foo` is valid name, or even `foo_3.0.2` - as long
as version can be determined from its name _AND_ file `pype/pype/version.py`
can be found inside, it is considered Pype installation.

If no Pype repositories are found in `PYPE_PATH` (user data dir)
then **Igniter** (Pype setup tool) will launch its GUI.

It can be used to specify `PYPE_PATH` or if it is _not_ specified, current
*"live"* repositories will be used to create zip file and copy it to
appdata dir in user home and extract it there. Version will be determined by
version specified in Pype module.

If Pype repository directories are found in default install location
(user data dir) or in `PYPE_PATH`, it will get list of those dirs there and
use latest one or the one specified with optional `--use-version` command
line argument. If the one specified doesn't exist then latest available
version will be used. All repositories in that dir will be added
to `sys.path` and `PYTHONPATH`.

If Pype is live (not frozen) then current version of Pype module will be
used. All directories under `repos` will be added to `sys.path` and
`PYTHONPATH`.

Pype depends on connection to `MongoDB`_. You can specify MongoDB connection
string via `PYPE_MONGO` set in environment or it can be set in user
settings or via **Igniter** GUI.

So, bootstrapping Pype looks like this::

.. code-block:: bash

+-------------------------------------------------------+
| Determine MongoDB connection:                         |
| Use `PYPE_MONGO`, system keyring `pypeMongo`          |
+--------------------------|----------------------------+
                   .--- Found? --.
                 YES             NO
                  |              |
                  |       +------v--------------+
                  |       | Fire up Igniter GUI |<---------+
                  |       | and ask User        |          |
                  |       +---------------------+          |
                  |                                        |
                  |                                        |
+-----------------v------------------------------------+   |
| Get location of Pype:                                |   |
|   1) Test for `PYPE_PATH` environment variable       |   |
|   2) Test `pypePath` in registry setting             |   |
|   3) Test user data directory                        |   |
| ...................................................  |   |
| If running from frozen code:                         |   |
|   - Use latest one found in user data dir            |   |
| If running from live code:                           |   |
|   - Use live code and install it to user data dir    |   |
| * can be overridden with `--use-version` argument    |   |
+-------------------------|----------------------------+   |
               .-- Is Pype found? --.                      |
             YES                    NO                     |
              |                     |                      |
              |      +--------------v------------------+   |
              |      | Look in `PYPE_PATH`, find       |   |
              |      | latest version and install it   |   |
              |      | to user data dir.               |   |
              |      +--------------|------------------+   |
              |           .-- Is Pype found? --.           |
              |         YES                    NO ---------+
              |          |
              |<---------+
              |
+-------------v------------+
|         Run Pype         |
+--------------------------+


Todo:
    Move or remove bootstrapping environments out of the code.

Attributes:
    silent_commands (list): list of commands for which we won't print Pype
        logo and info header.

.. _MongoDB:
   https://www.mongodb.com/

"""
import os
import re
import sys
import traceback
import subprocess
import site
from pathlib import Path

# add dependencies folder to sys.pat for frozen code
if getattr(sys, 'frozen', False):
    frozen_libs = os.path.normpath(
        os.path.join(os.path.dirname(sys.executable), "dependencies"))
    sys.path.append(frozen_libs)
    # add stuff from `<frozen>/dependencies` to PYTHONPATH.
    pythonpath = os.getenv("PYTHONPATH", "")
    paths = pythonpath.split(os.pathsep)
    paths.append(frozen_libs)
    os.environ["PYTHONPATH"] = os.pathsep.join(paths)

from igniter import BootstrapRepos  # noqa: E402
from igniter.tools import load_environments  # noqa: E402
from igniter.bootstrap_repos import PypeVersion  # noqa: E402

bootstrap = BootstrapRepos()
silent_commands = ["run", "igniter"]


def set_environments() -> None:
    """Set loaded environments.

    .. todo:
        better handling of environments

    """
    try:
        import acre
    except ImportError:
        if getattr(sys, 'frozen', False):
            sys.path.append(os.path.join(
                os.path.dirname(sys.executable),
                "dependencies"
            ))
            import acre
    try:
        env = load_environments(["global"])
    except OSError as e:
        print(f"!!! {e}")
        sys.exit(1)

    env = acre.merge(env, dict(os.environ))
    os.environ.clear()
    os.environ.update(env)


def run(arguments: list, env: dict = None) -> int:
    """Use correct executable to run stuff.

    This passing arguments to correct Pype executable. If Pype is run from
    live sources, executable will be `python` in virtual environment.
    If running from frozen code, executable will be `pype`. Its equivalent in
    live code is `python start.py`.

    Args:
        arguments (list): Argument list to pass Pype.
        env (dict, optional): Dictionary containing environment.

    Returns:
        int: Process return code.

    """
    if getattr(sys, 'frozen', False):
        interpreter = [sys.executable]
    else:
        interpreter = [sys.executable, __file__]

    interpreter.extend(arguments)

    p = subprocess.Popen(interpreter, env=env)
    p.wait()
    print(f">>> done [{p.returncode}]")
    return p.returncode


def set_modules_environments():
    """Set global environments for pype modules.

    This requires to have pype in `sys.path`.
    """

    from pype.modules import ModulesManager
    import acre

    modules_manager = ModulesManager()

    module_envs = modules_manager.collect_global_environments()
    publish_plugin_dirs = modules_manager.collect_plugin_paths()["publish"]

    # Set pyblish plugins paths if any module want to register them
    if publish_plugin_dirs:
        publish_paths_str = os.environ.get("PYBLISHPLUGINPATH") or ""
        publish_paths = publish_paths_str.split(os.pathsep)
        _publish_paths = {
            os.path.normpath(path) for path in publish_paths if path
        }
        for path in publish_plugin_dirs:
            _publish_paths.add(os.path.normpath(path))
        module_envs["PYBLISHPLUGINPATH"] = os.pathsep.join(_publish_paths)

    # Merge environments with current environments and update values
    if module_envs:
        parsed_envs = acre.parse(module_envs)
        env = acre.merge(parsed_envs, dict(os.environ))
        os.environ.clear()
        os.environ.update(env)


def _process_arguments() -> tuple:
    """Process command line arguments.

    Returns:
        tuple: Return tuple with specific version to use (if any) and flag
            to prioritize staging (if set)
    """
    # check for `--use-version=3.0.0` argument and `--use-staging`
    use_version = None
    use_staging = False
    for arg in sys.argv:
        if arg == "--use-version":
            print("!!! Please use option --use-version like:")
            print("    --use-version=3.0.0")
            sys.exit(1)

        m = re.search(r"--use-version=(?P<version>\d+\.\d+\.\d*.+?)", arg)
        if m and m.group('version'):
            use_version = m.group('version')
            sys.argv.remove(arg)
            break
    if "--use-staging" in sys.argv:
        use_staging = True
        sys.argv.remove("--use-staging")

    # handle igniter
    # this is helper to run igniter before anything else
    if "igniter" in sys.argv:
        import igniter
        igniter.run()

    return use_version, use_staging


def _determine_mongodb() -> str:
    """Determine mongodb connection string.

    First use ``PYPE_MONGO`` environment variable, then system keyring.
    Then try to run **Igniter UI** to let user specify it.

    Returns:
        str: mongodb connection URL

    Raises:
        RuntimeError: if mongodb connection url cannot by determined.

    """

    pype_mongo = os.getenv("PYPE_MONGO", None)
    if not pype_mongo:
        # try system keyring
        try:
            pype_mongo = bootstrap.registry.get_secure_item("pypeMongo")
        except ValueError:
            print("*** No DB connection string specified.")
            print("--- launching setup UI ...")
            run(["igniter"])
            try:
                pype_mongo = bootstrap.registry.get_secure_item("pypeMongo")
            except ValueError:
                raise RuntimeError("missing mongodb url")

    return pype_mongo


def _initialize_environment(pype_version: PypeVersion) -> None:
    version_path = pype_version.path
    os.environ["PYPE_VERSION"] = pype_version.version
    # inject version to Python environment (sys.path, ...)
    print(">>> Injecting Pype version to running environment  ...")
    bootstrap.add_paths_from_directory(version_path)

    # add venv 'site-packages' to PYTHONPATH
    python_path = os.getenv("PYTHONPATH", "")
    split_paths = python_path.split(os.pathsep)
    # add pype tools
    split_paths.append(os.path.join(os.environ["PYPE_ROOT"], "pype", "tools"))
    # add common pype vendor
    # (common for multiple Python interpreter versions)
    split_paths.append(os.path.join(
        os.environ["PYPE_ROOT"], "pype", "vendor", "python", "common"))
    os.environ["PYTHONPATH"] = os.pathsep.join(split_paths)

    # set PYPE_ROOT to point to currently used Pype version.
    os.environ["PYPE_ROOT"] = os.path.normpath(version_path.as_posix())


def _find_frozen_pype(use_version: str = None,
                      use_staging: bool = False) -> Path:
    """Find Pype to run from frozen code.

    This will process and modify environment variables:
    ``PYTHONPATH``, ``PYPE_VERSION``, ``PYPE_ROOT``

    Args:
        use_version (str, optional): Try to use specified version.
        use_staging (bool, optional): Prefer *staging* flavor over production.

    Returns:
        Path: Path to version to be used.

    Raises:
        RuntimeError: If no Pype version are found or no staging version
            (if requested).

    """
    pype_version = None
    pype_versions = bootstrap.find_pype(include_zips=True,
                                        staging=use_staging)
    try:
        # use latest one found (last in the list is latest)
        pype_version = pype_versions[-1]
    except IndexError:
        # no pype version found, run Igniter and ask for them.
        print('*** No Pype versions found.')
        print("--- launching setup UI ...")
        run(["igniter"])
        pype_versions = bootstrap.find_pype()

    if not pype_versions:
        # no Pype versions found anyway, lets use then the one
        # shipped with frozen Pype
        version_path = _bootstrap_from_code(use_version)
        pype_version = PypeVersion(
            version=BootstrapRepos.get_version(version_path),
            path=version_path)
        _initialize_environment(pype_version)
        return version_path

    # get path of version specified in `--use-version`
    version_path = BootstrapRepos.get_version_path_from_list(
        use_version, pype_versions)

    if not version_path:
        if use_version is not None:
            if not pype_version:
                ...
            else:
                print(("!!! Specified version was not found, using "
                       "latest available"))
        # specified version was not found so use latest detected.
        version_path = pype_version.path
        print(f">>> Using version [ {pype_version} ]")
        print(f"    From {version_path}")

    # test if latest detected is installed (in user data dir)
    is_inside = False
    try:
        is_inside = pype_version.path.resolve().relative_to(
            bootstrap.data_dir)
    except ValueError:
        # if relative path cannot be calculated, Pype version is not
        # inside user data dir
        pass

    if not is_inside:
        # install latest version to user data dir
        version_path = bootstrap.install_version(
            pype_version, force=True)

    if pype_version.path.is_file():
        print(">>> Extracting zip file ...")
        version_path = bootstrap.extract_pype(pype_version)
        pype_version.path = version_path

    _initialize_environment(pype_version)
    return version_path


def _bootstrap_from_code(use_version):
    """Bootstrap live code (or the one coming with frozen Pype.

    Args:
        use_version: (str): specific version to use.

    Returns:
        Path: path to sourced version.

    """
    # run through repos and add them to `sys.path` and `PYTHONPATH`
    # set root
    if getattr(sys, 'frozen', False):
        pype_root = os.path.normpath(
            os.path.dirname(sys.executable))
        local_version = bootstrap.get_version(Path(pype_root))
    else:
        pype_root = os.path.normpath(
            os.path.dirname(os.path.realpath(__file__)))
        # get current version of Pype
        local_version = bootstrap.get_local_live_version()

    os.environ["PYPE_VERSION"] = local_version
    if use_version and use_version != local_version:
        pype_versions = bootstrap.find_pype(include_zips=True)
        version_path = BootstrapRepos.get_version_path_from_list(
            use_version, pype_versions)
        if version_path:
            # use specified
            bootstrap.add_paths_from_directory(version_path)
            os.environ["PYPE_VERSION"] = use_version
    else:
        version_path = pype_root
    os.environ["PYPE_ROOT"] = pype_root
    repos = os.listdir(os.path.join(pype_root, "repos"))
    repos = [os.path.join(pype_root, "repos", repo) for repo in repos]
    # add self to python paths
    repos.insert(0, pype_root)
    for repo in repos:
        sys.path.append(repo)

    # add venv 'site-packages' to PYTHONPATH
    python_path = os.getenv("PYTHONPATH", "")
    split_paths = python_path.split(os.pathsep)
    split_paths += repos
    # add pype tools
    split_paths.append(os.path.join(os.environ["PYPE_ROOT"], "pype", "tools"))
    # last one should be venv site-packages
    # this is slightly convoluted as we can get here from frozen code too
    # in case when we are running without any version installed.
    if not getattr(sys, 'frozen', False):
        split_paths.append(site.getsitepackages()[-1])
    # add common pype vendor
    # (common for multiple Python interpreter versions)
    split_paths.append(os.path.join(
        os.environ["PYPE_ROOT"], "pype", "vendor", "python", "common"))
    os.environ["PYTHONPATH"] = os.pathsep.join(split_paths)

    return Path(version_path)


def boot():
    """Bootstrap Pype."""
    version_path = None

    # ------------------------------------------------------------------------
    # Play animation
    # ------------------------------------------------------------------------

    from igniter.terminal_splash import play_animation

    # don't play for silenced commands
    if all(item not in sys.argv for item in silent_commands):
        play_animation()

    # ------------------------------------------------------------------------
    # Process arguments
    # ------------------------------------------------------------------------

    use_version, use_staging = _process_arguments()

    # ------------------------------------------------------------------------
    # Determine mongodb connection
    # ------------------------------------------------------------------------

    try:
        pype_mongo = _determine_mongodb()
    except RuntimeError as e:
        # without mongodb url we are done for.
        print(f"!!! {e}")
        sys.exit(1)

    os.environ["PYPE_MONGO"] = pype_mongo

    # ------------------------------------------------------------------------
    # Load environments from database
    # ------------------------------------------------------------------------
    # set PYPE_ROOT to running location until proper version can be
    # determined.
    if getattr(sys, 'frozen', False):
        os.environ["PYPE_ROOT"] = os.path.dirname(sys.executable)
    else:
        os.environ["PYPE_ROOT"] = os.path.dirname(__file__)
    set_environments()

    # ------------------------------------------------------------------------
    # Find Pype versions
    # ------------------------------------------------------------------------

    if getattr(sys, 'frozen', False):
        # find versions of Pype to be used with frozen code
        try:
            version_path = _find_frozen_pype(use_version, use_staging)
        except RuntimeError as e:
            # no version to run
            print(f"!!! {e}")
            sys.exit(1)
    else:
        version_path = _bootstrap_from_code(use_version)

    # set this to point either to `python` from venv in case of live code
    # or to `pype` or `pype_console` in case of frozen code
    os.environ["PYPE_EXECUTABLE"] = sys.executable

    # TODO: DEPRECATE remove when `pype-config` dissolves into Pype for good.
    # PYPE_MODULE_ROOT should be changed to PYPE_REPOS_ROOT
    # This needs to replace environment building in hosts

    # .-=-----------------------=-=. ^ .=-=--------------------------=-.
    os.environ["PYPE_MODULE_ROOT"] = os.environ["PYPE_ROOT"]
    # -=------------------------=-=. v .=-=--------------------------=-.

    if getattr(sys, 'frozen', False):
        os.environ["PYPE_REPOS_ROOT"] = os.environ["PYPE_ROOT"]
    else:
        os.environ["PYPE_REPOS_ROOT"] = os.path.join(
            os.environ["PYPE_ROOT"], "repos")

    # delete Pype module from cache so it is used from specific version
    try:
        del sys.modules["pype"]
        del sys.modules["pype.version"]
    except AttributeError:
        pass
    except KeyError:
        pass

    from pype import cli
    from pype.lib import terminal as t
    from pype.version import __version__
    print(">>> loading environments ...")
    set_modules_environments()

    assert version_path, "Version path not defined."
    info = get_info()
    info.insert(0, f">>> Using Pype from [ {version_path} ]")

    t_width = os.get_terminal_size().columns - 2
    _header = f"*** Pype [{__version__}] "

    info.insert(0, _header + "-" * (t_width - len(_header)))
    for i in info:
        # don't show for running scripts
        if all(item not in sys.argv for item in silent_commands):
            t.echo(i)

    try:
        cli.main(obj={}, prog_name="pype")
    except Exception:
        exc_info = sys.exc_info()
        print("!!! Pype crashed:")
        traceback.print_exception(*exc_info)
        sys.exit(1)


def get_info() -> list:
    """Print additional information to console."""
    from pype.lib.mongo import get_default_components
    from pype.lib.log import PypeLogger

    components = get_default_components()

    inf = []
    if not getattr(sys, 'frozen', False):
        inf.append(("Pype variant", "staging"))
    else:
        inf.append(("Pype variant", "production"))
    inf.append(("Running pype from", os.environ.get('PYPE_ROOT')))
    inf.append(("Using mongodb", components["host"]))

    if os.environ.get("FTRACK_SERVER"):
        inf.append(("Using FTrack at",
                    os.environ.get("FTRACK_SERVER")))

    if os.environ.get('DEADLINE_REST_URL'):
        inf.append(("Using Deadline webservice at",
                    os.environ.get("DEADLINE_REST_URL")))

    if os.environ.get('MUSTER_REST_URL'):
        inf.append(("Using Muster at",
                    os.environ.get("MUSTER_REST_URL")))

    # Reinitialize
    PypeLogger.initialize()

    log_components = PypeLogger.log_mongo_url_components
    if log_components["host"]:
        inf.append(("Logging to MongoDB", log_components["host"]))
        inf.append(("  - port", log_components["port"] or "<N/A>"))
        inf.append(("  - database", PypeLogger.log_database_name))
        inf.append(("  - collection", PypeLogger.log_collection_name))
        inf.append(("  - user", log_components["username"] or "<N/A>"))
        if log_components["auth_db"]:
            inf.append(("  - auth source", log_components["auth_db"]))

    maximum = max(len(i[0]) for i in inf)
    formatted = []
    for info in inf:
        padding = (maximum - len(info[0])) + 1
        formatted.append(
            "... {}:{}[ {} ]".format(info[0], " " * padding, info[1]))
    return formatted


if __name__ == "__main__":
    boot()
