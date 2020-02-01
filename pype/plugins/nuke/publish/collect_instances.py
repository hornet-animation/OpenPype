import os

import nuke
import pyblish.api
from avalon import io, api
from avalon.nuke import get_avalon_knob_data


@pyblish.api.log
class CollectNukeInstances(pyblish.api.ContextPlugin):
    """Collect all nodes with Avalon knob."""

    order = pyblish.api.CollectorOrder + 0.01
    label = "Collect Instances"
    hosts = ["nuke", "nukeassist"]

    def process(self, context):
        asset_data = io.find_one({
            "type": "asset",
            "name": api.Session["AVALON_ASSET"]
        })

        self.log.debug("asset_data: {}".format(asset_data["data"]))
        instances = []

        root = nuke.root()

        self.log.debug("nuke.allNodes(): {}".format(nuke.allNodes()))
        for node in nuke.allNodes():

            if node.Class() in ["Viewer", "Dot"]:
                continue

            try:
                if node["disable"].value():
                    continue
            except Exception as E:
                self.log.warning(E)


            # get data from avalon knob
            self.log.debug("node[name]: {}".format(node['name'].value()))
            avalon_knob_data = get_avalon_knob_data(node, ["avalon:", "ak:"])

            self.log.debug("avalon_knob_data: {}".format(avalon_knob_data))

            if not avalon_knob_data:
                continue

            if avalon_knob_data["id"] != "pyblish.avalon.instance":
                continue

            # establish families
            family = avalon_knob_data["family"]
            families = list()

            # except disabled nodes but exclude backdrops in test
            if ("nukenodes" not in family) and (node["disable"].value()):
                continue

            subset = avalon_knob_data.get(
                "subset", None) or node["name"].value()

            # Create instance
            instance = context.create_instance(subset)
            instance.append(node)

            # Add all nodes in group instances.
            if node.Class() == "Group":
                # only alter families for render family
                if ("render" in family):
                    # check if node is not disabled
                    families.append(avalon_knob_data["families"])
                    if node["render"].value():
                        self.log.info("flagged for render")
                        add_family = "render.local"
                        # dealing with local/farm rendering
                        if node["render_farm"].value():
                            self.log.info("adding render farm family")
                            add_family = "render.farm"
                            instance.data["transfer"] = False
                        families.append(add_family)
                    else:
                        # add family into families
                        families.insert(0, family)

                node.begin()
                for i in nuke.allNodes():
                    instance.append(i)
                node.end()

            family = avalon_knob_data["family"]
            families = list()
            families_ak = avalon_knob_data.get("families")

            if families_ak:
                families.append(families_ak)
            else:
                families.append(family)

            # Get format
            format = root['format'].value()
            resolution_width = format.width()
            resolution_height = format.height()
            pixel_aspect = format.pixelAspect()

            if node.Class() not in "Read":
                if "render" not in node.knobs().keys():
                    pass
                elif node["render"].value():
                    self.log.info("flagged for render")
                    add_family = "render.local"
                    # dealing with local/farm rendering
                    if node["render_farm"].value():
                        self.log.info("adding render farm family")
                        add_family = "render.farm"
                        instance.data["transfer"] = False
                    families.append(add_family)
                else:
                    # add family into families
                    families.insert(0, family)

            instance.data.update({
                "subset": subset,
                "asset": os.environ["AVALON_ASSET"],
                "label": node.name(),
                "name": node.name(),
                "subset": subset,
                "family": family,
                "families": families,
                "avalonKnob": avalon_knob_data,
                "publish": node.knob('publish').value(),
                "step": 1,
                "fps": nuke.root()['fps'].value(),
                "resolutionWidth": resolution_width,
                "resolutionHeight": resolution_height,
                "pixelAspect": pixel_aspect,

            })

            self.log.info("collected instance: {}".format(instance.data))
            instances.append(instance)

        context.data["instances"] = instances
        self.log.debug("context: {}".format(context))
