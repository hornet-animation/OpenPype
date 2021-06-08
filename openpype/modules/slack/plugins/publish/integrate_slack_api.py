from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import pyblish.api
from openpype.lib.plugin_tools import prepare_template_data


class IntegrateSlackAPI(pyblish.api.InstancePlugin):
    """ Send message notification to a channel.

        Triggers on instances with "slack" family, filled by
        'collect_slack_family'.

        Expects configured profile in
        Project settings > Slack > Publish plugins > Notification to Slack

        Message template can contain {} placeholders from anatomyData.
    """
    order = pyblish.api.IntegratorOrder + 0.499
    label = "Integrate Slack Api"
    families = ["slack"]

    optional = True

    def process(self, instance):
        message_templ = instance.data["slack_message"]

        fill_pairs = set()
        for key, value in instance.data["anatomyData"].items():
            if not isinstance(value, str):
                continue
            fill_pairs.add((key, value))
        self.log.debug("fill_pairs:: {}".format(fill_pairs))

        message = message_templ.format(**prepare_template_data(fill_pairs))

        self.log.debug("message:: {}".format(message))
        if '{' in message:
            self.log.warning(
                "Missing values to fill message properly {}".format(message))

            return

        for channel in instance.data["slack_channel"]:
            try:
                client = WebClient(token=instance.data["slack_token"])
                _ = client.chat_postMessage(
                    channel=channel,
                    text=message
                )
            except SlackApiError as e:
                # You will get a SlackApiError if "ok" is False
                self.log.warning("Error happened {}".format(e.response[
                    "error"]))
