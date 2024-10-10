"""
The AsusWrt integration data resets when it reaches 4GB (https://github.com/home-assistant/core/issues/31404).

This app applies upload and download changes to another sensor which resets at midnight.

 Args:
    input_upload_sensor: AsusWrt upload sensor (default="sensor.asuswrt_upload")
    input_download_sensor: AsusWrt download sensor (default="sensor.asuswrt_download")
    output_download_sensor: Target upload sensor (default="sensor.daily_download")
    output_upload_sensor: Target download sensor (default="sensor.daily_upload")

"""
import hassapi as hass
import datetime


def convert_to_float(value) -> float:
    """Convert specified value to float."""
    try:
        return float(value)
    except:  # noqa: E722 pylint: disable=bare-except
        return 0


class AsusWrt(hass.Hass):
    def initialize(self):
        self._attributes = {
            "state_class": "measurement",
            "unit_of_measurement": "GB",
            "icon": "mdi:calculator",
        }

        self.verbose_log = self.args.get("verbose_log", False)
        self._upload_sensor = self.args.get("input_upload_sensor", "sensor.asuswrt_upload")
        self._download_sensor = self.args.get("input_download_sensor", "sensor.asuswrt_download")
        self._target_download_sensor = self.args.get("output_download_sensor", "sensor.daily_download")
        self._target_upload_sensor = self.args.get("output_upload_sensor", "sensor.daily_upload")

        self.listen_state(self.on_download_changed, self._download_sensor)
        self.listen_state(self.on_upload_changed, self._upload_sensor)

        midnight = datetime.time(0, 0, 0)
        self.run_daily(self.reset_sensor, midnight)

    def reset_sensor(self, kwargs):
        self.log("reset_sensor")
        self.set_state(self._target_upload_sensor, state=0)
        self.set_state(
            self._target_download_sensor,
            state=0,
        )

    def on_data_changed(self, entity, old, new, target_entity):
        old = convert_to_float(old)
        new = convert_to_float(new)

        if new > old:
            value = convert_to_float(self.get_state(target_entity))
            value = round(value + new - old, 2)

            self.set_state(
                target_entity,
                state=value,
            )
            # self.log(f"data_updated old={old} new={new} {target_entity} updated to {value}")
        else:
            value = convert_to_float(self.get_state(target_entity))
            self.log(f"data_updated old={old} new={new} no change to {target_entity} value remains {value}")

    def on_upload_changed(self, entity, attribute, old, new, kwargs):
        self.on_data_changed(entity, old, new, self._target_upload_sensor)

    def on_download_changed(self, entity, attribute, old, new, kwargs):
        self.on_data_changed(entity, old, new, self._target_download_sensor)
