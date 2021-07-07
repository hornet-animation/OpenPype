from openpype.modules.ftrack.lib import ServerAction


class MultipleNotesServer(ServerAction):
    """Action adds same note for muliple AssetVersions."""

    identifier = "multiple.notes.server"
    label = "Multiple Notes (Server)"
    description = "Add same note to multiple Asset Versions"

    def discover(self, session, entities, event):
        ''' Validation '''
        valid = True
        for entity in entities:
            if entity.entity_type.lower() != 'assetversion':
                valid = False
                break
        return valid

    def interface(self, session, entities, event):
        if not event['data'].get('values', {}):
            note_label = {
                'type': 'label',
                'value': '# Enter note: #'
            }

            note_value = {
                'name': 'note',
                'type': 'textarea'
            }

            category_label = {
                'type': 'label',
                'value': '## Category: ##'
            }

            category_data = []
            category_data.append({
                'label': '- None -',
                'value': 'none'
            })
            all_categories = session.query('NoteCategory').all()
            for cat in all_categories:
                category_data.append({
                    'label': cat['name'],
                    'value': cat['id']
                })
            category_value = {
                'type': 'enumerator',
                'name': 'category',
                'data': category_data,
                'value': 'none'
            }

            splitter = {
                'type': 'label',
                'value': '{}'.format(200*"-")
            }

            items = []
            items.append(note_label)
            items.append(note_value)
            items.append(splitter)
            items.append(category_label)
            items.append(category_value)
            return items

    def launch(self, session, entities, event):
        if 'values' not in event['data']:
            return

        values = event['data']['values']
        if len(values) <= 0 or 'note' not in values:
            return False
        # Get Note text
        note_value = values['note']
        if note_value.lower().strip() == '':
            return False
        # Get User
        user = session.query(
            'User where username is "{}"'.format(session.api_user)
        ).one()
        # Base note data
        note_data = {
            'content': note_value,
            'author': user
        }
        # Get category
        category_value = values['category']
        if category_value != 'none':
            category = session.query(
                'NoteCategory where id is "{}"'.format(category_value)
            ).one()
            note_data['category'] = category
        # Create notes for entities
        for entity in entities:
            new_note = session.create('Note', note_data)
            entity['notes'].append(new_note)
            session.commit()
        return True


def register(session):
    '''Register plugin. Called when used as an plugin.'''

    MultipleNotesServer(session).register()
