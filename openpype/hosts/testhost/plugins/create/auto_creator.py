from openpype.hosts.testhost.api import pipeline
from openpype.pipeline import (
    AutoCreator,
    CreatedInstance,
    lib
)
from avalon import io


class MyAutoCreator(AutoCreator):
    identifier = "workfile"
    family = "workfile"

    def get_attribute_defs(self):
        output = [
            lib.NumberDef("number_key", label="Number")
        ]
        return output

    def collect_instances(self, attr_plugins=None):
        for instance_data in pipeline.list_instances():
            creator_id = instance_data.get("creator_identifier")
            if creator_id is not None:
                if creator_id == self.identifier:
                    subset_name = instance_data["subset"]
                    instance = CreatedInstance(
                        self.family, subset_name, instance_data, self
                    )
                    self.create_context.add_instance(instance)

            elif instance_data["family"] == self.identifier:
                instance_data["creator_identifier"] = self.identifier
                instance = CreatedInstance.from_existing(
                    instance_data, self, attr_plugins
                )
                self.create_context.add_instance(instance)

    def update_instances(self, update_list):
        pipeline.update_instances(update_list)

    def create(self, options=None):
        existing_instance = None
        for instance in self.create_context.instances:
            if instance.family == self.family:
                existing_instance = instance
                break

        variant = "Main"
        project_name = io.Session["AVALON_PROJECT"]
        asset_name = io.Session["AVALON_ASSET"]
        task_name = io.Session["AVALON_TASK"]
        host_name = io.Session["AVALON_APP"]

        if existing_instance is None:
            asset_doc = io.find_one({"type": "asset", "name": asset_name})
            subset_name = self.get_subset_name(
                variant, task_name, asset_doc, project_name, host_name
            )
            data = {
                "asset": asset_name,
                "task": task_name,
                "variant": variant
            }
            data.update(self.get_dynamic_data(
                variant, task_name, asset_doc, project_name, host_name
            ))

            existing_instance = CreatedInstance(
                self.family, subset_name, data, self
            )
            pipeline.HostContext.add_instance(
                existing_instance.data_to_store()
            )

        elif (
            existing_instance.data["asset"] != asset_name
            or existing_instance.data["task"] != task_name
        ):
            asset_doc = io.find_one({"type": "asset", "name": asset_name})
            subset_name = self.get_subset_name(
                variant, task_name, asset_doc, project_name, host_name
            )
            existing_instance.data["asset"] = asset_name
            existing_instance.data["task"] = task_name

        return existing_instance
