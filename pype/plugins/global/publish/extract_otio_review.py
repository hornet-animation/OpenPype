import os
import sys
import six
import errno
import clique
from avalon.vendor import filelink

import opentimelineio as otio
from pyblish import api
import pype


class ExtractOTIOReview(pype.api.Extractor):
    """ Extract OTIO timeline into one concuted video file.

    Expecting (instance.data):
        otioClip (otio.schema.clip): clip from otio timeline
        otioReviewClips (list): list with instances of otio.schema.clip
                                or otio.schema.gap

    Process description:
        Comparing `otioClip` parent range with `otioReviewClip` parent range
        will result in frame range witch is the trimmed cut. In case more otio
        clips or otio gaps are found in otioReviewClips then ffmpeg will
        generate multiple clips and those are then concuted together to one
        video file or image sequence. Resulting files are then added to
        instance as representation ready for review family plugins.
    """

    # order = api.ExtractorOrder
    order = api.CollectorOrder
    label = "Extract OTIO review"
    hosts = ["resolve"]
    families = ["review"]

    collections = list()
    sequence_workflow = False

    def _trim_available_range(self, avl_range, start, duration, fps):
        avl_start = int(avl_range.start_time.value)
        avl_durtation = int(avl_range.duration.value)
        src_start = int(avl_start + start)

        self.log.debug(f"_ avl_start: {avl_start}")
        self.log.debug(f"_ avl_durtation: {avl_durtation}")
        self.log.debug(f"_ src_start: {src_start}")
        # it only trims to source if
        if src_start < avl_start:
            if self.sequence_workflow:
                gap_range = list(range(src_start, avl_start))
                _collection = self.create_gap_collection(
                    self.sequence_workflow, -1, _range=gap_range)
            self.collections.append(_collection)
            start = 0
        # if duration < avl_durtation:
        #     end = int(start + duration - 1)
        #     av_end = avl_start + avl_durtation - 1
        #     self.collections.append(range(av_end, end))
        #     duration = avl_durtation
        return self._trim_media_range(
            avl_range, self._range_from_frames(start, duration, fps)
        )

    def process(self, instance):
        # self.create_representation(
        #     _otio_clip, otio_clip_range, instance)
        # get ranges and other time info from instance clip
        staging_dir = self.staging_dir(instance)
        handle_start = instance.data["handleStart"]
        handle_end = instance.data["handleEnd"]
        otio_review_clips = instance.data["otioReviewClips"]

        # in case of more than one clip check if second clip is sequence
        # this will define what ffmpeg workflow will be used
        # test first clip if it is not gap
        test_clip = otio_review_clips[0]
        if not isinstance(test_clip, otio.schema.Clip):
            # if first was gap then test second
            test_clip = otio_review_clips[1]

        # make sure second clip is not gap
        if isinstance(test_clip, otio.schema.Clip):
            metadata = test_clip.media_reference.metadata
            is_sequence = metadata.get("isSequence")
            if is_sequence:
                path = test_clip.media_reference.target_url
                available_range = self._trim_media_range(
                    test_clip.available_range(),
                    test_clip.source_range
                )
                collection = self._make_collection(
                    path, available_range, metadata)
                self.sequence_workflow = collection

        # loop all otio review clips
        for index, r_otio_cl in enumerate(otio_review_clips):
            self.log.debug(f">>> r_otio_cl: {r_otio_cl}")
            src_range = r_otio_cl.source_range
            start = src_range.start_time.value
            duration = src_range.duration.value
            available_range = None
            fps = src_range.duration.rate

            # add available range only if not gap
            if isinstance(r_otio_cl, otio.schema.Clip):
                available_range = r_otio_cl.available_range()
                fps = available_range.duration.rate

            # reframing handles conditions
            if (len(otio_review_clips) > 1) and (index == 0):
                # more clips | first clip reframing with handle
                start -= handle_start
                duration += handle_start
            elif len(otio_review_clips) > 1 \
                    and (index == len(otio_review_clips) - 1):
                # more clips | last clip reframing with handle
                duration += handle_end
            elif len(otio_review_clips) == 1:
                # one clip | add both handles
                start -= handle_start
                duration += (handle_start + handle_end)

            if available_range:
                available_range = self._trim_available_range(
                    available_range, start, duration, fps)

                first, last = pype.lib.otio_range_to_frame_range(
                    available_range)
                self.log.debug(f"_ first, last: {first}-{last}")

            # media source info
            if isinstance(r_otio_cl, otio.schema.Clip):
                path = r_otio_cl.media_reference.target_url
                metadata = r_otio_cl.media_reference.metadata

                if self.sequence_workflow:
                    _collection = self._make_collection(
                        path, available_range, metadata)
                    self.collections.append(_collection)
                    self.sequence_workflow = _collection

                # create seconds values
                start_sec = self._frames_to_secons(
                    start,
                    src_range.start_time.rate)
                duration_sec = self._frames_to_secons(
                    duration,
                    src_range.duration.rate)
            else:
                # create seconds values
                start_sec = 0
                duration_sec = self._frames_to_secons(
                    duration,
                    src_range.duration.rate)

                # if sequence workflow
                if self.sequence_workflow:
                    _collection = self.create_gap_collection(
                        self.sequence_workflow, index, duration=duration
                    )
                    self.collections.append(_collection)
                    self.sequence_workflow = _collection

            self.log.debug(f"_ start_sec: {start_sec}")
            self.log.debug(f"_ duration_sec: {duration_sec}")

        self.log.debug(f"_ self.sequence_workflow: {self.sequence_workflow}")
        self.log.debug(f"_ self.collections: {self.collections}")

    @staticmethod
    def _frames_to_secons(frames, framerate):
        rt = otio.opentime.from_frames(frames, framerate)
        return otio.opentime.to_seconds(rt)

    @staticmethod
    def _make_collection(path, otio_range, metadata):
        if "%" not in path:
            return None
        basename = os.path.basename(path)
        head = basename.split("%")[0]
        tail = os.path.splitext(basename)[-1]
        first, last = pype.lib.otio_range_to_frame_range(otio_range)
        collection = clique.Collection(
            head=head, tail=tail, padding=metadata["padding"])
        collection.indexes.update([i for i in range(first, (last + 1))])
        return collection

    @staticmethod
    def _trim_media_range(media_range, source_range):
        rw_media_start = otio.opentime.RationalTime(
            media_range.start_time.value + source_range.start_time.value,
            media_range.start_time.rate
        )
        rw_media_duration = otio.opentime.RationalTime(
            source_range.duration.value,
            media_range.duration.rate
        )
        return otio.opentime.TimeRange(
            rw_media_start, rw_media_duration)

    @staticmethod
    def _range_from_frames(start, duration, fps):
        return otio.opentime.TimeRange(
            otio.opentime.RationalTime(start, fps),
            otio.opentime.RationalTime(duration, fps)
        )

    @staticmethod
    def create_gap_collection(collection, index, duration=None, _range=None):
        head = "gap" + collection.head[-1]
        tail = collection.tail
        padding = collection.padding
        first_frame = min(collection.indexes)
        last_frame = max(collection.indexes) + 1

        if _range:
            new_range = _range
        if duration:
            if index == 0:
                new_range = range(
                    int(first_frame - duration), first_frame)
            else:
                new_range = range(
                    last_frame, int(last_frame + duration))

        return clique.Collection(
            head, tail, padding, indexes=set(new_range))

        # otio_src_range_handles = pype.lib.otio_range_with_handles(
            #     otio_src_range, instance)
            # self.log.debug(otio_src_range_handles)
            # range_convert = pype.lib.otio_range_to_frame_range
            # tl_start, tl_end = range_convert(otio_tl_range)
            # self.log.debug((tl_start, tl_end))


    #     inst_data = instance.data
    #     asset = inst_data['asset']
    #     item = inst_data['item']
    #     event_number = int(item.eventNumber())
    #
    #     # get representation and loop them
    #     representations = inst_data["representations"]
    #
    #     # check if sequence
    #     is_sequence = inst_data["isSequence"]
    #
    #     # get resolution default
    #     resolution_width = inst_data["resolutionWidth"]
    #     resolution_height = inst_data["resolutionHeight"]
    #
    #     # frame range data
    #     media_duration = inst_data["mediaDuration"]
    #
    #     ffmpeg_path = pype.lib.get_ffmpeg_tool_path("ffmpeg")
    #     ffprobe_path = pype.lib.get_ffmpeg_tool_path("ffprobe")
    #
    #     # filter out mov and img sequences
    #     representations_new = representations[:]
    #     for repre in representations:
    #         input_args = list()
    #         output_args = list()
    #
    #         tags = repre.get("tags", [])
    #
    #         # check if supported tags are in representation for activation
    #         filter_tag = False
    #         for tag in ["_cut-bigger", "_cut-smaller"]:
    #             if tag in tags:
    #                 filter_tag = True
    #                 break
    #         if not filter_tag:
    #             continue
    #
    #         self.log.debug("__ repre: {}".format(repre))
    #
    #         files = repre.get("files")
    #         staging_dir = repre.get("stagingDir")
    #         fps = repre.get("fps")
    #         ext = repre.get("ext")
    #
    #         # make paths
    #         full_output_dir = os.path.join(
    #             staging_dir, "cuts")
    #
    #         if is_sequence:
    #             new_files = list()
    #
    #             # frame range delivery included handles
    #             frame_start = (
    #                 inst_data["frameStart"] - inst_data["handleStart"])
    #             frame_end = (
    #                 inst_data["frameEnd"] + inst_data["handleEnd"])
    #             self.log.debug("_ frame_start: {}".format(frame_start))
    #             self.log.debug("_ frame_end: {}".format(frame_end))
    #
    #             # make collection from input files list
    #             collections, remainder = clique.assemble(files)
    #             collection = collections.pop()
    #             self.log.debug("_ collection: {}".format(collection))
    #
    #             # name components
    #             head = collection.format("{head}")
    #             padding = collection.format("{padding}")
    #             tail = collection.format("{tail}")
    #             self.log.debug("_ head: {}".format(head))
    #             self.log.debug("_ padding: {}".format(padding))
    #             self.log.debug("_ tail: {}".format(tail))
    #
    #             # make destination file with instance data
    #             # frame start and end range
    #             index = 0
    #             for image in collection:
    #                 dst_file_num = frame_start + index
    #                 dst_file_name = "".join([
    #                     str(event_number),
    #                     head,
    #                     str(padding % dst_file_num),
    #                     tail
    #                 ])
    #                 src = os.path.join(staging_dir, image)
    #                 dst = os.path.join(full_output_dir, dst_file_name)
    #                 self.log.info("Creating temp hardlinks: {}".format(dst))
    #                 self.hardlink_file(src, dst)
    #                 new_files.append(dst_file_name)
    #                 index += 1
    #
    #             self.log.debug("_ new_files: {}".format(new_files))
    #
    #         else:
    #             # ffmpeg when single file
    #             new_files = "{}_{}".format(asset, files)
    #
    #             # frame range
    #             frame_start = repre.get("frameStart")
    #             frame_end = repre.get("frameEnd")
    #
    #             full_input_path = os.path.join(
    #                 staging_dir, files)
    #
    #             os.path.isdir(full_output_dir) or os.makedirs(full_output_dir)
    #
    #             full_output_path = os.path.join(
    #                 full_output_dir, new_files)
    #
    #             self.log.debug(
    #                 "__ full_input_path: {}".format(full_input_path))
    #             self.log.debug(
    #                 "__ full_output_path: {}".format(full_output_path))
    #
    #             # check if audio stream is in input video file
    #             ffprob_cmd = (
    #                 "\"{ffprobe_path}\" -i \"{full_input_path}\" -show_streams"
    #                 " -select_streams a -loglevel error"
    #             ).format(**locals())
    #
    #             self.log.debug("ffprob_cmd: {}".format(ffprob_cmd))
    #             audio_check_output = pype.api.subprocess(ffprob_cmd)
    #             self.log.debug(
    #                 "audio_check_output: {}".format(audio_check_output))
    #
    #             # Fix one frame difference
    #             """ TODO: this is just work-around for issue:
    #                       https://github.com/pypeclub/pype/issues/659
    #             """
    #             frame_duration_extend = 1
    #             if audio_check_output:
    #                 frame_duration_extend = 0
    #
    #             # translate frame to sec
    #             start_sec = float(frame_start) / fps
    #             duration_sec = float(
    #                 (frame_end - frame_start) + frame_duration_extend) / fps
    #
    #             empty_add = None
    #
    #             # check if not missing frames at start
    #             if (start_sec < 0) or (media_duration < frame_end):
    #                 # for later swithing off `-c:v copy` output arg
    #                 empty_add = True
    #
    #                 # init empty variables
    #                 video_empty_start = video_layer_start = ""
    #                 audio_empty_start = audio_layer_start = ""
    #                 video_empty_end = video_layer_end = ""
    #                 audio_empty_end = audio_layer_end = ""
    #                 audio_input = audio_output = ""
    #                 v_inp_idx = 0
    #                 concat_n = 1
    #
    #                 # try to get video native resolution data
    #                 try:
    #                     resolution_output = pype.api.subprocess((
    #                         "\"{ffprobe_path}\" -i \"{full_input_path}\""
    #                         " -v error "
    #                         "-select_streams v:0 -show_entries "
    #                         "stream=width,height -of csv=s=x:p=0"
    #                     ).format(**locals()))
    #
    #                     x, y = resolution_output.split("x")
    #                     resolution_width = int(x)
    #                     resolution_height = int(y)
    #                 except Exception as _ex:
    #                     self.log.warning(
    #                         "Video native resolution is untracable: {}".format(
    #                             _ex))
    #
    #                 if audio_check_output:
    #                     # adding input for empty audio
    #                     input_args.append("-f lavfi -i anullsrc")
    #
    #                     # define audio empty concat variables
    #                     audio_input = "[1:a]"
    #                     audio_output = ":a=1"
    #                     v_inp_idx = 1
    #
    #                 # adding input for video black frame
    #                 input_args.append((
    #                     "-f lavfi -i \"color=c=black:"
    #                     "s={resolution_width}x{resolution_height}:r={fps}\""
    #                 ).format(**locals()))
    #
    #                 if (start_sec < 0):
    #                     # recalculate input video timing
    #                     empty_start_dur = abs(start_sec)
    #                     start_sec = 0
    #                     duration_sec = float(frame_end - (
    #                         frame_start + (empty_start_dur * fps)) + 1) / fps
    #
    #                     # define starting empty video concat variables
    #                     video_empty_start = (
    #                         "[{v_inp_idx}]trim=duration={empty_start_dur}[gv0];"  # noqa
    #                     ).format(**locals())
    #                     video_layer_start = "[gv0]"
    #
    #                     if audio_check_output:
    #                         # define starting empty audio concat variables
    #                         audio_empty_start = (
    #                             "[0]atrim=duration={empty_start_dur}[ga0];"
    #                         ).format(**locals())
    #                         audio_layer_start = "[ga0]"
    #
    #                     # alter concat number of clips
    #                     concat_n += 1
    #
    #                 # check if not missing frames at the end
    #                 if (media_duration < frame_end):
    #                     # recalculate timing
    #                     empty_end_dur = float(
    #                         frame_end - media_duration + 1) / fps
    #                     duration_sec = float(
    #                         media_duration - frame_start) / fps
    #
    #                     # define ending empty video concat variables
    #                     video_empty_end = (
    #                         "[{v_inp_idx}]trim=duration={empty_end_dur}[gv1];"
    #                     ).format(**locals())
    #                     video_layer_end = "[gv1]"
    #
    #                     if audio_check_output:
    #                         # define ending empty audio concat variables
    #                         audio_empty_end = (
    #                             "[0]atrim=duration={empty_end_dur}[ga1];"
    #                         ).format(**locals())
    #                         audio_layer_end = "[ga0]"
    #
    #                     # alter concat number of clips
    #                     concat_n += 1
    #
    #                 # concatting black frame togather
    #                 output_args.append((
    #                     "-filter_complex \""
    #                     "{audio_empty_start}"
    #                     "{video_empty_start}"
    #                     "{audio_empty_end}"
    #                     "{video_empty_end}"
    #                     "{video_layer_start}{audio_layer_start}[1:v]{audio_input}"  # noqa
    #                     "{video_layer_end}{audio_layer_end}"
    #                     "concat=n={concat_n}:v=1{audio_output}\""
    #                 ).format(**locals()))
    #
    #             # append ffmpeg input video clip
    #             input_args.append("-ss {:0.2f}".format(start_sec))
    #             input_args.append("-t {:0.2f}".format(duration_sec))
    #             input_args.append("-i \"{}\"".format(full_input_path))
    #
    #             # add copy audio video codec if only shortening clip
    #             if ("_cut-bigger" in tags) and (not empty_add):
    #                 output_args.append("-c:v copy")
    #
    #             # make sure it is having no frame to frame comprassion
    #             output_args.append("-intra")
    #
    #             # output filename
    #             output_args.append("-y \"{}\"".format(full_output_path))
    #
    #             mov_args = [
    #                 "\"{}\"".format(ffmpeg_path),
    #                 " ".join(input_args),
    #                 " ".join(output_args)
    #             ]
    #             subprcs_cmd = " ".join(mov_args)
    #
    #             # run subprocess
    #             self.log.debug("Executing: {}".format(subprcs_cmd))
    #             output = pype.api.subprocess(subprcs_cmd)
    #             self.log.debug("Output: {}".format(output))
    #
    #         repre_new = {
    #             "files": new_files,
    #             "stagingDir": full_output_dir,
    #             "frameStart": frame_start,
    #             "frameEnd": frame_end,
    #             "frameStartFtrack": frame_start,
    #             "frameEndFtrack": frame_end,
    #             "step": 1,
    #             "fps": fps,
    #             "name": "cut_up_preview",
    #             "tags": ["review"] + self.tags_addition,
    #             "ext": ext,
    #             "anatomy_template": "publish"
    #         }
    #
    #         representations_new.append(repre_new)
    #
    #     for repre in representations_new:
    #         if ("delete" in repre.get("tags", [])) and (
    #                 "cut_up_preview" not in repre["name"]):
    #             representations_new.remove(repre)
    #
    #     self.log.debug(
    #         "Representations: {}".format(representations_new))
    #     instance.data["representations"] = representations_new
    #
    # def hardlink_file(self, src, dst):
    #     dirname = os.path.dirname(dst)
    #
    #     # make sure the destination folder exist
    #     try:
    #         os.makedirs(dirname)
    #     except OSError as e:
    #         if e.errno == errno.EEXIST:
    #             pass
    #         else:
    #             self.log.critical("An unexpected error occurred.")
    #             six.reraise(*sys.exc_info())
    #
    #     # create hardlined file
    #     try:
    #         filelink.create(src, dst, filelink.HARDLINK)
    #     except OSError as e:
    #         if e.errno == errno.EEXIST:
    #             pass
    #         else:
    #             self.log.critical("An unexpected error occurred.")
    #             six.reraise(*sys.exc_info())
    #
    # def create_representation(self, otio_clip, to_otio_range, instance):
    #     to_tl_start, to_tl_end = pype.lib.otio_range_to_frame_range(
    #         to_otio_range)
    #     tl_start, tl_end = pype.lib.otio_range_to_frame_range(
    #         otio_clip.range_in_parent())
    #     source_start, source_end = pype.lib.otio_range_to_frame_range(
    #         otio_clip.source_range)
    #     media_reference = otio_clip.media_reference
    #     metadata = media_reference.metadata
    #     mr_start, mr_end = pype.lib.otio_range_to_frame_range(
    #         media_reference.available_range)
    #     path = media_reference.target_url
    #     reference_frame_start = (mr_start + source_start) + (
    #         to_tl_start - tl_start)
    #     reference_frame_end = (mr_start + source_end) - (
    #         tl_end - to_tl_end)
    #
    #     base_name = os.path.basename(path)
    #     staging_dir = os.path.dirname(path)
    #     ext = os.path.splitext(base_name)[1][1:]
    #
    #     if metadata.get("isSequence"):
    #         files = list()
    #         padding = metadata["padding"]
    #         base_name = pype.lib.convert_to_padded_path(base_name, padding)
    #         for index in range(
    #                 reference_frame_start, (reference_frame_end + 1)):
    #             file_name = base_name % index
    #             path_test = os.path.join(staging_dir, file_name)
    #             if os.path.exists(path_test):
    #                 files.append(file_name)
    #
    #         self.log.debug(files)
    #     else:
    #         files = base_name
    #
    #     representation = {
    #         "ext": ext,
    #         "name": ext,
    #         "files": files,
    #         "frameStart": reference_frame_start,
    #         "frameEnd": reference_frame_end,
    #         "stagingDir": staging_dir
    #     }
    #     self.log.debug(representation)
