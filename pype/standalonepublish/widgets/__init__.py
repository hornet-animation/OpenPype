from avalon.vendor.Qt import *
from avalon.vendor import qtawesome as awesome
from avalon import style

HelpRole = QtCore.Qt.UserRole + 2
FamilyRole = QtCore.Qt.UserRole + 3
ExistsRole = QtCore.Qt.UserRole + 4
PluginRole = QtCore.Qt.UserRole + 5
PluginKeyRole = QtCore.Qt.UserRole + 6

from ..resources import get_resource
from .button_from_svgs import SvgResizable, SvgButton

from .model_node import Node
from .model_tree import TreeModel
from .model_asset import AssetModel
from .model_filter_proxy_exact_match import ExactMatchesFilterProxyModel
from .model_filter_proxy_recursive_sort import RecursiveSortFilterProxyModel
from .model_tasks_template import TasksTemplateModel
from .model_tree_view_deselectable import DeselectableTreeView

from .widget_asset_view import AssetView
from .widget_asset import AssetWidget

from .widget_family_desc import FamilyDescriptionWidget
from .widget_family import FamilyWidget

from .widget_drop_empty import DropEmpty
from .widget_component_item import ComponentItem
from .widget_components_list import ComponentsList
from .widget_drop_frame import DropDataFrame
from .widget_components import ComponentsWidget

from .widget_shadow import ShadowWidget
