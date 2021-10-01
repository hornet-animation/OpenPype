from openpype import resources
from openpype.hosts.testhost.api import pipeline
from openpype.pipeline import (
    Creator,
    CreatedInstance,
    lib
)


class TestCreatorOne(Creator):
    identifier = "test_one"
    family = "test"
    description = "Testing creator of testhost"

    def get_icon(self):
        return resources.get_openpype_splash_filepath()

    def collect_instances(self, attr_plugins):
        for instance_data in pipeline.list_instances():
            creator_id = instance_data.get("creator_identifier")
            if creator_id is not None:
                if creator_id == self.identifier:
                    subset_name = instance_data["subset"]
                    instance = CreatedInstance(
                        self.family, subset_name, instance_data, self
                    )
                    self._add_instance_to_context(instance)

            elif instance_data["family"] == self.identifier:
                instance_data["creator_identifier"] = self.identifier
                instance = CreatedInstance.from_existing(
                    instance_data, self, attr_plugins
                )
                self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        pipeline.update_instances(update_list)

    def remove_instances(self, instances):
        pipeline.remove_instances(instances)
        for instance in instances:
            self._remove_instance_from_context(instance)

    def create(self, subset_name, data, options=None):
        new_instance = CreatedInstance(self.family, subset_name, data, self)
        pipeline.HostContext.add_instance(new_instance.data_to_store())
        self.log.info(new_instance.data)
        self._add_instance_to_context(new_instance)

    def get_default_variants(self):
        return [
            "myVariant",
            "variantTwo",
            "different_variant"
        ]

    def get_attribute_defs(self):
        output = [
            lib.NumberDef("number_key", label="Number")
        ]
        return output

    def get_detail_description(self):
        return """# Relictus funes est Nyseides currusque nunc oblita

## Causa sed

Lorem markdownum posito consumptis, *plebe Amorque*, abstitimus rogatus fictaque
gladium Circe, nos? Bos aeternum quae. Utque me, si aliquem cladis, et vestigia
arbor, sic mea ferre lacrimae agantur prospiciens hactenus. Amanti dentes pete,
vos quid laudemque rastrorumque terras in gratantibus **radix** erat cedemus?

Pudor tu ponderibus verbaque illa; ire ergo iam Venus patris certe longae
cruentum lecta, et quaeque. Sit doce nox. Anteit ad tempora magni plenaque et
videres mersit sibique auctor in tendunt mittit cunctos ventisque gravitate
volucris quemquam Aeneaden. Pectore Mensis somnus; pectora
[ferunt](http://www.mox.org/oculosbracchia)? Fertilitatis bella dulce et suum?
        """
