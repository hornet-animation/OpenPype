import nuke
import sys
import six

from openpype.pipeline import (
    CreatedInstance
)
from openpype.lib import (
    BoolDef
)
from openpype.hosts.nuke import api as napi


class CreateWriteRender(napi.NukeWriteCreator):
    identifier = "create_write_render"
    label = "Render (write)"
    family = "render"
    icon = "sign-out"

    instance_attributes = [
        "reviewable"
    ]
    default_variants = [
        "Main",
        "Mask"
    ]
    temp_rendering_path_template = (
        "{work}/renders/nuke/{subset}/{subset}.{frame}.{ext}")

    def get_pre_create_attr_defs(self):
        attr_defs = [
            BoolDef(
                "use_selection",
                default=not self.create_context.headless,
                label="Use selection"
            ),
            self._get_render_target_enum()
        ]
        return attr_defs

    def create_instance_node(self, subset_name, instance_data):
        # add fpath_template
        write_data = {
            "creator": self.__class__.__name__,
            "subset": subset_name,
            "fpath_template": self.temp_rendering_path_template
        }

        write_data.update(instance_data)

        # get width and height
        if self.selected_node:
            width, height = (
                self.selected_node.width(), self.selected_node.height())
        else:
            actual_format = nuke.root().knob('format').value()
            width, height = (actual_format.width(), actual_format.height())

        created_node = napi.create_write_node(
            subset_name,
            write_data,
            input=self.selected_node,
            prenodes=self.prenodes,
            **{
                "width": width,
                "height": height
            }
        )
        self.add_info_knob(created_node)

        self.integrate_links(created_node, outputs=False)

        return created_node

    def create(self, subset_name, instance_data, pre_create_data):
        # pass values from precreate to instance
        self.pass_pre_attributes_to_instance(
            instance_data,
            pre_create_data,
            [
                "render_target"
            ]
        )
        # make sure selected nodes are added
        self.set_selected_nodes(pre_create_data)

        # make sure subset name is unique
        self.check_existing_subset(subset_name)

        instance_node = self.create_instance_node(
            subset_name,
            instance_data
        )

        try:
            instance = CreatedInstance(
                self.family,
                subset_name,
                instance_data,
                self
            )

            instance.transient_data["node"] = instance_node

            self._add_instance_to_context(instance)

            napi.set_node_data(
                instance_node,
                napi.INSTANCE_DATA_KNOB,
                instance.data_to_store()
            )

            return instance

        except Exception as er:
            six.reraise(
                napi.NukeCreatorError,
                napi.NukeCreatorError("Creator error: {}".format(er)),
                sys.exc_info()[2]
            )
