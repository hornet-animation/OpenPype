# -*- coding: utf-8 -*-
"""Loader for Vray Proxy files.

If there are Alembics published along vray proxy (in the same version),
loader will use them instead of native vray vrmesh format.

"""
import os

import maya.cmds as cmds

from avalon.maya import lib
from avalon import api, io
from openpype.api import get_project_settings


class VRayProxyLoader(api.Loader):
    """Load VRayMesh proxy."""

    families = ["vrayproxy"]
    representations = ["vrmesh"]

    label = "Import VRay Proxy"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name=None, namespace=None, options=None):
        # type: (dict, str, str, dict) -> None
        """Loader entry point.

        Args:
            context (dict): Loaded representation context.
            name (str): Name of container.
            namespace (str): Optional namespace name.
            options (dict): Optional loader options.

        """
        from avalon.maya.pipeline import containerise
        from openpype.hosts.maya.api.lib import namespaced

        try:
            family = context["representation"]["context"]["family"]
        except ValueError:
            family = "vrayproxy"

        #  get all representations for this version
        self.fname = self._get_abc(context["version"]["_id"]) or self.fname

        asset_name = context['asset']["name"]
        namespace = namespace or lib.unique_namespace(
            asset_name + "_",
            prefix="_" if asset_name[0].isdigit() else "",
            suffix="_",
        )

        # Ensure V-Ray for Maya is loaded.
        cmds.loadPlugin("vrayformaya", quiet=True)

        with lib.maintained_selection():
            cmds.namespace(addNamespace=namespace)
            with namespaced(namespace, new=False):
                nodes, group_node = self.create_vray_proxy(
                    name, filename=self.fname)

        self[:] = nodes
        if not nodes:
            return

        # colour the group node
        settings = get_project_settings(os.environ['AVALON_PROJECT'])
        colors = settings['maya']['load']['colors']
        c = colors.get(family)
        if c is not None:
            cmds.setAttr("{0}.useOutlinerColor".format(group_node), 1)
            cmds.setAttr("{0}.outlinerColor".format(group_node),
                         c[0], c[1], c[2])

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__)

    def update(self, container, representation):
        # type: (dict, dict) -> None
        """Update container with specified representation."""
        node = container['objectName']
        assert cmds.objExists(node), "Missing container"

        members = cmds.sets(node, query=True) or []
        vraymeshes = cmds.ls(members, type="VRayMesh")
        assert vraymeshes, "Cannot find VRayMesh in container"

        #  get all representations for this version
        filename = self._get_abc(representation["parent"]) or api.get_representation_path(representation)  # noqa: E501

        for vray_mesh in vraymeshes:
            cmds.setAttr("{}.fileName".format(vray_mesh),
                         filename,
                         type="string")

        # Update metadata
        cmds.setAttr("{}.representation".format(node),
                     str(representation["_id"]),
                     type="string")

    def remove(self, container):
        # type: (dict) -> None
        """Remove loaded container."""
        # Delete container and its contents
        if cmds.objExists(container['objectName']):
            members = cmds.sets(container['objectName'], query=True) or []
            cmds.delete([container['objectName']] + members)

        # Remove the namespace, if empty
        namespace = container['namespace']
        if cmds.namespace(exists=namespace):
            members = cmds.namespaceInfo(namespace, listNamespace=True)
            if not members:
                cmds.namespace(removeNamespace=namespace)
            else:
                self.log.warning("Namespace not deleted because it "
                                 "still has members: %s", namespace)

    def switch(self, container, representation):
        # type: (dict, dict) -> None
        """Switch loaded representation."""
        self.update(container, representation)

    def create_vray_proxy(self, name, filename):
        # type: (str, str) -> (list, str)
        """Re-create the structure created by VRay to support vrmeshes

        Args:
            name (str): Name of the asset.
            filename (str): File name of vrmesh.

        Returns:
            nodes(list)

        """
        # Create nodes
        vray_mesh = cmds.createNode('VRayMesh', name="{}_VRMS".format(name))
        mesh_shape = cmds.createNode("mesh", name="{}_GEOShape".format(name))
        vray_mat = cmds.shadingNode("VRayMeshMaterial", asShader=True,
                                    name="{}_VRMM".format(name))
        vray_mat_sg = cmds.sets(name="{}_VRSG".format(name),
                                empty=True,
                                renderable=True,
                                noSurfaceShader=True)

        cmds.setAttr("{}.fileName".format(vray_mesh),
                     filename,
                     type="string")

        # Create important connections
        cmds.connectAttr("time1.outTime",
                         "{0}.currentFrame".format(vray_mesh))
        cmds.connectAttr("{}.fileName2".format(vray_mesh),
                         "{}.fileName".format(vray_mat))
        cmds.connectAttr("{}.instancing".format(vray_mesh),
                         "{}.instancing".format(vray_mat))
        cmds.connectAttr("{}.output".format(vray_mesh),
                         "{}.inMesh".format(mesh_shape))
        cmds.connectAttr("{}.overrideFileName".format(vray_mesh),
                         "{}.overrideFileName".format(vray_mat))
        cmds.connectAttr("{}.currentFrame".format(vray_mesh),
                         "{}.currentFrame".format(vray_mat))

        # Set surface shader input
        cmds.connectAttr("{}.outColor".format(vray_mat),
                         "{}.surfaceShader".format(vray_mat_sg))

        # Connect mesh to shader
        cmds.sets([mesh_shape], addElement=vray_mat_sg)

        group_node = cmds.group(empty=True, name="{}_GRP".format(name))
        mesh_transform = cmds.listRelatives(mesh_shape,
                                            parent=True, fullPath=True)
        cmds.parent(mesh_transform, group_node)
        nodes = [vray_mesh, mesh_shape, vray_mat, vray_mat_sg, group_node]

        # Fix: Force refresh so the mesh shows correctly after creation
        cmds.refresh()
        cmds.setAttr("{}.geomType".format(vray_mesh), 2)

        return nodes, group_node

    def _get_abc(self, version_id):
        # type: (str) -> str
        """Get abc representation file path if present.

        If here is published Alembic (abc) representation published along
        vray proxy, get is file path.

        Args:
            version_id (str): Version hash id.

        Returns:
            str: Path to file.
            None: If abc not found.

        """
        self.log.debug(
            "Looking for abc in published representations of this version.")
        abc_rep = io.find_one(
            {
                "type": "representation",
                "parent": io.ObjectId(version_id),
                "name": "abc"
            })

        if abc_rep:
            self.log.debug("Found, we'll link alembic to vray proxy.")
            file_name = api.get_representation_path(abc_rep)
            self.log.debug("File: {}".format(self.fname))
            return file_name

        return None
