# :coding: utf-8
# :copyright: Copyright (c) 2017 ftrack
import os
import logging
import getpass
import platform
import ftrack_api
import toml
from avalon import io, lib, pipeline
from avalon import session as sess

from app.api import (
    Templates
)

t = Templates()



class AppAction(object):
    '''Custom Action base class

    <label> - a descriptive string identifing your action.
    <varaint>   - To group actions together, give them the same
                  label and specify a unique variant per action.
    <identifier>  - a unique identifier for app.
    <description>   - a verbose descriptive text for you action
    <icon>  - icon in ftrack
     '''

    def __init__(self, session, label, name, executable, variant=None, icon=None, description=None):
        '''Expects a ftrack_api.Session instance'''

        self.logger = logging.getLogger(
            '{0}.{1}'.format(__name__, self.__class__.__name__)
        )

        if label is None:
            raise ValueError('Action missing label.')
        elif name is None:
            raise ValueError('Action missing identifier.')
        elif executable is None:
            raise ValueError('Action missing executable.')

        self._session = session
        self.label = label
        self.identifier = name
        self.executable = executable
        self.variant = variant
        self.icon = icon
        self.description = description


    @property
    def session(self):
        '''Return current session.'''
        return self._session

    def register(self):
        '''Registers the action, subscribing the the discover and launch topics.'''
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover and source.user.username={0}'.format(
                self.session.api_user
                ), self._discover
        )

        self.session.event_hub.subscribe(
            'topic=ftrack.action.launch and data.actionIdentifier={0} and source.user.username={1}'.format(
                self.identifier,
                self.session.api_user
            ),
            self._launch
        )


    def _discover(self, event):
        args = self._translate_event(
            self.session, event
        )

        accepts = self.discover(
            self.session, *args
        )

        if accepts:
            self.logger.info('Selection is valid')
            return {
                'items': [{
                    'label': self.label,
                    'variant': self.variant,
                    'description': self.description,
                    'actionIdentifier': self.identifier,
                    'icon': self.icon,
                }]
            }
        else:
            self.logger.info('Selection is _not_ valid')

    def discover(self, session, entities, event):
        '''Return true if we can handle the selected entities.

        *session* is a `ftrack_api.Session` instance


        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''

        entity_type, entity_id = entities[0]
        entity = session.get(entity_type, entity_id)

        # TODO Should return False if not TASK ?!!!
        if entity.entity_type != 'Task':
            return False

        # TODO Should return False if more than one entity is selected ?!!!
        if len(entities) > 1:
            return False

        ft_project = entity['project'] if (entity.entity_type != 'Project') else entity

        os.environ['AVALON_PROJECT'] = ft_project['full_name']
        io.install()
        project = io.find_one({"type": "project", "name": ft_project['full_name']})
        io.uninstall()

        if project is None:
            return False
        else:
            apps = []
            for app in project['config']['apps']:
                apps.append(app['name'].split("_")[0])

            if self.identifier not in apps:
                return False

        return True

    def _translate_event(self, session, event):
        '''Return *event* translated structure to be used with the API.'''

        _selection = event['data'].get('selection', [])

        _entities = list()
        for entity in _selection:
            _entities.append(
                (
                    self._get_entity_type(entity), entity.get('entityId')
                )
            )

        return [
            _entities,
            event
        ]

    def _get_entity_type(self, entity):
        '''Return translated entity type tht can be used with API.'''
        # Get entity type and make sure it is lower cased. Most places except
        # the component tab in the Sidebar will use lower case notation.
        entity_type = entity.get('entityType').replace('_', '').lower()

        for schema in self.session.schemas:
            alias_for = schema.get('alias_for')

            if (
                alias_for and isinstance(alias_for, str) and
                alias_for.lower() == entity_type
            ):
                return schema['id']

        for schema in self.session.schemas:
            if schema['id'].lower() == entity_type:
                return schema['id']

        raise ValueError(
            'Unable to translate entity type: {0}.'.format(entity_type)
        )

    def _launch(self, event):
        args = self._translate_event(
            self.session, event
        )

        interface = self._interface(
            self.session, *args
        )

        if interface:
            return interface

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

        # TODO Delete this line
        print("Action - {0} ({1}) - just started".format(self.label, self.identifier))

        entity, id = entities[0]
        entity = session.get(entity, id)

        silo = "Film"
        if entity.entity_type=="AssetBuild":
            silo= "Asset"

        # set environments for Avalon
        os.environ["AVALON_PROJECT"] = entity['project']['full_name']
        os.environ["AVALON_SILO"] = silo
        os.environ["AVALON_ASSET"] = entity['parent']['name']
        os.environ["AVALON_TASK"] = entity['name']
        os.environ["AVALON_APP"] = self.identifier
        os.environ["AVALON_APP_NAME"] = self.identifier + "_" + self.variant


        anatomy = t.anatomy
        io.install()
        hierarchy = io.find_one({"type":'asset', "name":entity['parent']['name']})['data']['parents']
        io.uninstall()
        if hierarchy:
            # hierarchy = os.path.sep.join(hierarchy)
            hierarchy = os.path.join(*hierarchy)

        data = { "project": {"name": entity['project']['full_name'],
                            "code": entity['project']['name']},
                 "task": entity['name'],
                 "asset": entity['parent']['name'],
                 "hierarchy": hierarchy}

        anatomy = anatomy.format(data)


        os.environ["AVALON_WORKDIR"] = os.path.join(anatomy.work.root, anatomy.work.folder)

        # TODO Add paths to avalon setup from tomls
        if self.identifier == 'maya':
            os.environ['PYTHONPATH'] += os.pathsep + os.path.join(os.getenv("AVALON_CORE"), 'setup', 'maya')
        elif self.identifier == 'nuke':
            os.environ['NUKE_PATH'] = os.pathsep + os.path.join(os.getenv("AVALON_CORE"), 'setup', 'nuke')
        # config = toml.load(lib.which_app(self.identifier + "_" + self.variant))


        env = os.environ
        # Get path to execute
        st_temp_path = os.environ['PYPE_STUDIO_TEMPLATES']
        os_plat = platform.system().lower()

        # Path to folder with launchers
        path = os.path.join(st_temp_path, 'bin', os_plat)
        # Full path to executable launcher
        execfile = None

        for ext in os.environ["PATHEXT"].split(os.pathsep):
            fpath = os.path.join(path.strip('"'), self.executable + ext)
            if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
                execfile = fpath
                break

        # Run SW if was found executable
        if execfile is not None:
            lib.launch(executable=execfile, args=[], environment=env)
        else:
            return {
                'success': False,
                'message': "We didn't found launcher for {0}".format(self.label)
            }

        # RUN TIMER IN FTRACK
        username = event['source']['user']['username']
        user = session.query('User where username is "{}"'.format(username)).one()
        task = session.query('Task where id is {}'.format(entity['id'])).one()
        print('Starting timer for task: ' + task['name'])
        user.start_timer(task, force=True)

        return {
            'success': True,
            'message': "Launching {0}".format(self.label)
        }

    def _interface(self, *args):
        interface = self.interface(*args)

        if interface:
            return {
                'items': interface
            }

    def interface(self, session, entities, event):
        '''Return a interface if applicable or None

        *session* is a `ftrack_api.Session` instance

        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event
        '''
        return None

    def _handle_result(self, session, result, entities, event):
        '''Validate the returned result from the action callback'''
        if isinstance(result, bool):
            result = {
                'success': result,
                'message': (
                    '{0} launched successfully.'.format(
                        self.label
                    )
                )
            }

        elif isinstance(result, dict):
            for key in ('success', 'message'):
                if key in result:
                    continue

                raise KeyError(
                    'Missing required key: {0}.'.format(key)
                )

        else:
            self.logger.error(
                'Invalid result type must be bool or dictionary!'
            )

        return result


class BaseAction(object):
    '''Custom Action base class

    `label` a descriptive string identifing your action.

    `varaint` To group actions together, give them the same
    label and specify a unique variant per action.

    `identifier` a unique identifier for your action.

    `description` a verbose descriptive text for you action

     '''
    label = None
    variant = None
    identifier = None
    description = None
    icon = None

    def __init__(self, session):
        '''Expects a ftrack_api.Session instance'''

        self.logger = logging.getLogger(
            '{0}.{1}'.format(__name__, self.__class__.__name__)
        )

        if self.label is None:
            raise ValueError(
                'Action missing label.'
            )

        elif self.identifier is None:
            raise ValueError(
                'Action missing identifier.'
            )

        self._session = session

    @property
    def session(self):
        '''Return current session.'''
        return self._session

    def register(self):
        '''Registers the action, subscribing the the discover and launch topics.'''
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover and source.user.username={0}'.format(
                self.session.api_user
                ), self._discover
        )

        self.session.event_hub.subscribe(
            'topic=ftrack.action.launch and data.actionIdentifier={0} and source.user.username={1}'.format(
                self.identifier,
                self.session.api_user
            ),
            self._launch
        )
        print("----- action - <" + self.__class__.__name__ + "> - Has been registered -----")

    def _discover(self, event):
        args = self._translate_event(
            self.session, event
        )

        accepts = self.discover(
            self.session, *args
        )

        if accepts:
            self.logger.info(u'Discovering action with selection: {0}'.format(args[1]['data'].get('selection', [])))
            return {
                'items': [{
                    'label': self.label,
                    'variant': self.variant,
                    'description': self.description,
                    'actionIdentifier': self.identifier,
                    'icon': self.icon,
                }]
            }

    def discover(self, session, entities, event):
        '''Return true if we can handle the selected entities.

        *session* is a `ftrack_api.Session` instance


        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''

        return False

    def _translate_event(self, session, event):
        '''Return *event* translated structure to be used with the API.'''

        _selection = event['data'].get('selection', [])

        _entities = list()
        for entity in _selection:
            _entities.append(
                (
                    session.get(self._get_entity_type(entity), entity.get('entityId'))
                    # self._get_entity_type(entity), entity.get('entityId')
                )
            )

        return [
            _entities,
            event
        ]

    def _get_entity_type(self, entity):
        '''Return translated entity type tht can be used with API.'''
        # Get entity type and make sure it is lower cased. Most places except
        # the component tab in the Sidebar will use lower case notation.
        entity_type = entity.get('entityType').replace('_', '').lower()

        for schema in self.session.schemas:
            alias_for = schema.get('alias_for')

            if (
                alias_for and isinstance(alias_for, str) and
                alias_for.lower() == entity_type
            ):
                return schema['id']

        for schema in self.session.schemas:
            if schema['id'].lower() == entity_type:
                return schema['id']

        raise ValueError(
            'Unable to translate entity type: {0}.'.format(entity_type)
        )

    def _launch(self, event):
        args = self._translate_event(
            self.session, event
        )

        interface = self._interface(
            self.session, *args
        )

        if interface:
            return interface

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
        raise NotImplementedError()

    def _interface(self, *args):
        interface = self.interface(*args)

        if interface:
            return {
                'items': interface
            }

    def interface(self, session, entities, event):
        '''Return a interface if applicable or None

        *session* is a `ftrack_api.Session` instance

        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event
        '''
        return None

    def _handle_result(self, session, result, entities, event):
        '''Validate the returned result from the action callback'''
        if isinstance(result, bool):
            result = {
                'success': result,
                'message': (
                    '{0} launched successfully.'.format(
                        self.label
                    )
                )
            }

        elif isinstance(result, dict):
            for key in ('success', 'message'):
                if key in result:
                    continue

                raise KeyError(
                    'Missing required key: {0}.'.format(key)
                )

        else:
            self.logger.error(
                'Invalid result type must be bool or dictionary!'
            )

        return result
