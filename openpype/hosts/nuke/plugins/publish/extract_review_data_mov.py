import os
import re
from pprint import pformat
import pyblish.api

from openpype.pipeline import publish
from openpype.hosts.nuke.api import plugin
from openpype.hosts.nuke.api.lib import maintained_selection


class ExtractReviewDataMov(publish.Extractor):
    """Extracts movie and thumbnail with baked in luts

    must be run after extract_render_local.py

    """

    order = pyblish.api.ExtractorOrder + 0.01
    label = "Extract Review Data Mov"

    families = ["review"]
    hosts = ["nuke"]

    # presets
    viewer_lut_raw = None
    outputs = {}

    def process(self, instance):
        families = set(instance.data["families"])

        # add main family to make sure all families are compared
        families.add(instance.data["family"])

        task_type = instance.context.data["taskType"]
        subset = instance.data["subset"]
        self.log.info("Creating staging dir...")

        if "representations" not in instance.data:
            instance.data["representations"] = []

        staging_dir = os.path.normpath(
            os.path.dirname(instance.data["path"]))

        instance.data["stagingDir"] = staging_dir

        self.log.info(
            "StagingDir `{0}`...".format(instance.data["stagingDir"]))

        self.log.info(self.outputs)

        # generate data
        with maintained_selection():
            generated_repres = []
            for o_name, o_data in self.outputs.items():
                self.log.debug(
                    "o_name: {}, o_data: {}".format(o_name, pformat(o_data)))
                f_families = o_data["filter"]["families"]
                f_task_types = o_data["filter"]["task_types"]
                f_subsets = o_data["filter"]["subsets"]

                self.log.debug(
                    "f_families `{}` > families: {}".format(
                        f_families, families))

                self.log.debug(
                    "f_task_types `{}` > task_type: {}".format(
                        f_task_types, task_type))

                self.log.debug(
                    "f_subsets `{}` > subset: {}".format(
                        f_subsets, subset))

                # test if family found in context
                # using intersection to make sure all defined
                # families are present in combination
                if f_families and not families.intersection(f_families):
                    continue

                # test task types from filter
                if f_task_types and task_type not in f_task_types:
                    continue

                # test subsets from filter
                if f_subsets and not any(
                        re.search(s, subset) for s in f_subsets):
                    continue

                self.log.info(
                    "Baking output `{}` with settings: {}".format(
                        o_name, o_data))

                # check if settings have more then one preset
                # so we dont need to add outputName to representation
                # in case there is only one preset
                multiple_presets = len(self.outputs.keys()) > 1

                # adding bake presets to instance data for other plugins
                if not instance.data.get("bakePresets"):
                    instance.data["bakePresets"] = {}
                # add preset to bakePresets
                instance.data["bakePresets"][o_name] = o_data

                # create exporter instance
                exporter = plugin.ExporterReviewMov(
                    self, instance, o_name, o_data["extension"],
                    multiple_presets)

                if (
                    "render.farm" in families or
                    "prerender.farm" in families
                ):
                    if "review" in instance.data["families"]:
                        instance.data["families"].remove("review")

                    data = exporter.generate_mov(farm=True, **o_data)

                    self.log.debug(
                        "_ data: {}".format(data))

                    if not instance.data.get("bakingNukeScripts"):
                        instance.data["bakingNukeScripts"] = []

                    instance.data["bakingNukeScripts"].append({
                        "bakeRenderPath": data.get("bakeRenderPath"),
                        "bakeScriptPath": data.get("bakeScriptPath"),
                        "bakeWriteNodeName": data.get("bakeWriteNodeName")
                    })
                else:
                    data = exporter.generate_mov(**o_data)

                # add representation generated by exporter
                generated_repres.extend(data["representations"])
                self.log.debug(
                    "__ generated_repres: {}".format(generated_repres))

        if generated_repres:
            # assign to representations
            instance.data["representations"] += generated_repres
            instance.data["useSequenceForReview"] = False
        else:
            instance.data["families"].remove("review")
            self.log.info((
                "Removing `review` from families. "
                "Not available baking profile."
            ))
            self.log.debug(instance.data["families"])

        self.log.debug(
            "_ representations: {}".format(
                instance.data["representations"]))
