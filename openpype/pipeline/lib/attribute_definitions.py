import re
import collections
import uuid
from abc import ABCMeta, abstractmethod
import six


class AbstractAttrDefMeta(ABCMeta):
    """Meta class to validate existence of 'key' attribute.

    Each object of `AbtractAttrDef` mus have defined 'key' attribute.
    """
    def __call__(self, *args, **kwargs):
        obj = super(AbstractAttrDefMeta, self).__call__(*args, **kwargs)
        init_class = getattr(obj, "__init__class__", None)
        if init_class is not AbtractAttrDef:
            raise TypeError("{} super was not called in __init__.".format(
                type(obj)
            ))
        return obj


@six.add_metaclass(AbstractAttrDefMeta)
class AbtractAttrDef:
    """Abstraction of attribute definiton.

    Each attribute definition must have implemented validation and
    conversion method.

    Attribute definition should have ability to return "default" value. That
    can be based on passed data into `__init__` so is not abstracted to
    attribute.

    QUESTION:
    How to force to set `key` attribute?

    Args:
        key(str): Under which key will be attribute value stored.
        label(str): Attribute label.
        tooltip(str): Attribute tooltip.
    """

    def __init__(self, key, label=None, tooltip=None):
        self.key = key
        self.label = label
        self.tooltip = tooltip
        self._id = uuid.uuid4()

        self.__init__class__ = AbtractAttrDef

    @property
    def id(self):
        return self._id

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.key == other.key

    @abstractmethod
    def convert_value(self, value):
        """Convert value to a valid one.

        Convert passed value to a valid type. Use default if value can't be
        converted.
        """
        pass


class NumberDef(AbtractAttrDef):
    """Number definition.

    Number can have defined minimum/maximum value and decimal points. Value
    is integer if decimals are 0.

    Args:
        minimum(int, float): Minimum possible value.
        maximum(int, float): Maximum possible value.
        decimals(int): Maximum decimal points of value.
        default(int, float): Default value for conversion.
    """

    def __init__(
        self, key, minimum=None, maximum=None, decimals=None, default=None,
        **kwargs
    ):
        super(NumberDef, self).__init__(key, **kwargs)

        minimum = 0 if minimum is None else minimum
        maximum = 999999 if maximum is None else maximum
        # Swap min/max when are passed in opposited order
        if minimum > maximum:
            maximum, minimum = minimum, maximum

        if default is None:
            default = 0

        elif not isinstance(default, (int, float)):
            raise TypeError((
                "'default' argument must be 'int' or 'float', not '{}'"
            ).format(type(default)))

        # Fix default value by mim/max values
        if default < minimum:
            default = minimum

        elif default > maximum:
            default = maximum

        self.minimum = minimum
        self.maximum = maximum
        self.default = default
        self.decimals = 0 if decimals is None else decimals

    def __eq__(self, other):
        if not super(NumberDef, self).__eq__(other):
            return False

        return (
            self.decimals == other.decimals
            and self.maximum == other.maximum
            and self.maximum == other.maximum
        )

    def convert_value(self, value):
        if isinstance(value, six.string_types):
            try:
                value = float(value)
            except Exception:
                pass

        if not isinstance(value, (int, float)):
            return self.default

        if self.decimals == 0:
            return int(value)
        return round(float(value), self.decimals)


class TextDef(AbtractAttrDef):
    """Text definition.

    Text can have multiline option so endline characters are allowed regex
    validation can be applied placeholder for UI purposes and default value.

    Regex validation is not part of attribute implemntentation.

    Args:
        multiline(bool): Text has single or multiline support.
        regex(str, re.Pattern): Regex validation.
        placeholder(str): UI placeholder for attribute.
        default(str, None): Default value. Empty string used when not defined.
    """
    def __init__(
        self, key, multiline=None, regex=None, placeholder=None, default=None,
        **kwargs
    ):
        super(TextDef, self).__init__(key, **kwargs)

        if multiline is None:
            multiline = False

        if default is None:
            default = ""

        elif not isinstance(default, six.string_types):
            raise TypeError((
                "'default' argument must be a {}, not '{}'"
            ).format(six.string_types, type(default)))

        if isinstance(regex, six.string_types):
            regex = re.compile(regex)

        self.multiline = multiline
        self.placeholder = placeholder
        self.regex = regex
        self.default = default

    def __eq__(self, other):
        if not super(TextDef, self).__eq__(other):
            return False

        return (
            self.multiline == other.multiline
            and self.regex == other.regex
        )

    def convert_value(self, value):
        if isinstance(value, six.string_types):
            return value
        return self.default


class EnumDef(AbtractAttrDef):
    """Enumeration of single item from items.

    Args:
        items: Items definition that can be coverted to
            `collections.OrderedDict`. Dictionary represent {value: label}
            relation.
        default: Default value. Must be one key(value) from passed items.
    """

    def __init__(self, key, items, default=None, **kwargs):
        super(EnumDef, self).__init__(key, **kwargs)

        if not items:
            raise ValueError((
                "Empty 'items' value. {} must have"
                " defined values on initialization."
            ).format(self.__class__.__name__))

        items = collections.OrderedDict(items)
        if default not in items:
            for key in items.keys():
                default = key
                break

        self.items = items
        self.default = default

    def __eq__(self, other):
        if not super(EnumDef, self).__eq__(other):
            return False

        if set(self.items.keys()) != set(other.items.keys()):
            return False

        for key, label in self.items.items():
            if other.items[key] != label:
                return False
        return True

    def convert_value(self, value):
        if value in self.items:
            return value
        return self.default


class BoolDef(AbtractAttrDef):
    """Boolean representation.

    Args:
        default(bool): Default value. Set to `False` if not defined.
    """

    def __init__(self, key, default=None, **kwargs):
        super(BoolDef, self).__init__(key, **kwargs)

        if default is None:
            default = False
        self.default = default

    def convert_value(self, value):
        if isinstance(value, bool):
            return value
        return self.default
