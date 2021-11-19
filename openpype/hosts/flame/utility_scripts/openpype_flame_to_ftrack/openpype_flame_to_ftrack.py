from __future__ import print_function

import os
import sys

try:
    from panel_app import FlameToFtrackPanel
except ImportError:
    SCRIPT_DIR = os.path.dirname(__file__)
    PACKAGE_DIR = os.path.join(SCRIPT_DIR, "modules")
    sys.path.append(PACKAGE_DIR)

    from panel_app import FlameToFtrackPanel

def scope_sequence(selection):
    import flame
    return any(isinstance(item, flame.PySequence) for item in selection)


def get_media_panel_custom_ui_actions():
    return [
        {
            "name": "OpenPype: Ftrack",
            "actions": [
                {
                    "name": "Create Shots",
                    "isVisible": scope_sequence,
                    "execute": FlameToFtrackPanel
                }
            ]
        }
    ]
