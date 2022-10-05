import nuke
from openpype.hosts.nuke.api import (
    NukeCreator,
    NukeCreatorError,
    maintained_selection
)


class CreateCamera(NukeCreator):
    """Add Publishable Camera"""

    identifier = "create_camera"
    label = "Create 3d Camera"
    family = "camera"
    icon = "camera"

    # plugin attributes
    node_color = "0xff9100ff"

    def create_instance_node(
        self,
        node_name,
        knobs=None,
        parent=None,
        node_type=None
    ):
        with maintained_selection():
            if self.selected_nodes:
                created_node = self.selected_nodes[0]
            else:
                created_node = nuke.createNode("Camera2")

            created_node["tile_color"].setValue(
                int(self.node_color, 16))

            created_node["name"].setValue(node_name)

            self.add_info_knob(created_node)

            return created_node

    def create(self, subset_name, instance_data, pre_create_data):
        if self.check_existing_subset(subset_name, instance_data):
            raise NukeCreatorError(
                ("subset {} is already published with different HDA"
                 "definition.").format(subset_name))

        instance = super(CreateCamera, self).create(
            subset_name,
            instance_data,
            pre_create_data
        )

        return instance

    def set_selected_nodes(self, pre_create_data):
        if pre_create_data.get("use_selection"):
            self.selected_nodes = nuke.selectedNodes()
            if self.selected_nodes == []:
                raise NukeCreatorError("Creator error: No active selection")
            elif len(self.selected_nodes) > 1:
                NukeCreatorError("Creator error: Select only one camera node")
        else:
            self.selected_nodes = []

        self.log.debug("Selection is: {}".format(self.selected_nodes))

    def apply_settings(self, project_settings, system_settings):
        """Method called on initialization of plugin to apply settings."""

        # only selected keys ideally
        # settings = self.get_creator_settings(project_settings)

        # self.key = settings["key"]
        pass