import pyblish.api
import os
import clique
import json


class IntegrateFtrackInstance(pyblish.api.InstancePlugin):
    """Collect ftrack component data

    Add ftrack component list to instance.


    """

    order = pyblish.api.IntegratorOrder + 0.48
    label = 'Integrate Ftrack Component'
    families = ["ftrack"]

    family_mapping = {'camera': 'cam',
                      'look': 'look',
                      'mayaAscii': 'scene',
                      'model': 'geo',
                      'rig': 'rig',
                      'setdress': 'setdress',
                      'pointcache': 'cache',
                      'write': 'img',
                      'render': 'render',
                      'review': 'mov'}

    def process(self, instance):

        self.log.debug('instance {}'.format(instance))

        assumed_data = instance.data["assumedTemplateData"]
        assumed_version = assumed_data["VERSION"]
        version_number = int(assumed_version)
        family = instance.data['family'].lower()
        asset_type = ''

        asset_type = self.family_mapping[family]

        componentList = []

        dst_list = instance.data['destination_list']

        ft_session = instance.context.data["ftrackSession"]

        for file in instance.data['destination_list']:
            self.log.debug('file {}'.format(file))

        for file in dst_list:
            filename, ext = os.path.splitext(file)
            self.log.debug('dest ext: ' + ext)
            thumbnail = False

            if ext in ['.mov']:
                location = ft_session.query(
                    'Location where name is "ftrack.server"').one()
                component_data = {
                    "name": "ftrackreview-mp4",  # Default component name is "main".
                    "metadata": {'ftr_meta': json.dumps({
                        'frameIn': int(instance.data["startFrame"]),
                        'frameOut': int(instance.data["startFrame"]),
                        'frameRate': 25})}
                        }
            elif ext in [".jpg"]:
                component_data = {
                    "name": "thumbnail"  # Default component name is "main".
                    }
                thumbnail = True
                location = ft_session.query(
                    'Location where name is "ftrack.server"').one()
            else:
                component_data = {
                    "name": ext[1:]  # Default component name is "main".
                    }

                location = ft_session.query(
                    'Location where name is "ftrack.unmanaged"').one()

            self.log.debug('location {}'.format(location))

            componentList.append({"assettype_data": {
                "short": asset_type,
            },
                "asset_data": {
                "name": instance.data["subset"],
            },
                "assetversion_data": {
                "version": version_number,
            },
                "component_data": component_data,
                "component_path": file,
                'component_location': location,
                "component_overwrite": False,
                "thumbnail": thumbnail
            }
            )

        self.log.debug('componentsList: {}'.format(str(componentList)))
        instance.data["ftrackComponentsList"] = componentList
