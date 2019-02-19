import os
import toml
import time
from pype.ftrack import AppAction
from avalon import lib
from app.api import Logger
from pype import lib as pypelib

log = Logger.getLogger(__name__)


def registerApp(app, session):
    name = app['name']
    variant = ""
    try:
        variant = app['name'].split("_")[1]
    except Exception:
        log.warning((
            '"{0}" - App "name" and "variant" is not separated by "_"'
            ' (variant is not set)'
        ).format(app['name']))

    abspath = lib.which_app(app['name'])
    if abspath is None:
        log.error(
            "'{0}' - App don't have config toml file".format(app['name'])
        )
        return

    apptoml = toml.load(abspath)

    ''' REQUIRED '''
    executable = apptoml['executable']

    ''' OPTIONAL '''
    label = apptoml.get('ftrack_label', app.get('label', name))
    icon = apptoml.get('ftrack_icon', None)
    description = apptoml.get('description', None)
    preactions = apptoml.get('preactions', None)
    process_name = apptoml.get('process_name', None)
    script_path = apptoml.get('script_path', None)

    once_run_data = None
    if process_name is not None or script_path is not None:
        try:
            script_path = script_path.format(**os.environ)
            script_path.replace('/', os.path.sep)
        except Exception:
            pass
        once_run_data = {
            'process_name': process_name,
            'script_path': script_path
        }
    # register action
    AppAction(
        session, label, name, executable, variant, icon, description,
        preactions, once_run_data
    ).register()


def register(session):
    projects = pypelib.get_all_avalon_projects()

    apps = []
    appNames = []
    # Get all application from all projects
    for project in projects:
        for app in project['config']['apps']:
            if app['name'] not in appNames:
                appNames.append(app['name'])
                apps.append(app)

    apps = sorted(apps, key=lambda x: x['name'])
    for app in apps:
        try:
            registerApp(app, session)
            time.sleep(0.05)
        except Exception as e:
            log.warning("'{0}' - not proper App ({1})".format(app['name'], e))
