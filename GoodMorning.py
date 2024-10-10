"""App to update entities to on/off state daily based on days and dates to skip.

 Args:
    boolean_entity: Boolean entity to be updated.
    skip_days: Array of weekdays when automations are turned off.
    skip_dates: Array of dates on which when automations are turned off.

"""

import copy
from datetime import datetime, timedelta
import hassapi as hass
import AppUtils


class GoodMorning(hass.Hass):
    check_daily_timer = None

    def initialize(self):
        self.boolean_entity = self.args["boolean_entity"]
        self.override_boolean_entity = self.args["override_boolean_entity"]
        self.skip_days = self.args.get("skip_days", AppUtils.DEFAULT_SKIP_DAYS)
        self.skip_dates = AppUtils.get_skip_dates(self.args.get("skip_dates"))

        # Run daily at 5 AM
        self.check_daily_timer = self.run_daily(self.check, "05:00:00")
        self.log(f"Initialized at {self.datetime(True)} skipping days {self.skip_days}")

        if self.override_boolean_entity:
            self.listen_state(self.override_boolean_entity_changed, self.override_boolean_entity)

        self.check()

    def terminate(self):
        """Cancel all timers"""
        self.cancel_daily_check()

    def cancel_daily_check(self):
        if self.check_daily_timer is not None:
            self.cancel_timer(self.check_daily_timer)
            self.check_daily_timer = None

    def override_boolean_entity_changed(self, entity, attribute, old, new, kwargs):
        # Recalculate whenever boolean_entity sensor changes
        self.log(f"{self.override_boolean_entity} changed to '{new}' from '{old}'")
        self.check()

    def check(self, kwargs=None):
        override_state = self.get_state(self.override_boolean_entity)
        self.log(f"override_state is '{override_state}'")

        if override_state == "on":
            self.update_entity("on")
        else:
            today = self.date()
            weekday = today.weekday()

            if (weekday in self.skip_days) or (today in self.skip_dates):
                self.update_entity("on")
            else:
                self.update_entity("off")

    def update_entity(self, state):
        entity = self.boolean_entity
        current_state = self.get_state(entity)
        if current_state != state:
            self.log(f"Updating '{entity}' to '{state}'")

            # Maintain existing attributes
            attributes = self.get_state(entity, attribute="all")["attributes"]
            self.set_state(entity, state=state, attributes=attributes)
        else:
            self.log(f"'{entity}' is already '{state}'")
