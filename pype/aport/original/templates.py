from pype import api as pype
from pypeapp import Anatomy, config


log = pype.Logger().get_logger(__name__, "aport")


def get_anatomy(**kwarg):
    return Anatomy()


def get_dataflow(**kwarg):
    log.info(kwarg)
    host = kwarg.get("host", "aport")
    cls = kwarg.get("class", None)
    preset = kwarg.get("preset", None)
    assert any([host, cls]), log.error("aport.templates.get_dataflow():"
                                       "Missing mandatory kwargs `host`, `cls`")

    presets = config.get_init_presets()
    aport_dataflow = getattr(presets["dataflow"], str(host), None)
    aport_dataflow_node = getattr(aport_dataflow.nodes, str(cls), None)
    if preset:
        aport_dataflow_node = getattr(aport_dataflow_node, str(preset), None)

    log.info("Dataflow: {}".format(aport_dataflow_node))
    return aport_dataflow_node


def get_colorspace(**kwarg):
    log.info(kwarg)
    host = kwarg.get("host", "aport")
    cls = kwarg.get("class", None)
    preset = kwarg.get("preset", None)
    assert any([host, cls]), log.error("aport.templates.get_colorspace():"
                                       "Missing mandatory kwargs `host`, `cls`")

    presets = config.get_init_presets()
    aport_colorspace = getattr(presets["colorspace"], str(host), None)
    aport_colorspace_node = getattr(aport_colorspace, str(cls), None)
    if preset:
        aport_colorspace_node = getattr(aport_colorspace_node, str(preset), None)

    log.info("Colorspace: {}".format(aport_colorspace_node))
    return aport_colorspace_node
