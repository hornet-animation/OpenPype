class InputEntity(ItemEntity):
    type_error_template = "Got invalid value type {}. Expected: {}"

    def __init__(self, *args, **kwargs):
        super(InputEntity, self).__init__(*args, **kwargs)
        if self.default_value is NOT_SET:
            raise ValueError(
                "Attribute `default_value` is not filled. {}".format(
                    self.__class__.__name__
                )
            )

        self._current_value = NOT_SET

    def __eq__(self, other):
        if isinstance(other, ItemEntity):
            return self.current_value == other.current_value
        return self.current_value == other

    @property
    def current_value(self):
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

        elif self.override_state is OverrideState.STUDIO:
            if (
                self.has_studio_override
                and self.studio_override_value is not NOT_SET
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
        self.default_value = value

    def update_project_values(self, value):
        self.studio_override_value = value

    def update_studio_values(self, value):
        self.project_override_value = value

    @property
    def child_has_studio_override(self):
        return self.has_studio_override

    @property
    def child_is_invalid(self):
        return self.is_invalid

    @property
    def child_is_modified(self):
        return self.has_unsaved_changes

    @property
    def child_overriden(self):
        return self.is_overriden

    @property
    def has_unsaved_changes(self):
        if self.value_is_modified:
            return True

        if self.override_state is OverrideState.PROJECT:
            if self.has_project_override != self.had_project_override:
                return True

        elif self.override_state is OverrideState.STUDIO:
            if self.has_studio_override != self.had_studio_override:
                return True

        return False

    def settings_value(self):
        if self.is_in_dynamic_item:
            return self.current_value

        if not self.group_item:
            if not self.has_unsaved_changes:
                return NOT_SET
        return self.current_value

    def get_invalid(self):
        if self.is_invalid:
            return [self]

    def set_override_state(self, state):
        self.override_state = state
        if (
            state is OverrideState.PROJECT
            and self.project_override_value is not NOT_SET
        ):
            value = self.project_override_value

        elif self.studio_override_value is not NOT_SET:
            value = self.studio_override_value

        else:
            value = self.default_value

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
        self.set_value(self.default_value)

    def set_as_overriden(self):
        self.is_overriden = True

    def set_studio_default(self):
        self.set_value(self.studio_override_value)

    def discard_changes(self):
        self.has_studio_override = self.had_studio_override
        self.has_project_override = self.had_project_override


class NumberEntity(InputEntity):
    schema_types = ["number"]

    def item_initalization(self):
        self.valid_value_types = (int, float)
        self.default_value = 0

    def set_value(self, value):
        # TODO check number for floats, integers and point
        super(NumberEntity, self).set_value(value)


class BoolEntity(InputEntity):
    schema_types = ["boolean"]

    def item_initalization(self):
        self.default_value = True
        self.valid_value_types = (bool, )


class EnumEntity(InputEntity):
    schema_types = ["enum"]

    def item_initalization(self):
        self.multiselection = self.schema_data.get("multiselection", False)
        self.enum_items = self.schema_data["enum_items"]
        if not self.enum_items:
            raise ValueError("Attribute `enum_items` is not defined.")

        if self.multiselection:
            self.valid_value_types = (list, )
            self.default_value = []
        else:
            valid_value_types = set()
            for item in self.enum_items:
                if self.default_value is NOT_SET:
                    self.default_value = item
                valid_value_types.add(type(item))

            self.valid_value_types = tuple(valid_value_types)

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
