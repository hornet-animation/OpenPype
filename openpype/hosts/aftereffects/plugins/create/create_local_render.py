from openpype.hosts.aftereffects.plugins.create import create_render


class CreateLocalRender(create_render.CreateRender):
    """ Creator to render locally.

        Created only after default render on farm. So family 'render.local' is
        used for backward compatibility.
    """

    name = "renderDefault"
    label = "Render Locally"
    family = "renderLocal"
