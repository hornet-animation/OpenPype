from avalon import api, style
from avalon.nuke import lib as anlib
from openpype.api import (
    Logger)


class RepairOldLoaders(api.InventoryAction):

    label = "Repair Old Loaders"
    icon = "gears"
    color = style.colors.alert

    log = Logger().get_logger(__name__)

    def process(self, containers):
        import nuke
        new_loader = "LoadClip"

        for cdata in containers:
            orig_loader = cdata["loader"]
            orig_name = cdata["objectName"]
            if orig_loader not in ["LoadSequence", "LoadMov"]:
                self.log.warning(
                    "This repair action is only working on "
                    "`LoadSequence` and `LoadMov` Loaders")
                continue

            new_name = orig_name.replace(orig_loader, new_loader)
            node = nuke.toNode(cdata["objectName"])

            cdata.update({
                "loader": new_loader,
                "objectName": new_name
            })
            node["name"].setValue(new_name)
            # get data from avalon knob
            anlib.set_avalon_knob_data(node, cdata)
