from pype.modules.websocket_server import WebSocketServer
"""
    Stub handling connection from server to client.
    Used anywhere solution is calling client methods.
"""
import json
from collections import namedtuple


class PhotoshopClientStub():
    """
        Stub for calling function on client (Photoshop js) side.
        Expects that client is already connected (started when avalon menu
        is opened).
    """

    def __init__(self):
        self.websocketserver = WebSocketServer.get_instance()
        self.client = self.websocketserver.get_client()

    def read(self, layer, layers_meta=None):
        """
            Parses layer metadata from Headline field of active document
        :param layer: <namedTuple Layer("id":XX, "name":"YYY")
        :param layers_meta: full list from Headline (for performance in loops)
        :return:
        """
        if layers_meta is None:
            layers_meta = self._get_layers_metadata()

        return layers_meta.get(str(layer.id))

    def imprint(self, layer, data, all_layers=None, layers_meta=None):
        """
            Save layer metadata to Headline field of active document
        :param layer: <namedTuple> Layer("id": XXX, "name":'YYY')
        :param data: <string> json representation for single layer
        :param all_layers: <list of namedTuples> - for performance, could be
                injected for usage in loop, if not, single call will be
                triggered
        :return: None
        """
        if not layers_meta:
            layers_meta = self._get_layers_metadata()
        # json.dumps writes integer values in a dictionary to string, so
        # anticipating it here.
        if str(layer.id) in layers_meta and layers_meta[str(layer.id)]:
            layers_meta[str(layer.id)].update(data)
        else:
            layers_meta[str(layer.id)] = data

        # Ensure only valid ids are stored.
        if not all_layers:
            all_layers = self.get_layers()
        layer_ids = [layer.id for layer in all_layers]
        cleaned_data = {}

        for id in layers_meta:
            if int(id) in layer_ids:
                cleaned_data[id] = layers_meta[id]

        payload = json.dumps(cleaned_data, indent=4)

        self.websocketserver.call(self.client.call
                                  ('Photoshop.imprint', payload=payload)
                                  )

    def get_layers(self):
        """
            Returns JSON document with all(?) layers in active document.

        :return: <list of namedtuples>
                    Format of tuple: { 'id':'123',
                                     'name': 'My Layer 1',
                                     'type': 'GUIDE'|'FG'|'BG'|'OBJ'
                                     'visible': 'true'|'false'
        """
        res = self.websocketserver.call(self.client.call
                                        ('Photoshop.get_layers'))

        return self._to_records(res)

    def get_layers_in_layers(self, layers):
        """
            Return all layers that belong to layers (might be groups).
        :param layers:
        :return: <list of nametduples>
        """
        all_layers = self.get_layers()
        print("get_layers_in_layers {}".format(layers))
        print("get_layers_in_layers len {}".format(len(layers)))
        print("get_layers_in_layers type {}".format(type(layers)))
        ret = []
        layer_ids = [lay.id for lay in layers]
        layer_group_ids = [ll.groupId for ll in layers if ll.group]
        for layer in all_layers:
            if layer.groupId in layer_group_ids:  # all from group
                ret.append(layer)
            if layer.id in layer_ids:
                ret.append(layer)

        return ret

    def group_selected_layers(self):
        """
            Group selected layers into new layer
        :return:
        """
        self.websocketserver.call(self.client.call
                                  ('Photoshop.group_selected_layers'))

    def get_selected_layers(self):
        """
            Get a list of actually selected layers
        :return: <list of Layer('id':XX, 'name':"YYY")>
        """
        res = self.websocketserver.call(self.client.call
                                        ('Photoshop.get_selected_layers'))
        return self._to_records(res)

    def select_layers(self, layers):
        """
            Selecte specified layers in Photoshop
        :param layers: <list of Layer('id':XX, 'name':"YYY")>
        :return: None
        """
        layer_ids = [layer.id for layer in layers]

        self.websocketserver.call(self.client.call
                                  ('Photoshop.get_layers',
                                   layers=layer_ids)
                                  )

    def get_active_document_full_name(self):
        """
            Returns full name with path of active document via ws call
        :return: <string> full path with name
        """
        res = self.websocketserver.call(
              self.client.call('Photoshop.get_active_document_full_name'))

        return res

    def get_active_document_name(self):
        """
            Returns just a name of active document via ws call
        :return: <string> file name
        """
        res = self.websocketserver.call(self.client.call
                                        ('Photoshop.get_active_document_name'))

        return res

    def save(self):
        """
            Saves active document
        :return: None
        """
        self.websocketserver.call(self.client.call
                                  ('Photoshop.save'))

    def saveAs(self, image_path, ext, as_copy):
        """
            Saves active document to psd (copy) or png or jpg
        :param image_path: <string> full local path
        :param ext: <string psd|jpg|png>
        :param as_copy: <boolean>
        :return: None
        """
        self.websocketserver.call(self.client.call
                                  ('Photoshop.saveAs',
                                   image_path=image_path,
                                   ext=ext,
                                   as_copy=as_copy))

    def set_visible(self, layer_id, visibility):
        """
            Set layer with 'layer_id' to 'visibility'
        :param layer_id: <int>
        :param visibility: <true - set visible, false - hide>
        :return: None
        """
        self.websocketserver.call(self.client.call
                                  ('Photoshop.set_visible',
                                   layer_id=layer_id,
                                   visibility=visibility))

    def _get_layers_metadata(self):
        """
            Reads layers metadata from Headline from active document in PS.
            (Headline accessible by File > File Info)
        :return: <string> - json documents
        """
        layers_data = {}
        res = self.websocketserver.call(self.client.call('Photoshop.read'))
        try:
            layers_data = json.loads(res)
        except json.decoder.JSONDecodeError:
            pass
        return layers_data

    def import_smart_object(self, path):
        """
            Import the file at `path` as a smart object to active document.

        Args:
            path (str): File path to import.
        """

    def replace_smart_object(self, layer, path):
        """
            Replace the smart object `layer` with file at `path`

        Args:
            layer (namedTuple): Layer("id":XX, "name":"YY"..).
            path (str): File to import.
        """
        self.websocketserver.call(self.client.call
                                  ('Photoshop.replace_smart_object',
                                   layer=layer,
                                   path=path))

    def close(self):
        self.client.close()

    def _to_records(self, res):
        """
            Converts string json representation into list of named tuples for
            dot notation access to work.
        :return: <list of named tuples>
        :param res: <string> - json representation
        """
        try:
            layers_data = json.loads(res)
        except json.decoder.JSONDecodeError:
            raise ValueError("Received broken JSON {}".format(res))
        ret = []
        # convert to namedtuple to use dot donation
        for d in layers_data:
            ret.append(namedtuple('Layer', d.keys())(*d.values()))
        return ret




