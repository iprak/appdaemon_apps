import appdaemon.plugins.hass.hassapi as hass
import datetime


class ResetSnoozedAlarms(hass.Hass):
    def initialize(self):
        self.log("Hello from ResetSnoozedAlarms")
        time = datetime.time(19, 30, 0)
        self.run_daily(self.daily_callback, time)
        # self.run_daily_callback()

    def daily_callback(self, kwargs=None):
        entity_list = self.get_state("group.snoozed_alarms", attribute="all")[
            "attributes"
        ]["entity_id"]
        for entity_id in entity_list:
            self.log("Setting %s to off", entity_id)
            self.set_state(entity_id, state="off")
