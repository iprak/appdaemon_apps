import appdaemon.plugins.hass.hassapi as hass
from PIL import Image

#
# CameraPhotoNotifier: App to send picture notifications when motion is detected or when door is opened.
#
#   Args:
#       camera = Camera entity for taking snapshot
#       binary_sensor = The camera motion sensor
#
# GaragePhotoNotifier: App to sent notification when garage door is opened, motion is detected in the garage
#       and the door to garage is still closed. Detection is disabled once the door to garage is opened.
#
#   Args:
#       camera = Garage camera entity for taking snapshot
#       motion_sensor = Garage camera motion sensor
#       binary_sensor = The motion sensor
#       door_to_garage = Door to garage sensor
#       garage_door = Garage door sensor


NUMBER_OF_PICTURES = 3
DELAY_BETWEN_PHOTOS = 1
BORDER_WIDTH = 5
DELAY_RETRY_BUILD_COMPISTE_FAILURE = 1


class PhotoNotifier(hass.Hass):
    """Base class for capturing images and sending notification."""

    def initialize(self, message, camera):
        self._message = message
        self._camera = camera
        self._camera_name = camera.split(".")[1]

        self._processing_event = False
        self._picture_counter = 0
        self._file_paths = []
        self._combined_path = "/config/media/{0}-Combined.jpg".format(self._camera_name)

    def start_taking_photos(self):
        """Start capturing pictures."""
        if self._processing_event:
            self.log("Processing previous event")
        else:
            # self.log("motion_detected")
            self._processing_event = True
            self._picture_counter = 0
            self._file_paths = []
            self.take_picture_or_notify({})

    def take_picture_or_notify(self, kwargs):
        """Take another picture or send notification."""
        if self._picture_counter < NUMBER_OF_PICTURES:
            self._picture_counter = self._picture_counter + 1
            self.take_picture()
            self.run_in(
                self.take_picture_or_notify,
                DELAY_BETWEN_PHOTOS,
            )
        else:
            self.process_pictures({})

    def process_pictures(self, kwargs):
        retry = kwargs.get("retry", False)

        try:
            self.build_composite_image()
            self.send_notification()
            self._processing_event = False
        except (FileNotFoundError):
            # Retry if not already in a retry
            if not retry:
                self.log("Retrying process_pictures (%s)", self._camera)

                self.run_in(
                    self.process_pictures,
                    DELAY_RETRY_BUILD_COMPISTE_FAILURE,
                    retry=True,
                )

    def send_notification(self):
        """Send notification."""
        self.call_service(
            "notify/mybot",
            message=self._message,
            data={"photo": [{"caption": self._message, "file": self._combined_path}]},
        )
        self.log("sent notification")

    def take_picture(self):
        """Take a picture."""
        file = "/config/media/{0}-{1}.jpg".format(
            self._camera_name, self._picture_counter
        )
        self._file_paths.append(file)
        self.call_service("camera/snapshot", entity_id=self._camera, filename=file)

    def build_composite_image(self):
        images = [Image.open(x) for x in self._file_paths]
        widths, heights = zip(*(i.size for i in images))

        total_height = sum(heights) + (NUMBER_OF_PICTURES * BORDER_WIDTH * 2)
        max_width = max(widths) + (BORDER_WIDTH * 2)
        new_im = Image.new("RGB", (max_width, total_height), "black")

        y_offset = BORDER_WIDTH
        for im in images:
            new_im.paste(im, (BORDER_WIDTH, y_offset))
            y_offset += im.size[1] + (2 * BORDER_WIDTH)

        new_im.save(self._combined_path)


class CameraPhotoNotifier(PhotoNotifier):
    """Class for sending image notification when motion is detected."""

    def initialize(self):
        camera = self.args["camera"]
        name = camera.split(".")[1]

        PhotoNotifier.initialize(self, "Motion detected on {0}".format(name), camera)
        self.log("Monitoring %s (%s)", self.args["binary_sensor"], camera)

        self.listen_state(
            self.motion_detected,
            self.args["binary_sensor"],
            new="on",
        )

        # For testing
        # self.start_taking_photos()

    def motion_detected(self, entity, attribute, old, new, kwargs):
        #self.log(
        #    "motion_detected on %s old=%s new=%s", self.args["binary_sensor"], old, new
        #)
        self.start_taking_photos()


class GaragePhotoNotifier(PhotoNotifier):
    """Class for sending image notification when motion is detected after garage door is opened."""

    def initialize(self):
        self._motion_detected_handle = None

        camera = self.args["camera"]
        self._door_to_garage = self.args["door_to_garage"]
        self._motion_sensor = self.args["motion_sensor"]
        garage_door = self.args["garage_door"]

        PhotoNotifier.initialize(self, "Motion in garage", camera)

        # door_to_garage_last_changed = self.get_entity(self._door_to_garage).last_changed
        self.log(
            "Monitoring motion on %s (garage door %s)", self._motion_sensor, garage_door
        )

        self.listen_state(self.garage_opened, garage_door)
        self.listen_state(self.door_to_garage_changed, self._door_to_garage)

        # For testing
        # self.start_taking_photos()

    def door_to_garage_changed(self, entity, attribute, old, new, kwargs):
        # Stop motion detection when door to garage is opened
        if new == "on":
            self.stop_motion_detection()

    def garage_opened(self, entity, attribute, old, new, kwargs):
        if new == "closed":
            # Stop motion detection when garage is closed
            self.stop_motion_detection()
        else:
            # Open or opening
            if self.get_state(self._door_to_garage) == "off":
                self.log("Garage opened, door is closed, started watching for motion")

                self._motion_detected_handle = self.listen_state(
                    self.motion_detected,
                    self._motion_sensor,
                    new="on",
                )

    def motion_detected(self, entity, attribute, old, new, kwargs):
        self.log("motion_detected")
        self.start_taking_photos()

    def stop_motion_detection(self):
        if self._motion_detected_handle:
            self.log("stop_motion_detection")

            self.cancel_listen_state(self._motion_detected_handle)
            self._motion_detected_handle = None
