import ftrack_api
from pype.ftrack import BaseEvent


class CollectEntities(BaseEvent):

    priority = 1

    def launch(self, event):
        entities, entity_types = self.translate_event(event)
        entities_count = len(entities)
        event['data']['entities'] = entities
        event['data']['entity_types'] = entity_types
        event['data']['entities_count'] = entities_count

        return True

    def translate_event(self, event):
        selection = event['data'].get('selection', [])

        entities = list()
        entity_types = set()
        for entity in selection:
            ent = self.session.get(
                self.get_entity_type(entity),
                entity.get('entityId')
            )
            entities.append(ent)
            entity_types.add(ent.entity_type)

        return [entities, entity_types]

    def get_entity_type(self, entity):
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

    def register(self):
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover'
            ' and source.user.username={0}'.format(self.session.api_user),
            self.launch,
            priority=self.priority
        )


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''
    if not isinstance(session, ftrack_api.session.Session):
        return

    CollectEntities(session).register()
