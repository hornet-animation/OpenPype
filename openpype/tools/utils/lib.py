import os
import sys
import contextlib
import collections

from Qt import QtWidgets, QtCore, QtGui

from avalon import io, api, style
from avalon.vendor import qtawesome

self = sys.modules[__name__]
self._jobs = dict()


def format_version(value, hero_version=False):
    """Formats integer to displayable version name"""
    label = "v{0:03d}".format(value)
    if not hero_version:
        return label
    return "[{}]".format(label)


@contextlib.contextmanager
def application():
    app = QtWidgets.QApplication.instance()

    if not app:
        print("Starting new QApplication..")
        app = QtWidgets.QApplication(sys.argv)
        yield app
        app.exec_()
    else:
        print("Using existing QApplication..")
        yield app


def defer(delay, func):
    """Append artificial delay to `func`

    This aids in keeping the GUI responsive, but complicates logic
    when producing tests. To combat this, the environment variable ensures
    that every operation is synchonous.

    Arguments:
        delay (float): Delay multiplier; default 1, 0 means no delay
        func (callable): Any callable

    """

    delay *= float(os.getenv("PYBLISH_DELAY", 1))
    if delay > 0:
        return QtCore.QTimer.singleShot(delay, func)
    else:
        return func()


def schedule(func, time, channel="default"):
    """Run `func` at a later `time` in a dedicated `channel`

    Given an arbitrary function, call this function after a given
    timeout. It will ensure that only one "job" is running within
    the given channel at any one time and cancel any currently
    running job if a new job is submitted before the timeout.

    """

    try:
        self._jobs[channel].stop()
    except (AttributeError, KeyError, RuntimeError):
        pass

    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(func)
    timer.start(time)

    self._jobs[channel] = timer


@contextlib.contextmanager
def dummy():
    """Dummy context manager

    Usage:
        >> with some_context() if False else dummy():
        ..   pass

    """

    yield


def iter_model_rows(model, column, include_root=False):
    """Iterate over all row indices in a model"""
    indices = [QtCore.QModelIndex()]  # start iteration at root

    for index in indices:
        # Add children to the iterations
        child_rows = model.rowCount(index)
        for child_row in range(child_rows):
            child_index = model.index(child_row, column, index)
            indices.append(child_index)

        if not include_root and not index.isValid():
            continue

        yield index


@contextlib.contextmanager
def preserve_states(tree_view,
                    column=0,
                    role=None,
                    preserve_expanded=True,
                    preserve_selection=True,
                    expanded_role=QtCore.Qt.DisplayRole,
                    selection_role=QtCore.Qt.DisplayRole):
    """Preserves row selection in QTreeView by column's data role.
    This function is created to maintain the selection status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vise versa.
        tree_view (QWidgets.QTreeView): the tree view nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned
    Returns:
        None
    """
    # When `role` is set then override both expanded and selection roles
    if role:
        expanded_role = role
        selection_role = role

    model = tree_view.model()
    selection_model = tree_view.selectionModel()
    flags = selection_model.Select | selection_model.Rows

    expanded = set()

    if preserve_expanded:
        for index in iter_model_rows(
            model, column=column, include_root=False
        ):
            if tree_view.isExpanded(index):
                value = index.data(expanded_role)
                expanded.add(value)

    selected = None

    if preserve_selection:
        selected_rows = selection_model.selectedRows()
        if selected_rows:
            selected = set(row.data(selection_role) for row in selected_rows)

    try:
        yield
    finally:
        if expanded:
            for index in iter_model_rows(
                model, column=0, include_root=False
            ):
                value = index.data(expanded_role)
                is_expanded = value in expanded
                # skip if new index was created meanwhile
                if is_expanded is None:
                    continue
                tree_view.setExpanded(index, is_expanded)

        if selected:
            # Go through all indices, select the ones with similar data
            for index in iter_model_rows(
                model, column=column, include_root=False
            ):
                value = index.data(selection_role)
                state = value in selected
                if state:
                    tree_view.scrollTo(index)  # Ensure item is visible
                    selection_model.select(index, flags)


@contextlib.contextmanager
def preserve_expanded_rows(tree_view, column=0, role=None):
    """Preserves expanded row in QTreeView by column's data role.

    This function is created to maintain the expand vs collapse status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vise versa.

    Arguments:
        tree_view (QWidgets.QTreeView): the tree view which is
            nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()

    expanded = set()

    for index in iter_model_rows(model, column=column, include_root=False):
        if tree_view.isExpanded(index):
            value = index.data(role)
            expanded.add(value)

    try:
        yield
    finally:
        if not expanded:
            return

        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in expanded
            if state:
                tree_view.expand(index)
            else:
                tree_view.collapse(index)


@contextlib.contextmanager
def preserve_selection(tree_view, column=0, role=None, current_index=True):
    """Preserves row selection in QTreeView by column's data role.

    This function is created to maintain the selection status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vise versa.

        tree_view (QWidgets.QTreeView): the tree view nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()
    selection_model = tree_view.selectionModel()
    flags = selection_model.Select | selection_model.Rows

    if current_index:
        current_index_value = tree_view.currentIndex().data(role)
    else:
        current_index_value = None

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        yield
        return

    selected = set(row.data(role) for row in selected_rows)
    try:
        yield
    finally:
        if not selected:
            return

        # Go through all indices, select the ones with similar data
        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in selected
            if state:
                tree_view.scrollTo(index)  # Ensure item is visible
                selection_model.select(index, flags)

            if current_index_value and value == current_index_value:
                selection_model.setCurrentIndex(
                    index, selection_model.NoUpdate
                )


class FamilyConfigCache:
    default_color = "#0091B2"
    _default_icon = None
    _default_item = None

    def __init__(self, dbcon):
        self.dbcon = dbcon
        self.family_configs = {}

    @classmethod
    def default_icon(cls):
        if cls._default_icon is None:
            cls._default_icon = qtawesome.icon(
                "fa.folder", color=cls.default_color
            )
        return cls._default_icon

    @classmethod
    def default_item(cls):
        if cls._default_item is None:
            cls._default_item = {"icon": cls.default_icon()}
        return cls._default_item

    def family_config(self, family_name):
        """Get value from config with fallback to default"""
        return self.family_configs.get(family_name, self.default_item())

    def refresh(self):
        """Get the family configurations from the database

        The configuration must be stored on the project under `config`.
        For example:

        {"config": {
            "families": [
                {"name": "avalon.camera", label: "Camera", "icon": "photo"},
                {"name": "avalon.anim", label: "Animation", "icon": "male"},
            ]
        }}

        It is possible to override the default behavior and set specific
        families checked. For example we only want the families imagesequence
        and camera to be visible in the Loader.

        # This will turn every item off
        api.data["familyStateDefault"] = False

        # Only allow the imagesequence and camera
        api.data["familyStateToggled"] = ["imagesequence", "camera"]

        """

        self.family_configs.clear()

        families = []

        # Update the icons from the project configuration
        project_name = self.dbcon.Session.get("AVALON_PROJECT")
        if project_name:
            project_doc = self.dbcon.find_one(
                {"type": "project"},
                projection={"config.families": True}
            )

            if not project_doc:
                print((
                    "Project \"{}\" not found!"
                    " Can't refresh family icons cache."
                ).format(project_name))
            else:
                families = project_doc["config"].get("families") or []

        # Check if any family state are being overwritten by the configuration
        default_state = api.data.get("familiesStateDefault", True)
        toggled = set(api.data.get("familiesStateToggled") or [])

        # Replace icons with a Qt icon we can use in the user interfaces
        for family in families:
            name = family["name"]
            # Set family icon
            icon = family.get("icon", None)
            if icon:
                family["icon"] = qtawesome.icon(
                    "fa.{}".format(icon),
                    color=self.default_color
                )
            else:
                family["icon"] = self.default_icon()

            # Update state
            if name in toggled:
                state = True
            else:
                state = default_state
            family["state"] = state

            self.family_configs[name] = family

        return self.family_configs


class GroupsConfig:
    # Subset group item's default icon and order
    _default_group_config = None

    def __init__(self, dbcon):
        self.dbcon = dbcon
        self.groups = {}

    @classmethod
    def default_group_config(cls):
        if cls._default_group_config is None:
            cls._default_group_config = {
                "icon": qtawesome.icon(
                    "fa.object-group",
                    color=style.colors.default
                ),
                "order": 0
            }
        return cls._default_group_config

    def refresh(self):
        """Get subset group configurations from the database

        The 'group' configuration must be stored in the project `config` field.
        See schema `config-1.0.json`

        """
        # Clear cached groups
        self.groups.clear()

        group_configs = []
        project_name = self.dbcon.Session.get("AVALON_PROJECT")
        if project_name:
            # Get pre-defined group name and apperance from project config
            project_doc = self.dbcon.find_one(
                {"type": "project"},
                projection={"config.groups": True}
            )

            if project_doc:
                group_configs = project_doc["config"].get("groups") or []
            else:
                print("Project not found! \"{}\"".format(project_name))

        # Build pre-defined group configs
        for config in group_configs:
            name = config["name"]
            icon = "fa." + config.get("icon", "object-group")
            color = config.get("color", style.colors.default)
            order = float(config.get("order", 0))

            self.groups[name] = {
                "icon": qtawesome.icon(icon, color=color),
                "order": order
            }

        return self.groups

    def ordered_groups(self, group_names):
        # default order zero included
        _orders = set([0])
        for config in self.groups.values():
            _orders.add(config["order"])

        # Remap order to list index
        orders = sorted(_orders)

        _groups = list()
        for name in group_names:
            # Get group config
            config = self.groups.get(name) or self.default_group_config()
            # Base order
            remapped_order = orders.index(config["order"])

            data = {
                "name": name,
                "icon": config["icon"],
                "_order": remapped_order,
            }

            _groups.append(data)

        # Sort by tuple (base_order, name)
        # If there are multiple groups in same order, will sorted by name.
        ordered_groups = sorted(
            _groups, key=lambda _group: (_group.pop("_order"), _group["name"])
        )

        total = len(ordered_groups)
        order_temp = "%0{}d".format(len(str(total)))

        # Update sorted order to config
        for index, group_data in enumerate(ordered_groups):
            order = index
            inverse_order = total - index

            # Format orders into fixed length string for groups sorting
            group_data["order"] = order_temp % order
            group_data["inverseOrder"] = order_temp % inverse_order

        return ordered_groups

    def active_groups(self, asset_ids, include_predefined=True):
        """Collect all active groups from each subset"""
        # Collect groups from subsets
        group_names = set(
            self.dbcon.distinct(
                "data.subsetGroup",
                {"type": "subset", "parent": {"$in": asset_ids}}
            )
        )
        if include_predefined:
            # Ensure all predefined group configs will be included
            group_names.update(self.groups.keys())

        return self.ordered_groups(group_names)

    def split_subsets_for_groups(self, subset_docs, grouping):
        """Collect all active groups from each subset"""
        subset_docs_without_group = collections.defaultdict(list)
        subset_docs_by_group = collections.defaultdict(dict)
        for subset_doc in subset_docs:
            subset_name = subset_doc["name"]
            if grouping:
                group_name = subset_doc["data"].get("subsetGroup")
                if group_name:
                    if subset_name not in subset_docs_by_group[group_name]:
                        subset_docs_by_group[group_name][subset_name] = []

                    subset_docs_by_group[group_name][subset_name].append(
                        subset_doc
                    )
                    continue

            subset_docs_without_group[subset_name].append(subset_doc)

        ordered_groups = self.ordered_groups(subset_docs_by_group.keys())

        return ordered_groups, subset_docs_without_group, subset_docs_by_group


def create_qthread(func, *args, **kwargs):
    class Thread(QtCore.QThread):
        def run(self):
            func(*args, **kwargs)
    return Thread()


def get_repre_icons():
    try:
        from openpype_modules import sync_server
    except Exception:
        # Backwards compatibility
        from openpype.modules import sync_server

    resource_path = os.path.join(
        os.path.dirname(sync_server.sync_server_module.__file__),
        "providers", "resources"
    )
    icons = {}
    # TODO get from sync module
    for provider in ['studio', 'local_drive', 'gdrive']:
        pix_url = "{}/{}.png".format(resource_path, provider)
        icons[provider] = QtGui.QIcon(pix_url)

    return icons


def get_progress_for_repre(doc, active_site, remote_site):
    """
        Calculates average progress for representation.

        If site has created_dt >> fully available >> progress == 1

        Could be calculated in aggregate if it would be too slow
        Args:
            doc(dict): representation dict
        Returns:
            (dict) with active and remote sites progress
            {'studio': 1.0, 'gdrive': -1} - gdrive site is not present
                -1 is used to highlight the site should be added
            {'studio': 1.0, 'gdrive': 0.0} - gdrive site is present, not
                uploaded yet
    """
    progress = {active_site: -1,
                remote_site: -1}
    if not doc:
        return progress

    files = {active_site: 0, remote_site: 0}
    doc_files = doc.get("files") or []
    for doc_file in doc_files:
        if not isinstance(doc_file, dict):
            continue

        sites = doc_file.get("sites") or []
        for site in sites:
            if (
                # Pype 2 compatibility
                not isinstance(site, dict)
                # Check if site name is one of progress sites
                or site["name"] not in progress
            ):
                continue

            files[site["name"]] += 1
            norm_progress = max(progress[site["name"]], 0)
            if site.get("created_dt"):
                progress[site["name"]] = norm_progress + 1
            elif site.get("progress"):
                progress[site["name"]] = norm_progress + site["progress"]
            else:  # site exists, might be failed, do not add again
                progress[site["name"]] = 0

    # for example 13 fully avail. files out of 26 >> 13/26 = 0.5
    avg_progress = {}
    avg_progress[active_site] = \
        progress[active_site] / max(files[active_site], 1)
    avg_progress[remote_site] = \
        progress[remote_site] / max(files[remote_site], 1)
    return avg_progress


def is_sync_loader(loader):
    return is_remove_site_loader(loader) or is_add_site_loader(loader)


def is_remove_site_loader(loader):
    return hasattr(loader, "remove_site_on_representation")


def is_add_site_loader(loader):
    return hasattr(loader, "add_site_to_representation")
