import os
import sys
import copy
import platform
from avalon import lib as avalonlib
import acre
from pype import lib as pypelib
from pypeapp import config
from .ftrack_base_handler import BaseHandler

from pypeapp import Anatomy


class AppAction(BaseHandler):
    '''Custom Action base class

    <label> - a descriptive string identifing your action.
    <varaint>   - To group actions together, give them the same
                  label and specify a unique variant per action.
    <identifier>  - a unique identifier for app.
    <description>   - a verbose descriptive text for you action
    <icon>  - icon in ftrack
    '''

    type = 'Application'
    preactions = ['start.timer']

    def __init__(
        self, session, label, name, executable, variant=None,
        icon=None, description=None, preactions=[], plugins_presets={}
    ):
        super().__init__(session, plugins_presets)
        '''Expects a ftrack_api.Session instance'''

        if label is None:
            raise ValueError('Action missing label.')
        elif name is None:
            raise ValueError('Action missing identifier.')
        elif executable is None:
            raise ValueError('Action missing executable.')

        self.label = label
        self.identifier = name
        self.executable = executable
        self.variant = variant
        self.icon = icon
        self.description = description
        self.preactions.extend(preactions)

    def register(self):
        '''Registers the action, subscribing the discover and launch topics.'''

        discovery_subscription = (
            'topic=ftrack.action.discover and source.user.username={0}'
        ).format(self.session.api_user)

        self.session.event_hub.subscribe(
            discovery_subscription,
            self._discover,
            priority=self.priority
        )

        launch_subscription = (
            'topic=ftrack.action.launch'
            ' and data.actionIdentifier={0}'
            ' and source.user.username={1}'
        ).format(
            self.identifier,
            self.session.api_user
        )
        self.session.event_hub.subscribe(
            launch_subscription,
            self._launch
        )

    def discover(self, session, entities, event):
        '''Return true if we can handle the selected entities.

        *session* is a `ftrack_api.Session` instance

        *entities* is a list of tuples each containing the entity type and
        the entity id. If the entity is a hierarchical you will always get
        the entity type TypedContext, once retrieved through a get operation
        you will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''

        if (
            len(entities) != 1
            or entities[0].entity_type.lower() != 'task'
        ):
            return False

        if entities[0]['parent'].entity_type.lower() == 'project':
            return False

        ft_project = entities[0]['project']

        database = pypelib.get_avalon_database()
        project_name = ft_project['full_name']
        avalon_project = database[project_name].find_one({
            "type": "project"
        })

        if avalon_project is None:
            return False
        else:
            apps = [app['name'] for app in avalon_project['config'].get(
                'apps', []
            )]

            if self.identifier not in apps:
                return False

        return True

    def _launch(self, event):
        args = self._translate_event(
            self.session, event
        )

        preactions_launched = self._handle_preactions(
            self.session, event
        )
        if preactions_launched is False:
            return

        response = self.launch(
            self.session, *args
        )

        return self._handle_result(
            self.session, response, *args
        )

    def launch(self, session, entities, event):
        '''Callback method for the custom action.

        return either a bool ( True if successful or False if the action failed )
        or a dictionary with they keys `message` and `success`, the message should be a
        string and will be displayed as feedback to the user, success should be a bool,
        True if successful or False if the action failed.

        *session* is a `ftrack_api.Session` instance

        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''

        entity = entities[0]
        project_name = entity["project"]["full_name"]

        database = pypelib.get_avalon_database()

        asset_name = entity["parent"]["name"]
        asset_document = database[project_name].find_one({
            "type": "asset",
            "name": asset_name
        })

        hierarchy = ""
        asset_doc_parents = asset_document["data"].get("parents")
        if len(asset_doc_parents) > 0:
            hierarchy = os.path.join(*asset_doc_parents)

        application = avalonlib.get_application(self.identifier)
        data = {
            "project": {
                "name": entity["project"]["full_name"],
                "code": entity["project"]["name"]
            },
            "task": entity["name"],
            "asset": asset_name,
            "app": application["application_dir"],
            "hierarchy": hierarchy
        }

        try:
            anatomy = Anatomy(project_name)
            anatomy_filled = anatomy.format(data)
            workdir = os.path.normpath(anatomy_filled["work"]["folder"])

        except Exception as exc:
            msg = "Error in anatomy.format: {}".format(
                str(exc)
            )
            self.log.error(msg, exc_info=True)
            return {
                "success": False,
                "message": msg
            }

        try:
            os.makedirs(workdir)
        except FileExistsError:
            pass

        # set environments for Avalon
        prep_env = copy.deepcopy(os.environ)
        prep_env.update({
            "AVALON_PROJECT": project_name,
            "AVALON_ASSET": asset_name,
            "AVALON_TASK": entity["name"],
            "AVALON_APP": self.identifier.split("_")[0],
            "AVALON_APP_NAME": self.identifier,
            "AVALON_HIERARCHY": hierarchy,
            "AVALON_WORKDIR": workdir
        })

        # collect all parents from the task
        parents = []
        for item in entity['link']:
            parents.append(session.get(item['type'], item['id']))

        # collect all the 'environment' attributes from parents
        tools_attr = [prep_env["AVALON_APP"], prep_env["AVALON_APP_NAME"]]
        tools_env = asset_document["data"].get("tools_env") or []
        tools_attr.extend(tools_env)

        tools_env = acre.get_tools(tools_attr)
        env = acre.compute(tools_env)
        env = acre.merge(env, current_env=dict(prep_env))
        env = acre.append(dict(prep_env), env)

        # Get path to execute
        st_temp_path = os.environ["PYPE_CONFIG"]
        os_plat = platform.system().lower()

        # Path to folder with launchers
        path = os.path.join(st_temp_path, "launchers", os_plat)

        # Full path to executable launcher
        execfile = None
        if sys.platform == "win32":
            for ext in os.environ["PATHEXT"].split(os.pathsep):
                fpath = os.path.join(path.strip('"'), self.executable + ext)
                if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                    execfile = fpath
                    break

            # Run SW if was found executable
            if execfile is None:
                return {
                    "success": False,
                    "message": "We didn't found launcher for {0}".format(
                        self.label
                    )
                }

            popen = avalonlib.launch(
                executable=execfile, args=[], environment=env
            )

        elif sys.platform.startswith("linux"):
            execfile = os.path.join(path.strip('"'), self.executable)
            if not os.path.isfile(execfile):
                msg = "Launcher doesn't exist - {}".format(execfile)

                self.log.error(msg)
                return {
                    "success": False,
                    "message": msg
                }

            try:
                fp = open(execfile)
            except PermissionError as perm_exc:
                msg = "Access denied on launcher {} - {}".format(
                    execfile, perm_exc
                )

                self.log.exception(msg, exc_info=True)
                return {
                    "success": False,
                    "message": msg
                }

            fp.close()
            # check executable permission
            if not os.access(execfile, os.X_OK):
                msg = "No executable permission - {}".format(execfile)

                self.log.error(msg)
                return {
                    "success": False,
                    "message": msg
                }

            # Run SW if was found executable
            if execfile is None:
                return {
                    "success": False,
                    "message": "We didn't found launcher for {0}".format(
                        self.label
                    )
                }

            popen = avalonlib.launch(
                "/usr/bin/env", args=["bash", execfile], environment=env
            )

        # Change status of task to In progress
        presets = config.get_presets()["ftrack"]["ftrack_config"]

        if "status_update" in presets:
            statuses = presets["status_update"]

            actual_status = entity["status"]["name"].lower()
            already_tested = []
            ent_path = "/".join(
                [ent["name"] for ent in entity["link"]]
            )
            while True:
                next_status_name = None
                for key, value in statuses.items():
                    if key in already_tested:
                        continue
                    if actual_status in value or "_any_" in value:
                        if key != "_ignore_":
                            next_status_name = key
                            already_tested.append(key)
                        break
                    already_tested.append(key)

                if next_status_name is None:
                    break

                try:
                    query = "Status where name is \"{}\"".format(
                        next_status_name
                    )
                    status = session.query(query).one()

                    entity["status"] = status
                    session.commit()
                    self.log.debug("Changing status to \"{}\" <{}>".format(
                        next_status_name, ent_path
                    ))
                    break

                except Exception:
                    session.rollback()
                    msg = (
                        "Status \"{}\" in presets wasn't found"
                        " on Ftrack entity type \"{}\""
                    ).format(next_status_name, entity.entity_type)
                    self.log.warning(msg)

        return {
            "success": True,
            "message": "Launching {0}".format(self.label)
        }
