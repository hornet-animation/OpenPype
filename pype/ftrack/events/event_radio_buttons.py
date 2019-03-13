import ftrack_api
from pype.ftrack import BaseEvent


ignore_me = True


class Radio_buttons(BaseEvent):

    def launch(self, session, entities, event):
        '''Provides a readio button behaviour to any bolean attribute in
           radio_button group.'''

        # start of event procedure ----------------------------------
        for entity in event['data'].get('entities', []):

            if entity['entityType'] == 'assetversion':

                query = 'CustomAttributeGroup where name is "radio_button"'
                group = session.query(query).one()
                radio_buttons = []
                for g in group['custom_attribute_configurations']:
                    radio_buttons.append(g['key'])

                for key in entity['keys']:
                    if (key in radio_buttons and entity['changes'] is not None):
                        if entity['changes'][key]['new'] == '1':
                            version = session.get('AssetVersion',
                                                  entity['entityId'])
                            asset = session.get('Asset', entity['parentId'])
                            for v in asset['versions']:
                                if version is not v:
                                    v['custom_attributes'][key] = 0

            session.commit()

def register(session):
    '''Register plugin. Called when used as an plugin.'''
    if not isinstance(session, ftrack_api.session.Session):
        return

    Radio_buttons(session).register()
