from avalon import api, aftereffects
from pype.plugins import lib
import re

stub = aftereffects.stub()


class FileLoader(api.Loader):
    """Load images

    Stores the imported asset in a container named after the asset.
    """
    label = "File Loader"

    families = ["image",
                "render2d",
                "source",
                "plate",
                "render",
                "prerender",
                "review",
                "preview",
                "workfile",
                "audio"]
    representations = ["*"]

    def load(self, context, name=None, namespace=None, data=None):
        comp_name = lib.get_unique_layer_name(stub.get_items(comps=True),
                                              context["asset"]["name"],
                                              name)

        import_options = {}

        file = self.fname

        repr_cont = context["representation"]["context"]
        if "#" not in file:
            frame = repr_cont.get("frame")
            if frame:
                padding = len(frame)
                file = file.replace(frame, "#" * padding)
                import_options['sequence'] = True

        if not file:
            repr_id = context["representation"]["_id"]
            self.log.warning(
                "Representation id `{}` is failing to load".format(repr_id))
            return

        file = file.replace("\\", "/")
        if '.psd' in file:
            import_options['ImportAsType'] = 'ImportAsType.COMP'

        comp = stub.import_file(self.fname, comp_name, import_options)

        if not comp:
            self.log.warning(
                "Representation id `{}` is failing to load".format(file))
            self.log.warning("Check host app for alert error.")
            return

        self[:] = [comp]
        namespace = namespace or comp_name

        return aftereffects.containerise(
            name,
            namespace,
            comp,
            context,
            self.__class__.__name__
        )

    def update(self, container, representation):
        """ Switch asset or change version """
        layer = container.pop("layer")

        context = representation.get("context", {})

        namespace_from_container = re.sub(r'_\d{3}$', '',
                                          container["namespace"])
        layer_name = "{}_{}".format(context["asset"], context["subset"])
        # switching assets
        if namespace_from_container != layer_name:
            layer_name = lib.get_unique_layer_name(stub.get_items(comps=True),
                                                   context["asset"],
                                                   context["subset"])
        else:  # switching version - keep same name
            layer_name = container["namespace"]
        path = api.get_representation_path(representation)
        # with aftereffects.maintained_selection():  # TODO
        stub.replace_item(layer, path, layer_name)
        stub.imprint(
            layer, {"representation": str(representation["_id"]),
                    "name": context["subset"],
                    "namespace": layer_name}
        )

    def remove(self, container):
        """
            Removes element from scene: deletes layer + removes from Headline
        Args:
            container (dict): container to be removed - used to get layer_id
        """
        layer = container.pop("layer")
        stub.imprint(layer, {})
        stub.delete_item(layer.id)

    def switch(self, container, representation):
        self.update(container, representation)
