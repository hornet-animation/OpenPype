import os
import sys
import re
import copy
import json
import collections
from queue import Queue
sys.path.append(r"C:\Users\Public\pype_env2\Lib\site-packages")
from PIL import Image, ImageFont, ImageDraw, ImageEnhance, ImageColor
from uuid import uuid4


class BaseObj:
    """Base Object for slates."""

    obj_type = None
    available_parents = []
    all_style_keys = [
        "font-family", "font-size", "font-color", "font-bold", "font-italic",
        "bg-color", "bg-alter-color",
        "alignment-horizontal", "alignment-vertical",
        "padding", "padding-left", "padding-right",
        "padding-top", "padding-bottom",
        "margin", "margin-left", "margin-right",
        "margin-top", "margin-bottom", "width", "height",
        "fill"
    ]

    def __init__(self, parent, style={}, name=None, pos_x=None, pos_y=None):
        if not self.obj_type:
            raise NotImplementedError(
                "Class don't have set object type <{}>".format(
                    self.__class__.__name__
                )
            )

        parent_obj_type = None
        if parent:
            parent_obj_type = parent.obj_type

        if parent_obj_type not in self.available_parents:
            expected_parents = ", ".join(self.available_parents)
            raise Exception((
                "Invalid parent <{}> for <{}>. Expected <{}>"
            ).format(
                parent.__class__.__name__, self.obj_type, expected_parents
            ))

        self.parent = parent
        self._style = style

        self.id = uuid4()
        self.name = name
        self.items = {}

        self._pos_x = pos_x or 0
        self._pos_y = pos_y or 0

    @property
    def main_style(self):
        default_style_v1 = {
            "*": {
                "font-family": "arial",
                "font-size": 26,
                "font-color": "#ffffff",
                "font-bold": False,
                "font-italic": False,
                "bg-color": "#0077ff",
                "bg-alter-color": "#0055dd",
                "alignment-horizontal": "center",
                "alignment-vertical": "bottom",
                "padding": 0,
                "margin": 0,
            },
            "main_frame": {
                "padding": 0,
                "margin": 0
            },
            "layer": {
                "padding": 0,
                "margin": 0
            },
            "image": {
                "padding": 0,
                "margin": 0
            },
            "text": {
                "padding": 0,
                "margin": 0
            },
            "table": {
                "padding": 0,
                "margin": 0
            },
            "table-item": {
                "alignment-horizontal": "right",
                "padding": 0,
                "margin": 0
            },
            "__not_implemented__": {
                "table-item-col-0": {},
                "#MyName": {}
            }
        }
        return default_style_v1

    def height(self):
        raise NotImplementedError(
            "Attribute `height` is not implemented for <{}>".format(
                self.__clas__.__name__
            )
        )

    def width(self):
        raise NotImplementedError(
            "Attribute `width` is not implemented for <{}>".format(
                self.__clas__.__name__
            )
        )

    @property
    def full_style(self):
        if self.parent is not None:
            style = dict(val for val in self.parent.full_style.items())
        else:
            style = self.main_style

        for key, value in self._style.items():
            if key in self.all_style_keys:
                # TODO which variant is right?
                style[self.obj_type][key] = value
                # style["*"][key] = value
            else:
                if key not in style:
                    style[key] = {}

                if isinstance(style[key], dict):
                    style[key].update(value)
                else:
                    style[key] = value

        return style

    def get_style_for_obj_type(self, obj_type, style=None):
        if not style:
            style = copy.deepcopy(self.full_style)

        base = style.get("*") or {}
        obj_specific = style.get(obj_type) or {}
        name_specific = {}
        if self.name:
            name = str(self.name)
            if not name.startswith("#"):
                name += "#"
            name_specific = style.get(name) or {}


        if obj_type == "table-item":
            col_regex = r"table-item-col\[([\d\-, ]+)*\]"
            row_regex = r"table-item-row\[([\d\-, ]+)*\]"
            field_regex = (
                r"table-item-field\[(([ ]+)?\d+([ ]+)?:([ ]+)?\d+([ ]+)?)*\]"
            )
            # STRICT field regex (not allowed spaces)
            # fild_regex = r"table-item-field\[(\d+:\d+)*\]"

            def get_indexes_from_regex_match(result, field=False):
                group = result.group(1)
                indexes = []
                if field:
                    return [
                        int(part.strip()) for part in group.strip().split(":")
                    ]

                parts = group.strip().split(",")
                for part in parts:
                    part = part.strip()
                    if "-" not in part:
                        indexes.append(int(part))
                        continue

                    sub_parts = [
                        int(sub.strip()) for sub in part.split("-")
                    ]
                    if len(sub_parts) != 2:
                        # TODO logging
                        print("invalid range '{}'".format(part))
                        continue

                    for idx in range(sub_parts[0], sub_parts[1]+1):
                        indexes.append(idx)
                return indexes

            for key, value in style.items():
                if not key.startswith(obj_type):
                    continue

                result = re.search(col_regex, key)
                if result:
                    indexes = get_indexes_from_regex_match(result)
                    if self.col_idx in indexes:
                        obj_specific.update(value)
                    continue

                result = re.search(row_regex, key)
                if result:
                    indexes = get_indexes_from_regex_match(result)
                    if self.row_idx in indexes:
                        obj_specific.update(value)
                    continue

                result = re.search(field_regex, key)
                if result:
                    col_idx, row_idx = get_indexes_from_regex_match(
                        result, True
                    )
                    if self.col_idx == col_idx and self.row_idx == row_idx:
                        obj_specific.update(value)

        output = {}
        output.update(base)
        output.update(obj_specific)
        output.update(name_specific)

        return output

    @property
    def style(self):
        return self.get_style_for_obj_type(self.obj_type)

    @property
    def item_pos_x(self):
        if self.parent.obj_type == "main_frame":
            return int(self._pos_x)
        return 0

    @property
    def item_pos_y(self):
        if self.parent.obj_type == "main_frame":
            return int(self._pos_y)
        return 0

    @property
    def content_pos_x(self):
        pos_x = self.item_pos_x
        margin = self.style["margin"]
        margin_left = self.style.get("margin-left") or margin

        pos_x += margin_left

        return pos_x

    @property
    def content_pos_y(self):
        pos_y = self.item_pos_y
        margin = self.style["margin"]
        margin_top = self.style.get("margin-top") or margin
        return pos_y + margin_top

    @property
    def value_pos_x(self):
        pos_x = int(self.content_pos_x)
        padding = self.style["padding"]
        padding_left = self.style.get("padding-left")
        if padding_left is None:
            padding_left = padding

        pos_x += padding_left

        return pos_x

    @property
    def value_pos_y(self):
        pos_y = int(self.content_pos_y)
        padding = self.style["padding"]
        padding_top = self.style.get("padding-top")
        if padding_top is None:
            padding_top = padding

        pos_y += padding_top

        return pos_y

    @property
    def value_pos_start(self):
        return (self.value_pos_x, self.value_pos_y)

    @property
    def value_pos_end(self):
        pos_x, pos_y = self.value_pos_start
        pos_x += self.width()
        pos_y += self.height()
        return (pos_x, pos_y)

    @property
    def content_pos_start(self):
        return (self.content_pos_x, self.content_pos_y)

    @property
    def content_pos_end(self):
        pos_x, pos_y = self.content_pos_start
        pos_x += self.content_width()
        pos_y += self.content_height()
        return (pos_x, pos_y)

    def value_width(self):
        raise NotImplementedError(
            "Attribute <content_width> is not implemented <{}>".format(
                self.__class__.__name__
            )
        )

    def value_height(self):
        raise NotImplementedError(
            "Attribute <content_width> is not implemented for <{}>".format(
                self.__class__.__name__
            )
        )

    def content_width(self):
        width = self.value_width()
        padding = self.style["padding"]
        padding_left = self.style.get("padding-left")
        if padding_left is None:
            padding_left = padding

        padding_right = self.style.get("padding-right")
        if padding_right is None:
            padding_right = padding

        return width + padding_left + padding_right

    def content_height(self):
        height = self.value_height()
        padding = self.style["padding"]
        padding_top = self.style.get("padding-top")
        if padding_top is None:
            padding_top = padding

        padding_bottom = self.style.get("padding-bottom")
        if padding_bottom is None:
            padding_bottom = padding

        return height + padding_top + padding_bottom

    def width(self):
        width = self.content_width()

        margin = self.style["margin"]
        margin_left = self.style.get("margin-left") or margin
        margin_right = self.style.get("margin-right") or margin

        return width + margin_left + margin_right

    def height(self):
        height = self.content_height()

        margin = self.style["margin"]
        margin_top = self.style.get("margin-top") or margin
        margin_bottom = self.style.get("margin-bottom") or margin

        return height + margin_bottom + margin_top

    def add_item(self, item):
        self.items[item.id] = item

    def reset(self):
        for item in self.items.values():
            item.reset()


class MainFrame(BaseObj):

    obj_type = "main_frame"
    available_parents = [None]

    def __init__(self, width, height, destination_path=None, *args, **kwargs):
        kwargs["parent"] = None
        super(MainFrame, self).__init__(*args, **kwargs)
        self._width = width
        self._height = height
        self.dst_path = destination_path

    def value_width(self):
        width = 0
        for item in self.items.values():
            width += item.width()
        return width

    def value_height(self):
        height = 0
        for item in self.items.values():
            height += item.height()
        return height

    def width(self):
        return self._width

    def height(self):
        return self._height

    def draw(self, path=None):
        if not path:
            path = self.dst_path

        if not path:
            raise TypeError((
                "draw() missing 1 required positional argument: 'path'"
                " if 'destination_path is not specified'"
            ))

        dir_path = os.path.dirname(path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        bg_color = self.style["bg-color"]
        image = Image.new("RGB", (self.width(), self.height()), color=bg_color)
        drawer = ImageDraw.Draw(image)
        for item in self.items.values():
            item.draw(image, drawer)

        image.save(path)
        self.reset()


class Layer(BaseObj):
    obj_type = "layer"
    available_parents = ["main_frame", "layer"]

    # Direction can be 0=vertical/ 1=horizontal
    def __init__(self, direction=0, *args, **kwargs):
        super(Layer, self).__init__(*args, **kwargs)
        self._direction = direction

    @property
    def item_pos_x(self):
        if self.parent.obj_type == self.obj_type:
            pos_x = self.parent.child_pos_x(self.id)
        elif self.parent.obj_type == "main_frame":
            pos_x = self._pos_x
        else:
            pos_x = self.parent.value_pos_x
        return int(pos_x)

    @property
    def item_pos_y(self):
        if self.parent.obj_type == self.obj_type:
            pos_y = self.parent.child_pos_y(self.id)
        elif self.parent.obj_type == "main_frame":
            pos_y = self._pos_y
        else:
            pos_y = self.parent.value_pos_y
        return int(pos_y)

    @property
    def direction(self):
        if self._direction not in (0, 1):
            print(
                "Direction must be 0 or 1 (0 is horizontal / 1 is vertical)!"
            )
            return 0
        return self._direction

    def child_pos_x(self, item_id):
        pos_x = self.value_pos_x
        alignment_hor = self.style["alignment-horizontal"].lower()

        item = None
        for id, _item in self.items.items():
            if item_id == id:
                item = _item
                break

        if self.direction == 1:
            for id, _item in self.items.items():
                if item_id == id:
                    break

                pos_x += _item.width()
                if _item.obj_type != "image":
                    pos_x += 1

        else:
            if alignment_hor in ["center", "centre"]:
                pos_x += (self.content_width() - item.content_width()) / 2

            elif alignment_hor == "right":
                pos_x += self.content_width() - item.content_width()

            else:
                margin = self.style["margin"]
                margin_left = self.style.get("margin-left") or margin
                pos_x += margin_left

        return int(pos_x)

    def child_pos_y(self, item_id):
        pos_y = self.value_pos_y
        alignment_ver = self.style["alignment-horizontal"].lower()

        item = None
        for id, _item in self.items.items():
            if item_id == id:
                item = _item
                break

        if self.direction != 1:
            for id, item in self.items.items():
                if item_id == id:
                    break
                pos_y += item.height()
                if item.obj_type != "image":
                    pos_y += 1

        else:
            if alignment_ver in ["center", "centre"]:
                pos_y += (self.content_height() - item.content_height()) / 2

            elif alignment_ver == "bottom":
                pos_y += self.content_height() - item.content_height()

            else:
                margin = self.style["margin"]
                margin_top = self.style.get("margin-top") or margin
                pos_y += margin_top
        return int(pos_y)

    def value_height(self):
        height = 0
        for item in self.items.values():
            if self.direction == 0:
                if height > item.height():
                    continue
                # times 1 because won't get object pointer but number
                height += item.height()
            else:
                height = item.height()

        # TODO this is not right
        min_height = self.style.get("min-height")
        if min_height and min_height > height:
            return min_height
        return height

    def value_width(self):
        width = 0
        for item in self.items.values():
            if self.direction == 1:
                if width > item.width():
                    continue
                # times 1 because won't get object pointer but number
                width = item.width()
            else:
                width += item.width()

        min_width = self.style.get("min-width")
        if min_width and min_width > width:
            return min_width
        return width

    def draw(self, image, drawer):
        for item in self.items.values():
            item.draw(image, drawer)


class BaseItem(BaseObj):
    available_parents = ["main_frame", "layer"]


    @property
    def item_pos_x(self):
        if self.parent.obj_type == "main_frame":
            return self._pos_x
        return self.parent.child_pos_x(self.id)

    @property
    def item_pos_y(self):
        if self.parent.obj_type == "main_frame":
            return self._pos_y
        return self.parent.child_pos_y(self.id)

    def add_item(self, *args, **kwargs):
        raise Exception("Can't add item to an item, use layers instead.")

    def draw(self, image, drawer):
        raise NotImplementedError(
            "Method `draw` is not implemented for <{}>".format(
                self.__clas__.__name__
            )
        )


class ItemImage(BaseItem):
    obj_type = "image"

    def __init__(self, image_path, *args, **kwargs):
        super(ItemImage, self).__init__(*args, **kwargs)
        self.image_path = image_path

    def draw(self, image, drawer):
        source_image = Image.open(os.path.normpath(self.image_path))
        paste_image = source_image.resize(
            (self.value_width(), self.value_height()),
            Image.ANTIALIAS
        )
        image.paste(
            paste_image,
            (self.value_pos_x, self.value_pos_y)
        )

    def value_width(self):
        return int(self.style["width"])

    def value_height(self):
        return int(self.style["height"])


class ItemRectangle(BaseItem):
    obj_type = "rectangle"

    def draw(self, image, drawer):
        bg_color = self.style["bg-color"]
        fill = self.style.get("fill", False)
        kwargs = {}
        if fill:
            kwargs["fill"] = bg_color
        else:
            kwargs["outline"] = bg_color

        start_pos_x = self.value_pos_x
        start_pos_y = self.value_pos_y
        end_pos_x = start_pos_x + self.value_width()
        end_pos_y = start_pos_y + self.value_height()
        drawer.rectangle(
            (
                (start_pos_x, start_pos_y),
                (end_pos_x, end_pos_y)
            ),
            **kwargs
        )

    def value_width(self):
        return int(self.style["width"])

    def value_height(self):
        return int(self.style["height"])


class ItemPlaceHolder(BaseItem):
    obj_type = "placeholder"

    def __init__(self, image_path, *args, **kwargs):
        self.image_path = image_path
        super(ItemPlaceHolder, self).__init__(*args, **kwargs)

    def fill_data_format(self):
        if re.match(self.fill_data_regex, self.image_path):
            self.image_path = self.image_path.format(**self.fill_data)

    def draw(self, image, drawer):
        bg_color = self.style["bg-color"]

        kwargs = {}
        if bg_color != "tranparent":
            kwargs["fill"] = bg_color

        start_pos_x = self.value_pos_x
        start_pos_y = self.value_pos_y
        end_pos_x = start_pos_x + self.value_width()
        end_pos_y = start_pos_y + self.value_height()

        drawer.rectangle(
            (
                (start_pos_x, start_pos_y),
                (end_pos_x, end_pos_y)
            ),
            **kwargs
        )

    def value_width(self):
        return int(self.style["width"])

    def value_height(self):
        return int(self.style["height"])

    def collect_data(self):
        return {
            "pos_x": self.value_pos_x,
            "pos_y": self.value_pos_y,
            "width": self.value_width(),
            "height": self.value_height(),
            "path": self.image_path
        }


class ItemText(BaseItem):
    obj_type = "text"

    def __init__(self, value, *args, **kwargs):
        super(ItemText, self).__init__(*args, **kwargs)
        self.value = value

    def draw(self, image, drawer):
        bg_color = self.style["bg-color"]
        if bg_color and bg_color.lower() != "transparent":
            # TODO border outline styles
            drawer.rectangle(
                (self.content_pos_start, self.content_pos_end),
                fill=bg_color,
                outline=None
            )

        font_color = self.style["font-color"]
        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        drawer.text(
            self.value_pos_start,
            self.value,
            font=font,
            fill=font_color
        )

    def value_width(self):
        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        width = font.getsize(self.value)[0]
        return int(width)

    def value_height(self):
        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        height = font.getsize(self.value)[1]
        return int(height)


class ItemTable(BaseItem):

    obj_type = "table"

    def __init__(self, values, use_alternate_color=False, *args, **kwargs):
        super(ItemTable, self).__init__(*args, **kwargs)
        self.size_values = None
        self.values_by_cords = None

        self.prepare_values(values)
        self.calculate_sizes()

        self.use_alternate_color = use_alternate_color

    def prepare_values(self, _values):
        values = []
        values_by_cords = []
        row_count = 0
        col_count = 0
        for row in _values:
            row_count += 1
            if len(row) > col_count:
                col_count = len(row)

        for row_idx in range(row_count):
            values_by_cords.append([])
            for col_idx in range(col_count):
                values_by_cords[row_idx].append([])
                if col_idx <= len(_values[row_idx]) - 1:
                    col = _values[row_idx][col_idx]
                else:
                    col = ""

                col_item = TableField(row_idx, col_idx, col, parent=self)
                values_by_cords[row_idx][col_idx] = col_item
                values.append(col_item)

        self.values = values
        self.values_by_cords = values_by_cords

    def calculate_sizes(self):
        row_heights = []
        col_widths = []
        for row_idx, row in enumerate(self.values_by_cords):
            row_heights.append(0)
            for col_idx, col_item in enumerate(row):
                if len(col_widths) < col_idx + 1:
                    col_widths.append(0)

                _width = col_widths[col_idx]
                item_width = col_item.width()
                if _width < item_width:
                    col_widths[col_idx] = item_width

                _height = row_heights[row_idx]
                item_height = col_item.height()
                if _height < item_height:
                    row_heights[row_idx] = item_height

        self.size_values = (row_heights, col_widths)

    def draw(self, image, drawer):
        bg_color = self.style["bg-color"]
        if bg_color and bg_color.lower() != "transparent":
            # TODO border outline styles
            drawer.rectangle(
                (self.content_pos_start, self.content_pos_end),
                fill=bg_color,
                outline=None
            )

        for value in self.values:
            value.draw(image, drawer)

    def value_width(self):
        row_heights, col_widths = self.size_values
        width = 0
        for _width in col_widths:
            width += _width

        if width != 0:
            width -= 1
        return width

    def value_height(self):
        row_heights, col_widths = self.size_values
        height = 0
        for _height in row_heights:
            height += _height

        if height != 0:
            height -= 1
        return height

    def content_pos_info_by_cord(self, row_idx, col_idx):
        row_heights, col_widths = self.size_values
        pos_x = int(self.value_pos_x)
        pos_y = int(self.value_pos_y)
        width = 0
        height = 0
        for idx, value in enumerate(col_widths):
            if col_idx == idx:
                width = value
                break
            pos_x += value

        for idx, value in enumerate(row_heights):
            if row_idx == idx:
                height = value
                break
            pos_y += value

        return (pos_x, pos_y, width, height)


class TableField(BaseItem):

    obj_type = "table-item"
    available_parents = ["table"]
    ellide_text = "..."

    def __init__(self, row_idx, col_idx, value, *args, **kwargs):
        super(TableField, self).__init__(*args, **kwargs)
        self.row_idx = row_idx
        self.col_idx = col_idx

        self.orig_value = value

        max_width = self.style.get("max-width")
        max_width = self.style.get("width") or max_width
        if max_width:
            value = self.recalculate_by_width(value, max_width)

        self.value = value

    def recalculate_by_width(self, value, max_width):
        padding = self.style["padding"]
        padding_left = self.style.get("padding-left")
        if padding_left is None:
            padding_left = padding

        padding_right = self.style.get("padding-right")
        if padding_right is None:
            padding_right = padding

        max_width -= (padding_left + padding_right)

        if not value:
            return ""

        word_wrap = self.style.get("word-wrap")
        ellide = self.style.get("ellide")
        max_lines = self.style.get("max-lines")

        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        val_width = font.getsize(value)[0]
        if val_width <= max_width:
            return value

        if not ellide and not word_wrap:
            # TODO logging
            print((
                "Can't draw text because is too long with"
                " `word-wrap` and `ellide` turned off"
            ))
            return ""

        elif ellide and not word_wrap:
            max_lines = 1

        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )

        words = [word for word in value.split()]
        words_len = len(words)
        lines = []
        last_index = 0
        while True:
            line = ""
            for idx in range(last_index, words_len):
                _word = words[idx]
                _line = " ".join([line, _word])
                _line_width = font.getsize(_line)[0]
                if _line_width > max_width:
                    break
                line = _line
                last_index = idx

            if line:
                lines.append(line)

            if last_index == words_len - 1:
                break

            elif last_index == 0:
                if ellide:
                    line = ""
                    for idx, char in enumerate(words[idx]):
                        _line = line + char + self.ellide_text
                        _line_width = font.getsize(_line)[0]
                        if _line_width > max_width:
                            if idx == 0:
                                line = _line
                            break
                        line = _line

                    lines.append(line)
                # TODO logging
                print("Font size is too big.")
                break

        output = ""
        if not lines:
            return output

        if max_lines and len(lines) > max_lines:
            lines = [lines[idx] for idx in range(max_lines)]
            if not ellide:
                return "\n".join(lines)

            last_line = lines[-1]
            last_line_width = font.getsize(last_line + self.ellide_text)[0]
            if last_line_width <= max_width:
                lines[-1] += self.ellide_text
                return "\n".join([line for line in lines])

            last_line_words = last_line.split()
            if len(last_line_words) == 1:
                if max_lines > 1:
                    lines[-1] = self.ellide_text
                    return "\n".join([line for line in lines])

                _line = ""
                for idx, char in enumerate(last_line):
                    _line = line + char + self.ellide_text
                    _line_width = font.getsize(_line)[0]
                    if _line_width > max_width:
                        if idx == 0:
                            line = _line
                        break
                    line = _line
                lines[-1] = line
                return "\n".join([line for line in lines])

        return "\n".join([line for line in lines])


    def value_width(self):
        if not self.value:
            return 0

        width = self.style.get("width")
        if width:
            return int(width)

        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        width = font.getsize_multiline(self.value)[0] + 1

        min_width = self.style.get("min-height")
        if min_width and min_width > width:
            width = min_width

        return int(width)

    def value_height(self):
        if not self.value:
            return 0

        height = self.style.get("height")
        if height:
            return int(height)

        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        height = font.getsize_multiline(self.value)[1] + 1

        min_height = self.style.get("min-height")
        if min_height and min_height > height:
            height = min_height

        return int(height)

    @property
    def item_pos_x(self):
        pos_x, pos_y, width, height = (
            self.parent.content_pos_info_by_cord(self.row_idx, self.col_idx)
        )
        return pos_x

    @property
    def item_pos_y(self):
        pos_x, pos_y, width, height = (
            self.parent.content_pos_info_by_cord(self.row_idx, self.col_idx)
        )
        return pos_y

    @property
    def value_pos_x(self):
        pos_x, pos_y, width, height = (
            self.parent.content_pos_info_by_cord(self.row_idx, self.col_idx)
        )
        alignment_hor = self.style["alignment-horizontal"].lower()
        if alignment_hor in ["center", "centre"]:
            pos_x += (width - self.value_width()) / 2

        elif alignment_hor == "right":
            pos_x += width - self.value_width()

        else:
            padding = self.style["padding"]
            padding_left = self.style.get("padding-left") or padding
            pos_x += padding_left

        return int(pos_x)

    @property
    def value_pos_y(self):
        pos_x, pos_y, width, height = (
            self.parent.content_pos_info_by_cord(self.row_idx, self.col_idx)
        )

        alignment_ver = self.style["alignment-vertical"].lower()
        if alignment_ver in ["center", "centre"]:
            pos_y += (height - self.value_height()) / 2

        elif alignment_ver == "bottom":
            pos_y += height - self.value_height()

        else:
            padding = self.style["padding"]
            padding_top = self.style.get("padding-top") or padding
            pos_y += padding_top

        return int(pos_y)

    def draw(self, image, drawer):
        pos_x, pos_y, width, height = (
            self.parent.content_pos_info_by_cord(self.row_idx, self.col_idx)
        )
        pos_start = (pos_x, pos_y)
        pos_end = (pos_x + width, pos_y + height)
        bg_color = self.style["bg-color"]
        if self.parent.use_alternate_color and (self.row_idx % 2) == 1:
            bg_color = self.style["bg-alter-color"]

        if bg_color and bg_color.lower() != "transparent":
            # TODO border outline styles
            drawer.rectangle(
                (pos_start, pos_end),
                fill=bg_color,
                outline=None
            )

        font_color = self.style["font-color"]
        font_family = self.style["font-family"]
        font_size = self.style["font-size"]
        font_bold = self.style.get("font-bold", False)
        font_italic = self.style.get("font-italic", False)

        font = FontFactory.get_font(
            font_family, font_size, font_italic, font_bold
        )
        drawer.text(
            self.value_pos_start,
            self.value,
            font=font,
            fill=font_color
        )


class FontFactory:
    fonts = None
    default = None

    @classmethod
    def get_font(cls, family, font_size=None, italic=False, bold=False):
        if cls.fonts is None:
            cls.load_fonts()

        styles = []
        if bold:
            styles.append("Bold")

        if italic:
            styles.append("Italic")

        if not styles:
            styles.append("Regular")

        style = " ".join(styles)
        family = family.lower()
        family_styles = cls.fonts.get(family)
        if not family_styles:
            return cls.default

        font = family_styles.get(style)
        if font:
            if font_size:
                font = font.font_variant(size=font_size)
            return font

        # Return first found
        for font in family_styles:
            if font_size:
                font = font.font_variant(size=font_size)
            return font

        return cls.default

    @classmethod
    def load_fonts(cls):

        cls.default = ImageFont.load_default()

        available_font_ext = [".ttf", ".ttc"]
        dirs = []
        if sys.platform == "win32":
            # check the windows font repository
            # NOTE: must use uppercase WINDIR, to work around bugs in
            # 1.5.2's os.environ.get()
            windir = os.environ.get("WINDIR")
            if windir:
                dirs.append(os.path.join(windir, "fonts"))

        elif sys.platform in ("linux", "linux2"):
            lindirs = os.environ.get("XDG_DATA_DIRS", "")
            if not lindirs:
                # According to the freedesktop spec, XDG_DATA_DIRS should
                # default to /usr/share
                lindirs = "/usr/share"
            dirs += [
                os.path.join(lindir, "fonts") for lindir in lindirs.split(":")
            ]

        elif sys.platform == "darwin":
            dirs += [
                "/Library/Fonts",
                "/System/Library/Fonts",
                os.path.expanduser("~/Library/Fonts")
            ]

        available_fonts = collections.defaultdict(dict)
        for directory in dirs:
            for walkroot, walkdir, walkfilenames in os.walk(directory):
                for walkfilename in walkfilenames:
                    ext = os.path.splitext(walkfilename)[1]
                    if ext.lower() not in available_font_ext:
                        continue

                    fontpath = os.path.join(walkroot, walkfilename)
                    font_obj = ImageFont.truetype(fontpath)
                    family = font_obj.font.family.lower()
                    style = font_obj.font.style
                    available_fonts[family][style] = font_obj

        cls.fonts = available_fonts

def main():
    cur_folder = os.path.dirname(os.path.abspath(__file__))
    input_json = os.path.join(cur_folder, "netflix_v01.1.json")
    with open(input_json) as json_file:
        slate_data = json.load(json_file)

    width = slate_data["width"]
    height = slate_data["height"]
    style = slate_data.get("style") or {}
    dst_path = slate_data.get("destination_path")
    main = MainFrame(width, height, destination_path=dst_path, style=style)

    load_queue = Queue()
    for item in slate_data["items"]:
        load_queue.put((item, main))

    while not load_queue.empty():
        item_data, parent = load_queue.get()

        item_type = item_data["type"].lower()
        item_style = item_data.get("style", {})
        item_name = item_data.get("name")

        pos_x = None
        pos_y = None
        if parent.obj_type == "main_frame":
            pos_x = item_data.get("pos_x", {})
            pos_y = item_data.get("pos_y", {})

        kwargs = {
            "parent": parent,
            "style": item_style,
            "name": item_name,
            "pos_x": pos_x,
            "pos_y": pos_y
        }

        item_obj = None
        if item_type == "layer":
            direction = item_data.get("direction", 0)
            item_obj = Layer(direction, **kwargs)
            for item in item_data.get("items", []):
                load_queue.put((item, item_obj))

        elif item_type == "table":
            use_alternate_color = item_data.get("use_alternate_color", False)
            values = item_data.get("values") or []
            item_obj = ItemTable(values, use_alternate_color, **kwargs)

        elif item_type == "image":
            path = item_data["path"]
            item_obj = ItemImage(path, **kwargs)

        elif item_type == "rectangle":
            item_obj = ItemRectangle(**kwargs)

        if not item_obj:
            # TODO logging
            print(
                "Slate item not implemented <{}> - skipping".format(item_type)
            )
            continue

        parent.add_item(item_obj)

    main.draw()
    print("*** Drawing is done")


if __name__ == "__main__":
    main()
