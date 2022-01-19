import pyblish
import openpype
import openpype.hosts.flame.api as opfapi
from openpype.hosts.flame.otio import flame_export

# # developer reload modules
from pprint import pformat


class PrecollectInstances(pyblish.api.ContextPlugin):
    """Collect all Track items selection."""

    order = pyblish.api.CollectorOrder - 0.47
    label = "Precollect Instances"
    hosts = ["flame"]

    audio_track_items = []

    def process(self, context):
        project = context.data["flameProject"]
        sequence = context.data["flameSequence"]
        self.otio_timeline = context.data["otioTimeline"]
        self.clips_in_reels = opfapi.get_clips_in_reels(project)
        self.fps = context.data["fps"]

        # process all sellected
        with opfapi.maintained_segment_selection(sequence) as segments:
            for segment in segments:
                clip_data = opfapi.get_segment_attributes(segment)
                clip_name = clip_data["segment_name"]
                self.log.debug("clip_name: {}".format(clip_name))

                # get openpype tag data
                marker_data = opfapi.get_segment_data_marker(segment)
                self.log.debug("__ marker_data: {}".format(
                    pformat(marker_data)))

                if not marker_data:
                    continue

                if marker_data.get("id") != "pyblish.avalon.instance":
                    continue

                # get file path
                file_path = clip_data["fpath"]

                # get source clip
                source_clip = self._get_reel_clip(file_path)

                first_frame = opfapi.get_frame_from_path(file_path) or 0

                head, tail = self._get_head_tail(clip_data, first_frame)

                # solve handles length
                marker_data["handleStart"] = min(
                    marker_data["handleStart"], head)
                marker_data["handleEnd"] = min(
                    marker_data["handleEnd"], tail)

                with_audio = bool(marker_data.pop("audio"))

                # add marker data to instance data
                inst_data = dict(marker_data.items())

                asset = marker_data["asset"]
                subset = marker_data["subset"]

                # insert family into families
                family = marker_data["family"]
                families = [str(f) for f in marker_data["families"]]
                families.insert(0, str(family))

                # form label
                label = asset
                if asset != clip_name:
                    label += " ({})".format(clip_name)
                label += " {}".format(subset)
                label += " {}".format("[" + ", ".join(families) + "]")

                inst_data.update({
                    "name": "{}_{}".format(asset, subset),
                    "label": label,
                    "asset": asset,
                    "item": segment,
                    "families": families,
                    "publish": marker_data["publish"],
                    "fps": self.fps,
                    "flameSourceClip": source_clip,
                    "sourceFirstFrame": first_frame,
                    "path": file_path
                })

                # get otio clip data
                otio_data = self._get_otio_clip_instance_data(clip_data) or {}
                self.log.debug("__ otio_data: {}".format(pformat(otio_data)))

                # add to instance data
                inst_data.update(otio_data)
                self.log.debug("__ inst_data: {}".format(pformat(inst_data)))

                # add resolution
                self._get_resolution_to_data(inst_data, context)

                # create instance
                instance = context.create_instance(**inst_data)

                # add colorspace data
                instance.data.update({
                    "versionData": {
                        "colorspace": clip_data["colour_space"],
                    }
                })

                # create shot instance for shot attributes create/update
                self._create_shot_instance(context, clip_name, **inst_data)

                self.log.info("Creating instance: {}".format(instance))
                self.log.info(
                    "_ instance.data: {}".format(pformat(instance.data)))

                if not with_audio:
                    continue

                # add audioReview attribute to plate instance data
                # if reviewTrack is on
                if marker_data.get("reviewTrack") is not None:
                    instance.data["reviewAudio"] = True

    def _get_head_tail(self, clip_data, first_frame):
        # calculate head and tail with forward compatibility
        head = clip_data.get("segment_head")
        tail = clip_data.get("segment_tail")

        if not head:
            head = int(clip_data["source_in"]) - int(first_frame)
        if not tail:
            tail = int(
                clip_data["source_duration"] - (
                    head + clip_data["record_duration"]
                )
            )
        return head, tail

    def _get_reel_clip(self, path):
        match_reel_clip = [
            clip for clip in self.clips_in_reels
            if clip["fpath"] == path
        ]
        if match_reel_clip:
            return match_reel_clip.pop()

    def _get_resolution_to_data(self, data, context):
        assert data.get("otioClip"), "Missing `otioClip` data"

        # solve source resolution option
        if data.get("sourceResolution", None):
            otio_clip_metadata = data[
                "otioClip"].media_reference.metadata
            data.update({
                "resolutionWidth": otio_clip_metadata[
                        "openpype.source.width"],
                "resolutionHeight": otio_clip_metadata[
                    "openpype.source.height"],
                "pixelAspect": otio_clip_metadata[
                    "openpype.source.pixelAspect"]
            })
        else:
            otio_tl_metadata = context.data["otioTimeline"].metadata
            data.update({
                "resolutionWidth": otio_tl_metadata["openpype.timeline.width"],
                "resolutionHeight": otio_tl_metadata[
                    "openpype.timeline.height"],
                "pixelAspect": otio_tl_metadata[
                    "openpype.timeline.pixelAspect"]
            })

    def _create_shot_instance(self, context, clip_name, **data):
        master_layer = data.get("heroTrack")
        hierarchy_data = data.get("hierarchyData")
        asset = data.get("asset")

        if not master_layer:
            return

        if not hierarchy_data:
            return

        asset = data["asset"]
        subset = "shotMain"

        # insert family into families
        family = "shot"

        # form label
        label = asset
        if asset != clip_name:
            label += " ({}) ".format(clip_name)
        label += " {}".format(subset)
        label += " [{}]".format(family)

        data.update({
            "name": "{}_{}".format(asset, subset),
            "label": label,
            "subset": subset,
            "asset": asset,
            "family": family,
            "families": []
        })

        instance = context.create_instance(**data)
        self.log.info("Creating instance: {}".format(instance))
        self.log.debug(
            "_ instance.data: {}".format(pformat(instance.data)))

    def _get_otio_clip_instance_data(self, clip_data):
        """
        Return otio objects for timeline, track and clip

        Args:
            timeline_item_data (dict): timeline_item_data from list returned by
                                    resolve.get_current_timeline_items()
            otio_timeline (otio.schema.Timeline): otio object

        Returns:
            dict: otio clip object

        """
        segment = clip_data["PySegment"]
        s_track_name = segment.parent.name.get_value()
        timeline_range = self._create_otio_time_range_from_timeline_item_data(
            clip_data)

        for otio_clip in self.otio_timeline.each_clip():
            track_name = otio_clip.parent().name
            parent_range = otio_clip.range_in_parent()
            if s_track_name not in track_name:
                continue
            if otio_clip.name not in segment.name.get_value():
                continue
            if openpype.lib.is_overlapping_otio_ranges(
                    parent_range, timeline_range, strict=True):

                # add pypedata marker to otio_clip metadata
                for marker in otio_clip.markers:
                    if opfapi.MARKER_NAME in marker.name:
                        otio_clip.metadata.update(marker.metadata)
                return {"otioClip": otio_clip}

        return None

    def _create_otio_time_range_from_timeline_item_data(self, clip_data):
        frame_start = int(clip_data["record_in"])
        frame_duration = int(clip_data["record_duration"])

        return flame_export.create_otio_time_range(
            frame_start, frame_duration, self.fps)
