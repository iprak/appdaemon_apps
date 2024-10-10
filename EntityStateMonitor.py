"""Sends message if an entity has been in a particular state for specified duration."""
import hassapi as hass
from datetime import timedelta

CHECK_DURATION = 5


class EntityStateMonitor(hass.Hass):
    _check_timer = None

    def initialize(self):
        self._entity = self.args["entity"]

        duration_seconds = self.args["duration_seconds"]
        self._duration_delta = timedelta(seconds=duration_seconds)

        self._message = self.args["message"]
        self._state = self.args["state"]
        self.listen_state(self.state_changed, self._entity)

        self.log_notify(
            f"Monitoring {self._entity} for state='{self._state}' and duration={duration_seconds} seconds."
        )

        self.start_stop_check()

    def cancel_check_timer(self):
        """Cancel the recurring check timer."""
        if self._check_timer is not None:
            self.cancel_timer(self._check_timer)
            self._check_timer = None

    def check(self, kwargs):
        """
        Check if entity has been in the specified state for specified duration.
        Send notification and cancel the recurring check.
        """

        # Safety check
        if self._start is None:
            return

        now = self.datetime(True)
        if now >= (self._start + self._duration_delta):
            self.cancel_check_timer()
            self.send_notification()

    def start_stop_check(self):
        state = self.get_state(self._entity)

        if state == self._state:
            self.log_notify("measurement started")
            self._start = self.datetime(True)
            self._check_timer = self.run_every(self.check, "now", CHECK_DURATION)
        else:
            self._start = None
            self.cancel_check_timer()
            self.log_notify("measurement reset")

    def state_changed(self, entity, attribute, old, new, kwargs):
        self.start_stop_check()

    def send_notification(self):
        """Send a notification."""
        self.call_service(
            "notify/mybot",
            message=self._message,
        )
        self.log_notify("sent notification")

    def log_notify(self, message, level="INFO"):
        if "verbose_log" in self.args:
            self.log(message)
        if "notify" in self.args:
            self.notify(message, globals.notify, name=globals.notify)
