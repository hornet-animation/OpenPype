# -*- coding: utf-8 -*-
"""Close PS after publish. For Webpublishing only."""
import os

import pyblish.api

from avalon import photoshop


class ClosePS(pyblish.api.ContextPlugin):
    """Close PS after publish. For Webpublishing only.
    """

    order = pyblish.api.IntegratorOrder + 14
    label = "Close PS"
    optional = True
    active = True

    hosts = ["photoshop"]

    def process(self, context):
        self.log.info("ClosePS")
        if not os.environ.get("IS_HEADLESS"):
            return

        stub = photoshop.stub()
        self.log.info("Shutting down PS")
        stub.save()
        stub.close()
        self.log.info("PS closed")
