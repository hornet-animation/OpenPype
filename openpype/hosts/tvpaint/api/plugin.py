import re
import uuid

from openpype.pipeline import (
    LegacyCreator,
    LoaderPlugin,
    registered_host,
)
from openpype.pipeline.create import (
    CreatedInstance,
    get_subset_name,
    AutoCreator,
    Creator as NewCreator,
)
from openpype.pipeline.create.creator_plugins import cache_and_get_instances

from .lib import get_layers_data
from .pipeline import get_current_workfile_context


SHARED_DATA_KEY = "openpype.tvpaint.instances"


def _collect_instances(creator):
    instances_by_identifier = cache_and_get_instances(
        creator, SHARED_DATA_KEY, creator.host.list_instances
    )
    for instance_data in instances_by_identifier[creator.identifier]:
        instance = CreatedInstance.from_existing(instance_data, creator)
        creator._add_instance_to_context(instance)


def _update_instances(creator, update_list):
    if not update_list:
        return

    cur_instances = creator.host.list_instances()
    cur_instances_by_id = {}
    for instance_data in cur_instances:
        instance_id = instance_data.get("instance_id")
        if instance_id:
            cur_instances_by_id[instance_id] = instance_data

    for instance, changes in update_list:
        instance_data = instance.data_to_store()
        cur_instance_data = cur_instances_by_id.get(instance.id)
        if cur_instance_data is None:
            cur_instances.append(instance_data)
            continue
        for key in set(cur_instance_data) - set(instance_data):
            instance_data.pop(key)
        instance_data.update(cur_instance_data)
    creator.host.write_instances(cur_instances)


class TVPaintCreator(NewCreator):
    @property
    def subset_template_family(self):
        return self.family

    def collect_instances(self):
        _collect_instances(self)

    def update_instances(self, update_list):
        _update_instances(self, update_list)

    def remove_instances(self, instances):
        ids_to_remove = {
            instance.id
            for instance in instances
        }
        cur_instances = self.host.list_instances()
        changed = False
        new_instances = []
        for instance_data in cur_instances:
            if instance_data.get("instance_id") in ids_to_remove:
                changed = True
            else:
                new_instances.append(instance_data)

        if changed:
            self.host.write_instances(new_instances)

        for instance in instances:
            self._remove_instance_from_context(instance)

    def get_dynamic_data(self, *args, **kwargs):
        # Change asset and name by current workfile context
        # TODO use context from 'create_context'
        workfile_context = self.host.get_current_context()
        asset_name = workfile_context.get("asset")
        task_name = workfile_context.get("task")
        output = {}
        if asset_name:
            output["asset"] = asset_name
            if task_name:
                output["task"] = task_name
        return output

    def get_subset_name(
        self,
        variant,
        task_name,
        asset_doc,
        project_name,
        host_name=None,
        instance=None
    ):
        dynamic_data = self.get_dynamic_data(
            variant, task_name, asset_doc, project_name, host_name, instance
        )

        return get_subset_name(
            self.subset_template_family,
            variant,
            task_name,
            asset_doc,
            project_name,
            host_name,
            dynamic_data=dynamic_data,
            project_settings=self.project_settings
        )

    def _store_new_instance(self, new_instance):
        instances_data = self.host.list_instances()
        instances_data.append(new_instance.data_to_store())
        self.host.write_instances(instances_data)
        self._add_instance_to_context(new_instance)


class TVPaintAutoCreator(AutoCreator):
    def collect_instances(self):
        _collect_instances(self)

    def update_instances(self, update_list):
        _update_instances(self, update_list)


class Creator(LegacyCreator):
    def __init__(self, *args, **kwargs):
        super(Creator, self).__init__(*args, **kwargs)
        # Add unified identifier created with `uuid` module
        self.data["uuid"] = str(uuid.uuid4())

    @classmethod
    def get_dynamic_data(cls, *args, **kwargs):
        dynamic_data = super(Creator, cls).get_dynamic_data(*args, **kwargs)

        # Change asset and name by current workfile context
        workfile_context = get_current_workfile_context()
        asset_name = workfile_context.get("asset")
        task_name = workfile_context.get("task")
        if "asset" not in dynamic_data and asset_name:
            dynamic_data["asset"] = asset_name

        if "task" not in dynamic_data and task_name:
            dynamic_data["task"] = task_name
        return dynamic_data

    def write_instances(self, data):
        self.log.debug(
            "Storing instance data to workfile. {}".format(str(data))
        )
        host = registered_host()
        return host.write_instances(data)

    def process(self):
        host = registered_host()
        data = host.list_instances()
        data.append(self.data)
        self.write_instances(data)


class Loader(LoaderPlugin):
    hosts = ["tvpaint"]

    @staticmethod
    def get_members_from_container(container):
        if "members" not in container and "objectName" in container:
            # Backwards compatibility
            layer_ids_str = container.get("objectName")
            return [
                int(layer_id) for layer_id in layer_ids_str.split("|")
            ]
        return container["members"]

    def get_unique_layer_name(self, asset_name, name):
        """Layer name with counter as suffix.

        Find higher 3 digit suffix from all layer names in scene matching regex
        `{asset_name}_{name}_{suffix}`. Higher 3 digit suffix is used
        as base for next number if scene does not contain layer matching regex
        `0` is used ase base.

        Args:
            asset_name (str): Name of subset's parent asset document.
            name (str): Name of loaded subset.

        Returns:
            (str): `{asset_name}_{name}_{higher suffix + 1}`
        """
        layer_name_base = "{}_{}".format(asset_name, name)

        counter_regex = re.compile(r"_(\d{3})$")

        higher_counter = 0
        for layer in get_layers_data():
            layer_name = layer["name"]
            if not layer_name.startswith(layer_name_base):
                continue
            number_subpart = layer_name[len(layer_name_base):]
            groups = counter_regex.findall(number_subpart)
            if len(groups) != 1:
                continue

            counter = int(groups[0])
            if counter > higher_counter:
                higher_counter = counter
                continue

        return "{}_{:0>3d}".format(layer_name_base, higher_counter + 1)
