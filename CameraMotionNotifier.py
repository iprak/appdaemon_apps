import appdaemon.plugins.hass.hassapi as hass
from datetime import date, datetime, timedelta

#Successfully installed numpy-1.21.2 opencv-python-headless-4.5.2.54
import numpy as np
import cv2 as cv

# import numpy

#
# App to send notification when motion is detected
#
# Args:
#
# camera = Camera entity for taking snapshot
# binary_sensor = The motion sensor
# message_prefix = Message prefix
#

__NUMBER_OF_PICTURES__ = 3
__DELAY_BETWEN_PICTURES__ = 2
__VIDEO_CAPTURE_WAIT_DELAY__ = 3
__VIDEO_DURATION__ = 3
__VIDEO_LOOKBACK_DURATION__ = 2

RTSP_URL = "rtsp://hass:xdxW%25W8^Pg8o@192.168.1.59:554/Streaming/Channels/102/"


class CameraMotionNotifier(hass.Hass):
    def initialize(self):
        self.camera_name = "front"
        self.record_video()

    def record_video(self):
        file = "/media/{0}-{1}.mp4".format(
            self.camera_name, self.datetime(True).strftime("%Y%m%d-%H%M%S")
        )
        self.log("recording to file=%s", file)
        cap = cv.VideoCapture(RTSP_URL, cv.CAP_FFMPEG)

        source = av.open(
            RTSP_URL,
            metadata_encoding="utf-8",
        )
        output = av.open(file, mode="w", format="h264")

        in_to_out = {}

        for i, stream in enumerate(source.streams):

            if (
                (stream.type == "audio")
                or (stream.type == "video")
                or (stream.type == "subtitle")
                or (stream.type == "data")
            ):
                in_to_out[stream] = ostream = output.add_stream(template=stream)
                ostream.options = {}

        count = 0
        for i, packet in enumerate(source.demux()):
            try:
                if packet.dts is None:
                    continue

                packet.stream = in_to_out[packet.stream]
                output.mux(packet)
                count += 1
                if count > 200:
                    break

            except InterruptedError:
                output.close()
                break

        output.close()
