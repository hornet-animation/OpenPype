import pyblish.api
import colorbleed.api

from config.apps.maya import lib


class ValidateNodeIDs(pyblish.api.InstancePlugin):
    """Validate nodes have a Colorbleed Id.
    
    When IDs are missing from nodes *save your scene* and they should be 
    automatically generated because IDs are created on non-referenced nodes 
    in Maya upon scene save.

    """

    order = colorbleed.api.ValidatePipelineOrder
    label = 'Instance Nodes Have ID'
    hosts = ['maya']
    families = ["colorbleed.model",
                "colorbleed.look",
                "colorbleed.rig",
                "colorbleed.pointcache",
                "colorbleed.animation",
                "colorbleed.setdress"]

    actions = [colorbleed.api.SelectInvalidAction,
               colorbleed.api.GenerateUUIDsOnInvalidAction]

    def process(self, instance):
        """Process all meshes"""

        # Ensure all nodes have a cbId
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Nodes found without "
                               "IDs: {0}".format(invalid))

    @classmethod
    def get_invalid(cls, instance):
        """Return the member nodes that are invalid"""

        # We do want to check the referenced nodes as it might be
        # part of the end product.
        id_nodes = lib.get_id_required_nodes(referenced_nodes=True,
                                             nodes=instance[:])
        invalid = [n for n in id_nodes if not lib.get_id(n)]

        return invalid
