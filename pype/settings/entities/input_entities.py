import copy
from .item_entities import ItemEntity
from .lib import (
    NOT_SET,
    DefaultsNotDefined
)
from .constants import (
    OverrideState,
    METADATA_KEYS,
    M_DYNAMIC_KEY_LABEL,
    M_ENVIRONMENT_KEY
)


class InputEntity(ItemEntity):
    type_error_template = "Got invalid value type {}. Expected: {}"

    def __init__(self, *args, **kwargs):
        super(InputEntity, self).__init__(*args, **kwargs)
        if not self.group_item and not self.is_group:
            self.is_group = True
        if self.value_on_not_set is NOT_SET:
            raise ValueError(
                "Attribute `value_on_not_set` is not filled. {}".format(
                    self.__class__.__name__
                )
            )

        self._current_value = NOT_SET

    def schema_validations(self):
        if not self.file_item:
            raise ValueError(
                "{}: Missing parent file entity.".format(self.path)
            )

        super(InputEntity, self).schema_validations()

    def __eq__(self, other):
        if isinstance(other, ItemEntity):
            return self.value == other.value
        return self.value == other

    @property
    def value(self):
        return self._current_value

    def validate_value(self, value):
        if value is NOT_SET:
            raise ValueError(
                "Setting value to NOT_SET object is invalid operation."
            )

        if not isinstance(value, self.valid_value_types):
            raise TypeError(self.type_error_template.format(
                str(type(value)),
                ", ".join([str(_t) for _t in self.valid_value_types])
            ))

    def set_value(self, value):
        self.validate_value(value)
        self._current_value = value
        self.on_value_change()

    def on_value_change(self):
        # Change has_project_override attr value
        if self.override_state is OverrideState.PROJECT:
            self.has_project_override = True

        elif self.override_state is OverrideState.STUDIO:
            self.has_studio_override = True

        self.on_change()

    def on_change(self):
        value_is_modified = None
        if self.override_state is OverrideState.PROJECT:
            # Only value change
            if (
                self.has_project_override
                and self.project_override_value is not NOT_SET
            ):
                value_is_modified = (
                    self._current_value != self.project_override_value
                )

        if (
            self.override_state is OverrideState.STUDIO
            or value_is_modified is None
            and (
                self.has_studio_override
                and self.studio_override_value is not NOT_SET
            )
        ):
            value_is_modified = (
                self._current_value != self.studio_override_value
            )

        if value_is_modified is None:
            value_is_modified = self._current_value != self.default_value

        self.value_is_modified = value_is_modified

        self.parent.on_child_change(self)

    def on_child_change(self, child_obj):
        raise TypeError("Input entities do not contain children.")

    def update_default_value(self, value):
        # NOTE must call set_override_state manually
        self.default_value = value
        self.has_default_value = value is not NOT_SET

    def update_studio_values(self, value):
        # NOTE must call set_override_state manually
        self.studio_override_value = value
        self.had_studio_override = bool(value is not NOT_SET)

    def update_project_values(self, value):
        # NOTE must call set_override_state manually
        self.project_override_value = value
        self.had_project_override = bool(value is not NOT_SET)

    @property
    def child_has_studio_override(self):
        return self.has_studio_override

    @property
    def child_has_project_override(self):
        return self.has_project_override

    @property
    def child_is_invalid(self):
        return self.is_invalid

    @property
    def child_is_modified(self):
        return self.has_unsaved_changes

    @property
    def has_unsaved_changes(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return False

        if self.value_is_modified:
            return True

        # These may be stored on value change
        if self.override_state is OverrideState.DEFAULTS:
            if not self.has_default_value:
                return True

        elif self.override_state is OverrideState.STUDIO:
            if self.has_studio_override != self.had_studio_override:
                return True

            if not self.has_studio_override and not self.has_default_value:
                return True

        elif self.override_state is OverrideState.PROJECT:
            if self.has_project_override != self.had_project_override:
                return True

            if (
                not self.has_project_override
                and not self.has_studio_override
                and not self.has_default_value
            ):
                return True
        return False

    def settings_value(self):
        if self.override_state is OverrideState.NOT_DEFINED:
            return NOT_SET

        if self.is_group:
            if self.override_state is OverrideState.STUDIO:
                if not self.has_studio_override:
                    return NOT_SET
            elif self.override_state is OverrideState.PROJECT:
                if not self.has_project_override:
                    return NOT_SET
        return self.value

    def get_invalid(self):
        if self.is_invalid:
            return [self]

    def set_override_state(self, state):
        self.override_state = state
        if (
            not self.has_default_value
            and state in (OverrideState.STUDIO, OverrideState.PROJECT)
        ):
            raise DefaultsNotDefined(self)

        if state is OverrideState.STUDIO:
            self.has_studio_override = (
                self.studio_override_value is not NOT_SET
            )

        elif state is OverrideState.PROJECT:
            self.has_project_override = (
                self.project_override_value is not NOT_SET
            )
            self.has_studio_override = self.had_studio_override

        if (
            state is OverrideState.PROJECT
            and self.has_project_override
        ):
            value = self.project_override_value

        elif self.has_studio_override:
            value = self.studio_override_value

        else:
            value = self.default_value

        if value is NOT_SET:
            value = self.value_on_not_set
            self.has_default_value = False
        else:
            self.has_default_value = True
        self.value_is_modified = False

        self._current_value = copy.deepcopy(value)

    def remove_overrides(self):
        current_value = self.default_value
        if self.override_state is OverrideState.STUDIO:
            self.has_studio_override = False

        elif self.override_state is OverrideState.PROJECT:
            self.has_project_override = False
            if self.studio_override_value is not NOT_SET:
                current_value = self.studio_override_value

        self._current_value = current_value

    def reset_to_pype_default(self):
        if self.override_state is OverrideState.PROJECT:
            raise ValueError(
                "Can't reset to Pype defaults on project overrides state."
            )
        self.has_studio_override = False
        value = self.default_value
        if value is NOT_SET:
            value = self.value_on_not_set
        self.set_value(value)

    def set_as_overriden(self):
        pass

    def set_studio_default(self):
        # self.set_value(self.studio_override_value)
        pass

    def discard_changes(self):
        pass

    def get_child_path(self, child_obj):
        raise TypeError("{} can't have children".format(
            self.__class__.__name__
        ))


class NumberEntity(InputEntity):
    schema_types = ["number"]

    def item_initalization(self):
        self.minimum = self.schema_data.get("minimum", -99999)
        self.maximum = self.schema_data.get("maximum", 99999)
        self.decimal = self.schema_data.get("decimal", 0)

        if self.decimal:
            valid_value_types = (int, float)
        else:
            valid_value_types = (int, )
        self.valid_value_types = valid_value_types
        self.value_on_not_set = 0

    def set_value(self, value):
        # TODO check number for floats, integers and point
        super(NumberEntity, self).set_value(value)


class BoolEntity(InputEntity):
    schema_types = ["boolean"]

    def item_initalization(self):
        self.valid_value_types = (bool, )
        self.value_on_not_set = True


class EnumEntity(InputEntity):
    schema_types = ["enum"]

    def item_initalization(self):
        self.multiselection = self.schema_data.get("multiselection", False)
        self.enum_items = self.schema_data["enum_items"]
        if not self.enum_items:
            raise ValueError("Attribute `enum_items` is not defined.")

        if self.multiselection:
            self.valid_value_types = (list, )
            self.value_on_not_set = []
        else:
            valid_value_types = set()
            for item in self.enum_items:
                if self.value_on_not_set is NOT_SET:
                    self.value_on_not_set = item
                valid_value_types.add(type(item))

            self.valid_value_types = tuple(valid_value_types)

        # GUI attribute
        self.placeholder = self.schema_data.get("placeholder")

    def set_value(self, value):
        if self.multiselection:
            if not isinstance(value, list):
                if isinstance(value, (set, tuple)):
                    value = list(value)
                else:
                    value = [value]
            check_values = value
        else:
            check_values = [value]

        for item in check_values:
            if item not in self.enum_items:
                raise ValueError(
                    "Invalid value \"{}\". Expected: {}".format(
                        item, self.enum_items
                    )
                )
        self._current_value = value


class TextEntity(InputEntity):
    schema_types = ["text"]

    def item_initalization(self):
        self.valid_value_types = (str, )
        self.value_on_not_set = ""

        # GUI attributes
        self.multiline = self.schema_data.get("multiline", False)
        self.placeholder_text = self.schema_data.get("placeholder")


class PathInput(InputEntity):
    schema_types = ["path-input"]

    def item_initalization(self):
        self.with_arguments = self.schema_data.get("with_arguments", False)
        if self.with_arguments:
            self.valid_value_types = (list, )
            self.value_on_not_set = []
        else:
            self.valid_value_types = (str, )
            self.value_on_not_set = ""


class RawJsonEntity(InputEntity):
    schema_types = ["raw-json"]

    def item_initalization(self):
        # Schema must define if valid value is dict or list
        self.valid_value_types = (list, dict)
        self.value_on_not_set = {}

        self.default_metadata = {}
        self.studio_override_metadata = {}
        self.project_override_metadata = {}

        self.current_metadata = {}

    def set_value(self, value):
        self.validate_value(value)
        self._current_value = value
        self.current_metadata = self.get_metadata_from_value(value)
        self.on_value_change()

    def get_metadata_from_value(self, value):
        metadata = {}
        if self.is_env_group and isinstance(value, dict):
            if M_DYNAMIC_KEY_LABEL in value:
                metadata[M_DYNAMIC_KEY_LABEL] = value.pop(M_DYNAMIC_KEY_LABEL)

            metadata[M_ENVIRONMENT_KEY] = {
                self.env_group_key: list(value.keys())
            }
        return metadata

    def set_override_state(self, state):
        self.override_state = state
        if (
            not self.has_default_value
            and state in (OverrideState.STUDIO, OverrideState.PROJECT)
        ):
            raise DefaultsNotDefined(self)

        if state is OverrideState.STUDIO:
            self.has_studio_override = (
                self.studio_override_value is not NOT_SET
            )

        elif state is OverrideState.PROJECT:
            self.has_project_override = (
                self.project_override_value is not NOT_SET
            )
            self.has_studio_override = self.had_studio_override

        if (
            state is OverrideState.PROJECT
            and self.has_project_override
        ):
            value = self.project_override_value

        elif self.has_studio_override:
            value = self.studio_override_value

        elif self.default_value is not NOT_SET:
            value = self.default_value

        else:
            value = self.value_on_not_set

        self._current_value = copy.deepcopy(value)
        self.current_metadata = self.get_metadata_from_value(
            self._current_value
        )

    def settings_value(self):
        value = super(RawJsonEntity, self).settings_value()
        if self.is_env_group and isinstance(value, dict):
            value.update(self.current_metadata)
        return value

    def _prepare_value(self, value):
        metadata = {}
        if isinstance(value, dict):
            for key in METADATA_KEYS:
                if key in value:
                    metadata[key] = value.pop(key)
        return value, metadata

    def update_default_value(self, value):
        self.has_default_value = value is not NOT_SET
        value, metadata = self._prepare_value(value)
        self.default_value = value
        self.default_metadata = metadata

    def update_studio_values(self, value):
        self.had_studio_override = value is not NOT_SET
        value, metadata = self._prepare_value(value)
        self.studio_override_value = value
        self.studio_override_metadata = metadata

    def update_project_values(self, value):
        self.had_project_override = value is not NOT_SET
        value, metadata = self._prepare_value(value)
        self.project_override_value = value
        self.project_override_metadata = metadata
