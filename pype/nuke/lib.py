import sys
from pprint import pprint
from avalon.vendor.Qt import QtGui
import avalon.nuke

from app.api import Logger

import nuke

log = Logger.getLogger(__name__, "nuke")
self = sys.modules[__name__]
self._project = None


def update_frame_range(start, end, root=None):
    """Set Nuke script start and end frame range

    Args:
        start (float, int): start frame
        end (float, int): end frame
        root (object, Optional): root object from nuke's script

    Returns:
        None

    """

    knobs = {
        "first_frame": start,
        "last_frame": end
    }

    with avalon.nuke.viewer_update_and_undo_stop():
        for key, value in knobs.items():
            if root:
                root[key].setValue(value)
            else:
                nuke.root()[key].setValue(value)


def get_additional_data(container):
    """Get Nuke's related data for the container

    Args:
        container(dict): the container found by the ls() function

    Returns:
        dict
    """

    node = container["_tool"]
    tile_color = node['tile_color'].value()
    if tile_color is None:
        return {}

    hex = '%08x' % tile_color
    rgba = [
        float(int(hex[0:2], 16)) / 255.0,
        float(int(hex[2:4], 16)) / 255.0,
        float(int(hex[4:6], 16)) / 255.0
    ]

    return {"color": QtGui.QColor().fromRgbF(rgba[0], rgba[1], rgba[2])}


def set_viewers_colorspace(viewer):
    assert isinstance(viewer, dict), log.error(
        "set_viewers_colorspace(): argument should be dictionary")

    filter_knobs = [
        "viewerProcess",
        "wipe_position"
    ]
    viewers = [n for n in nuke.allNodes() if n.Class() == 'Viewer']
    erased_viewers = []

    for v in viewers:
        v['viewerProcess'].setValue(str(viewer.viewerProcess))
        if str(viewer.viewerProcess) not in v['viewerProcess'].value():
            copy_inputs = v.dependencies()
            copy_knobs = {k: v[k].value() for k in v.knobs()
                          if k not in filter_knobs}
            pprint(copy_knobs)
            # delete viewer with wrong settings
            erased_viewers.append(v['name'].value())
            nuke.delete(v)

            # create new viewer
            nv = nuke.createNode("Viewer")

            # connect to original inputs
            for i, n in enumerate(copy_inputs):
                nv.setInput(i, n)

            # set coppied knobs
            for k, v in copy_knobs.items():
                print(k, v)
                nv[k].setValue(v)

            # set viewerProcess
            nv['viewerProcess'].setValue(str(viewer.viewerProcess))

    if erased_viewers:
        log.warning(
            "Attention! Viewer nodes {} were erased."
            "It had wrong color profile".format(erased_viewers))


def set_root_colorspace(root_dict):
    assert isinstance(root_dict, dict), log.error(
        "set_root_colorspace(): argument should be dictionary")
    for knob, value in root_dict.items():
        if nuke.root()[knob].value() not in value:
            nuke.root()[knob].setValue(str(value))
            log.info("nuke.root()['{}'] changed to: {}".format(knob, value))


def set_writes_colorspace(write_dict):
    assert isinstance(write_dict, dict), log.error(
        "set_root_colorspace(): argument should be dictionary")
    log.info("set_writes_colorspace(): {}".format(write_dict))


def set_colorspace():
    from pype import api as pype

    nuke_colorspace = getattr(pype.Colorspace, "nuke", None)

    try:
        set_root_colorspace(nuke_colorspace.root)
    except AttributeError:
        log.error(
            "set_colorspace(): missing `root` settings in template")
    try:
        set_viewers_colorspace(nuke_colorspace.viewer)
    except AttributeError:
        log.error(
            "set_colorspace(): missing `viewer` settings in template")
    try:
        set_writes_colorspace(nuke_colorspace.write)
    except AttributeError:
        log.error(
            "set_colorspace(): missing `write` settings in template")

    try:
        for key in nuke_colorspace:
            log.info("{}".format(key))
    except TypeError:
        log.error("Nuke is not in templates! \n\n\n"
                  "contact your supervisor!")
