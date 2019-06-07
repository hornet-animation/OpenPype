from pyblish import api
import pype


class CollectPlates(api.InstancePlugin):
    """Collect plates"""

    order = api.CollectorOrder + 0.49
    label = "Collect Plates"
    hosts = ["nukestudio"]
    families = ["plate"]

    def process(self, instance):
        import os

        # add to representations
        if not instance.data.get("representations"):
            instance.data["representations"] = list()

        version_data = dict()
        context = instance.context
        anatomy = context.data.get("anatomy", None)
        padding = int(anatomy.templates['render']['padding'])

        name = instance.data["subset"]
        asset = instance.data["asset"]
        track = instance.data["track"]
        family = instance.data["family"]
        families = instance.data["families"]
        version = instance.data["version"]
        source_path = instance.data["sourcePath"]
        source_file = os.path.basename(source_path)

        # staging dir creation
        staging_dir = os.path.dirname(
            source_path)

        item = instance.data["item"]

        # get handles
        handles = int(instance.data["handles"])
        handle_start = int(instance.data["handleStart"])
        handle_end = int(instance.data["handleEnd"])

        # get source frames
        source_in = int(instance.data["sourceIn"])
        source_out = int(instance.data["sourceOut"])

        # get source frames
        frame_start = int(instance.data["startFrame"])
        frame_end = int(instance.data["endFrame"])

        # get source frames
        source_in_h = int(instance.data["sourceInH"])
        source_out_h = int(instance.data["sourceOutH"])

        # get timeline frames
        timeline_in = int(instance.data["timelineIn"])
        timeline_out = int(instance.data["timelineOut"])

        # frame-ranges with handles
        timeline_frame_start = int(instance.data["timelineInHandles"])
        timeline_frame_end = int(instance.data["timelineOutHandles"])

        # get colorspace
        colorspace = item.sourceMediaColourTransform()

        # get sequence from context, and fps
        fps = float(str(instance.data["fps"]))

        # test output
        self.log.debug("__ handles: {}".format(handles))
        self.log.debug("__ handle_start: {}".format(handle_start))
        self.log.debug("__ handle_end: {}".format(handle_end))
        self.log.debug("__ frame_start: {}".format(frame_start))
        self.log.debug("__ frame_end: {}".format(frame_end))
        self.log.debug("__ f duration: {}".format(frame_end - frame_start + 1))
        self.log.debug("__ source_in: {}".format(source_in))
        self.log.debug("__ source_out: {}".format(source_out))
        self.log.debug("__ s duration: {}".format(source_out - source_in + 1))
        self.log.debug("__ source_in_h: {}".format(source_in_h))
        self.log.debug("__ source_out_h: {}".format(source_out_h))
        self.log.debug("__ sh duration: {}".format(source_out_h - source_in_h + 1))
        self.log.debug("__ timeline_in: {}".format(timeline_in))
        self.log.debug("__ timeline_out: {}".format(timeline_out))
        self.log.debug("__ t duration: {}".format(timeline_out - timeline_in + 1))
        self.log.debug("__ timeline_frame_start: {}".format(
            timeline_frame_start))
        self.log.debug("__ timeline_frame_end: {}".format(timeline_frame_end))
        self.log.debug("__ colorspace: {}".format(colorspace))
        self.log.debug("__ track: {}".format(track))
        self.log.debug("__ fps: {}".format(fps))
        self.log.debug("__ source_file: {}".format(source_file))
        self.log.debug("__ staging_dir: {}".format(staging_dir))

        self.log.debug("__ before family: {}".format(family))
        self.log.debug("__ before families: {}".format(families))
        #
        # this is just workaround because 'clip' family is filtered
        instance.data["family"] = families[-1]
        instance.data["families"].append(family)

        # add to data of representation
        version_data.update({
            "handles": handles,
            "handleStart": handle_start,
            "handleEnd": handle_end,
            "sourceIn": source_in,
            "sourceOut": source_out,
            "startFrame": frame_start,
            "endFrame": frame_end,
            "timelineIn": timeline_in,
            "timelineOut": timeline_out,
            "timelineInHandles": timeline_frame_start,
            "timelineOutHandles": timeline_frame_end,
            "fps": fps,
            "colorspace": colorspace,
            "families": [f for f in families if 'ftrack' not in f],
            "asset": asset,
            "subset": name,
            "track": track,
            "version": int(version)
        })
        instance.data["versionData"] = version_data

        try:
            head, padding, ext = source_file.split('.')
            source_first_frame = int(padding)
            padding = len(padding)
            file = "{head}.%0{padding}d.{ext}".format(
                head=head,
                padding=padding,
                ext=ext
            )
            start_frame = source_first_frame
            end_frame = source_first_frame + source_out
            files = [file % i for i in range(
                (source_first_frame + source_in_h),
                ((source_first_frame + source_out_h) + 1), 1)]
        except Exception as e:
            self.log.debug("Exception in file: {}".format(e))
            head, ext = source_file.split('.')
            files = source_file
            start_frame = source_in_h
            end_frame = source_out_h

        if isinstance(files, list):
            mov_file = head + ".mov"
            mov_path = os.path.normpath(os.path.join(staging_dir, mov_file))
            if os.path.exists(mov_path):
                # adding mov into the representations
                self.log.debug("__ mov_path: {}".format(mov_path))
                plates_mov_representation = {
                    'files': mov_file,
                    'stagingDir': staging_dir,
                    'startFrame': 0,
                    'endFrame': source_out - source_in + 1,
                    'step': 1,
                    'frameRate': fps,
                    'preview': True,
                    'thumbnail': False,
                    'name': "preview",
                    'ext': "mov",
                }
                instance.data["representations"].append(
                    plates_mov_representation)

        thumb_file = head + ".png"
        thumb_path = os.path.join(staging_dir, thumb_file)
        self.log.debug("__ thumb_path: {}".format(thumb_path))
        thumbnail = item.thumbnail(source_in).save(
            thumb_path,
            format='png'
        )
        self.log.debug("__ thumbnail: {}".format(thumbnail))

        thumb_representation = {
            'files': thumb_file,
            'stagingDir': staging_dir,
            'name': "thumbnail",
            'thumbnail': True,
            'ext': "png"
        }
        instance.data["representations"].append(
            thumb_representation)

        # adding representation for plates
        plates_representation = {
            'files': files,
            'stagingDir': staging_dir,
            'name': ext,
            'ext': ext,
            'startFrame': start_frame,
            'endFrame': end_frame,
        }
        instance.data["representations"].append(plates_representation)

        # testing families
        family = instance.data["family"]
        families = instance.data["families"]

        # test prints version_data
        self.log.debug("__ version_data: {}".format(version_data))
        self.log.debug("__ plates_representation: {}".format(
            plates_representation))
        self.log.debug("__ after family: {}".format(family))
        self.log.debug("__ after families: {}".format(families))

        # # this will do FnNsFrameServer
        # FnNsFrameServer.renderFrames(*_args)
