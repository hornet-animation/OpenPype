"""
Requires:
    None

Provides:
    instance     -> family ("review")
"""

import os

import pyblish.api


class CollectReview(pyblish.api.ContextPlugin):
    """Gather the active document as review instance.

    Triggers once even if no 'image' is published as by defaults it creates
    flatten image from a workfile.
    """

    label = "Collect Review"
    order = pyblish.api.CollectorOrder
    hosts = ["photoshop"]

    def process(self, context):
        family = "review"
        task = os.getenv("AVALON_TASK", None)
        subset = family + task.capitalize()

        instance = context.create_instance(subset)
        instance.data.update({
            "subset": subset,
            "label": subset,
            "name": subset,
            "family": family,
            "families": [],
            "representations": [],
            "asset": os.environ["AVALON_ASSET"]
        })
