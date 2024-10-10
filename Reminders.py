"""App to announce reminders based on calendar feed.

Sample output:
    "Robert: maths" will generate "Hello Robert, you have maths in 2 minutes."
    "Family zoom" will generate "Family zoom in 2 minutes."

 Args:
    feed: iCal feed url (required)
    alexa_devices: Alexa devices to send announcement
    google_devices: Google devices to send announcement
    reminder_sensor: sensor to update with next reminder details (required)
    fetch_interval: Minutes between calendar fetch (default = 10 minutes)
    reminder_offset: Minutes before the event for sending notification (default = 2 minutes)
    skip_days: Array of weekdays on which to skip reminders (default = Saturday, Sunday)
    skip_dates: Array of dates on which to skip reminders, the dates can be a range
    start_hour: starting hour for the day (default = 7 AM)
    end_hour: ending hour for the day (default = 8 PM)
    reminder_sensor_friendly_name: Friendly name of the reminder sensor (default = Reminder)

"""

import os
from datetime import date, datetime, timedelta

import adbase as ad
import hassapi as hass
import icalendar
import pytz
import recurring_ical_events
import requests
import AppUtils

DEFAULT_FETCH_INTERVAL = 10  # 10 minutes
DEFAULT_REMINDER_OFFSET = 2  # 2 minutes

DEFAULT_START_HOUR = 7  # 7 AM
DEFAULT_END_HOUR = 20  # 8 PM


class Reminders(hass.Hass):
    data_fetch_timer = None
    events = None  # Events for today
    scheduled_event_uids = None

    def tryLog(self, message):
        '''Conditionally log'''
        if "verbose_log" in self.args:
            self.log(message)

    def initialize(self):
        self.feed = self.args["feed"]
        self.alexa_devices = self.args.get("alexa_devices", [])
        self.google_devices = self.args.get("google_devices", [])
        self.no_reminder_today_sensor = self.args.get("no_reminder_today_sensor")
        self.reminder_sensor = self.args.get("reminder_sensor")
        self.reminder_sensor_friendly_name = self.args.get("reminder_sensor_friendly_name", "Reminder")
        self.fetch_interval = self.args.get("fetch_interval", DEFAULT_FETCH_INTERVAL)
        self.reminder_offset = self.args.get("reminder_offset", DEFAULT_REMINDER_OFFSET)
        self.skip_days = self.args.get("skip_days", AppUtils.DEFAULT_SKIP_DAYS)
        self.skip_dates = AppUtils.get_skip_dates(self.args.get("skip_dates"))
        self.start_hour = self.args.get("start_hour", DEFAULT_START_HOUR)
        self.end_hour = self.args.get("end_hour", DEFAULT_END_HOUR)

        # In test mode, data is downloaded once and saved to a local file "basic.ics" for future use.
        # No announcements are send. This mode can be combined with "time travel" flags for testing.
        # https://appdaemon.readthedocs.io/en/latest/INSTALL.html?highlight=Time%20Travel#appdaemon-arguments
        # e.g. appdaemon -c ~/appdaemon_config/ -s "2021-02-15 09:00:00" -t 5
        self.test_mode = self.args.get("test_mode", False)

        reminder_offset = self.reminder_offset
        if self.fetch_interval <= reminder_offset:
            raise Exception(
                f"fetch_interval '{self.fetch_interval}' should be more than reminder_offset '{reminder_offset}'."  # noqa: E501
            )

        # now = self.get_now()
        # localTZ = pytz.timezone(self.get_timezone())
        # self.log(now)
        # self.log(now.astimezone(localTZ))
        # This is the same as before
        self.tryLog(f"Initialized at {self.datetime(True)} skipping days {self.skip_days}")

        if self.test_mode:
            CURR_DIR = os.path.dirname(os.path.realpath(__file__))
            data_file = os.path.join(CURR_DIR, "basic.ics")

            if os.path.exists(data_file):
                f = open(data_file, "r")
                self.test_cached_feed_text = f.read()
                self.tryLog("Using cached data")

        self.events = {}
        self.scheduled_event_uids = []
        self.set_reminder_sensor("None", None)

        # Start listening to no_school input_boolean sensor
        if self.no_reminder_today_sensor:
            self.listen_state(self.no_school_status_changed, self.no_reminder_today_sensor)

        self.set_recurring_fetch()

    def is_no_reminder_today(self) -> bool:
        """Check if no school today."""
        if self.no_reminder_today_sensor:
            state = self.get_state(self.no_reminder_today_sensor)
            self.tryLog(f"is_no_reminder_today {state}")
            return state == "on"
        return False

    def no_school_status_changed(self, entity, attribute, old, new, kwargs):
        # Recalculate whenever no_reminder_today_sensor changes
        self.tryLog(f"{self.no_reminder_today_sensor} changed to {new} from {old}")

        # Cancel current callbacks and determine new fetch time
        self.cancel_reminders()
        self.cancel_recurring_fetch()
        self.set_reminder_sensor("None", None)

        self.set_recurring_fetch()

    def get_current_instant(self):
        # now = datetime.now()
        now = self.datetime(True)
        return now

    def terminate(self):
        self.cancel_reminders()
        self.cancel_recurring_fetch()

    def cancel_recurring_fetch(self):
        """Cancel the recurring fetch timer."""
        if self.data_fetch_timer is not None:
            self.cancel_timer(self.data_fetch_timer)
            self.data_fetch_timer = None

    def set_recurring_fetch(self):
        """Set the recurring fetch timer."""
        next_fetch_at = self.get_fetch_starting(self.get_current_instant())
        run_once_now = False

        if isinstance(next_fetch_at, str):
            next_fetch_at_str = f"Will check {next_fetch_at}"
            run_once_now = next_fetch_at == "now"
        else:
            next_fetch_at_str = f"Will check at {next_fetch_at.strftime('%-I:%M %p %-m/%-d/%y')}"

        # Cancel previous reminders since we might not fetch data right away
        # self.cancel_reminders()
        if self.test_mode:
            self.tryLog(next_fetch_at_str)
        else:
            self.set_state(
                self.reminder_sensor,
                state=next_fetch_at_str,
                attributes={"friendly_name": self.reminder_sensor_friendly_name},
            )

        self.tryLog(f"Scheduled recurring fetch starting '{next_fetch_at}'")

        self.data_fetch_timer = self.run_every(self.fetch_data, next_fetch_at, self.fetch_interval * 60)
        if run_once_now:
            self.fetch_data()

    def get_fetch_starting(self, start_time):
        """Returns when to begin data fetch based on the start_time."""

        # School starts remind_at 8:15 AM and ends around 4 PM
        today = start_time.date()
        day_delta = timedelta(days=1)

        start_date = today
        while True:
            weekday = start_date.weekday()

            if weekday in self.skip_days:
                start_date += day_delta
                continue

            if start_date in self.skip_dates:
                start_date += day_delta
                continue

            if start_date == today:
                if self.is_no_reminder_today():
                    start_date += day_delta
                    continue

                hour = start_time.hour

                # If before START_HOUR, then event_start at START_HOUR
                if hour < self.start_hour:
                    return start_time.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
                else:
                    # If after END_HOUR, then event_start tomorrow
                    if hour >= self.end_hour:
                        start_date += day_delta
                        continue
                    else:
                        break

            else:  # We found a valid date, set time
                return datetime(
                    year=start_date.year,
                    month=start_date.month,
                    day=start_date.day,
                    hour=self.start_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

        return "now"

    @ad.app_lock
    def fetch_data(self, kwargs=None):
        """Fetches new Calendar data"""

        localTZ = pytz.timezone(self.get_timezone())
        current_time = self.get_current_instant()

        self.tryLog(f"[{current_time}] fetch_data")

        if current_time.hour >= self.end_hour:  # If after end hour, adjust next fetch
            self.cancel_reminders()
            self.cancel_recurring_fetch()
            self.set_recurring_fetch()
            return

        try:
            if self.test_mode and self.test_cached_feed_text:
                feed_text = self.test_cached_feed_text
                self.tryLog("Using cached feed text")
            else:
                feed_text = requests.get(self.feed).text
                # self.tryLog(feed_text)

                if self.test_mode:
                    self.test_cached_feed_text = feed_text
        except Exception as error:
            self.tryLog(f"Error getting calendar feed {error}")
            return

        # recurring_ical_events supports recurring events
        calendar = icalendar.Calendar.from_ical(feed_text)

        for event in calendar.walk():
            if isinstance(event, icalendar.cal.Event):
                event_start_dt = event["DTSTART"].dt

                # Fix event_start_dt to be datetime
                if (not isinstance(event_start_dt, datetime)) and isinstance(event_start_dt, date):
                    # self.log(f'{event_start_dt} {event["SUMMARY"]} dateOnly')
                    event_start_dt = datetime(
                        year=event_start_dt.year,
                        month=event_start_dt.month,
                        day=event_start_dt.day,
                        tzinfo=localTZ,
                    )
                    # self.tryLog(f'Fixed {event["SUMMARY"]} to {event_start_dt}')
                    event["DTSTART"].dt = event_start_dt

        # Always fetch from starting time
        start_time = current_time.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        end_time = start_time.replace(hour=self.end_hour)

        reminder_state_set = False
        self.tryLog(f"Getting events between {start_time} - {end_time}")
        events = recurring_ical_events.of(calendar).between(start_time, end_time)
        events.sort(key=Reminders.get_starttime)

        self.tryLog(f"Found {len(events)} events")

        for event in events:
            summary = event["SUMMARY"]
            event_start = event["DTSTART"].dt
            UID = event["UID"]

            # event_start can sometime in UTC, convert it to local for comparison
            event_start = event_start.astimezone(localTZ)
            self.tryLog(f"{summary} @ {event_start} {UID}")

            if UID in self.events:
                if not self.events[UID]["done"]:
                    # if event time changed, then cancel current timer
                    if self.events[UID]["start"] != event_start:
                        self.cancel_timer(self.events[UID]["timer_id"])

                        self.events[UID]["scheduled"] = False
                        self.events[UID]["timer_id"] = None

            else:
                self.events[UID] = {
                    "done": False,
                    "scheduled": False,
                    "start": event_start,
                    "summary": summary,
                    "timer_id": None,
                }

            if self.events[UID]["done"]:
                self.tryLog(f"{UID} done")
                continue

            if self.events[UID]["scheduled"]:
                self.tryLog(f"{UID} scheduled")
                reminder_state_set = True
                continue

            if current_time <= event_start:
                # Schedule a reminder task 2 min before it starts
                remind_at = event_start + timedelta(minutes=-self.reminder_offset)
                remind_time = remind_at.time()
                message = Reminders.get_announcement(summary, self.reminder_offset)
                reminder_sensor_state = f"{message} @{remind_time.strftime('%-I:%M %p')}"

                if current_time < remind_at:
                    self.tryLog(f"Scheduling '{message}' at {remind_time}")

                    # run_once schedules a task for today
                    timer_id = self.run_once(self.remind, remind_time, message=message, UID=UID)

                    self.events[UID]["scheduled"] = True
                    self.events[UID]["timer_id"] = timer_id
                    self.events[UID]["sensor_state"] = reminder_sensor_state
                    self.scheduled_event_uids.append(UID)

                    if not reminder_state_set:
                        reminder_state_set = True
                        self.set_reminder_sensor(reminder_sensor_state, UID)
                else:
                    # Send reminder right away if we have passed reminder_offset period (this would
                    # be probably due to app restart). But if there is a reminder scheduled and data
                    # was reloaded in that 2 minute period, then don't send another reminder right away.

                    if self.get_reminder_sensor_UID() != UID:
                        self.tryLog(f'Sending reminder right away "{reminder_sensor_state} {UID}"')
                        self.remind({"message": message, "UID": UID})
            else:
                self.tryLog(f"Event '{summary}' has passed")
                self.events[UID]["done"] = True
                self.events[UID]["scheduled"] = False

        # No reminder, clear the sensor
        if not reminder_state_set:
            self.set_reminder_sensor("None", None)

    def get_reminder_sensor_UID(self):
        """Get the UID associated with the current reminder."""
        state = self.get_state(self.reminder_sensor, attribute="all")
        if state is not None:
            return state["attributes"]["UID"]
        return None

    def set_reminder_sensor(self, state, UID):
        """Update the reminder_sensor."""
        self.set_state(
            self.reminder_sensor,
            state=state,
            attributes={
                "friendly_name": self.reminder_sensor_friendly_name,
                "UID": UID,
            },
        )

    @ad.app_lock
    def remind(self, kwargs):
        """Invoke services to send reminder notifications. This also updates events structure."""

        message = kwargs["message"]
        UID = kwargs["UID"]

        self.events[UID]["done"] = True
        self.events[UID]["scheduled"] = False
        self.events[UID]["timer_id"] = None

        reminder_state = "None"

        if self.scheduled_event_uids:
            # The first item in scheduled_event_uids should be UID
            self.scheduled_event_uids.pop(0)

            if self.scheduled_event_uids:
                next_UID = self.scheduled_event_uids[0]
                reminder_state = self.events[next_UID]["sensor_state"]

        self.tryLog(f"Announcing '{message}', next '{reminder_state}'")

        if self.test_mode:
            return

        self.call_service("notify/mybot", message=message)

        try:
            for device in self.alexa_devices:
                self.call_service(
                    "notify/alexa_media",
                    target=device,
                    data={"type": "announce"},
                    message=message,
                )
        except Exception as e:
            self.tryLog(f"Error invoking alexa_devices. {e}")

        try:
            for device in self.google_devices:
                self.call_service("tts/google_say", entity_id=device, 
                                  message=message)
        except Exception as e:
            self.tryLog(f"Error invoking google_devices. {e}")

        self.set_state(
            self.reminder_sensor,
            state=reminder_state,
            attributes={"friendly_name": self.reminder_sensor_friendly_name},
        )

    def cancel_reminders(self):
        """Cancel all scheduled reminders"""

        if self.events:
            self.tryLog("Cancelling current reminders")

            for UID in self.events:
                if self.events[UID]["timer_id"] is not None:
                    self.tryLog(f"Cancelling reminder for {UID}")
                    self.cancel_timer(self.events[UID]["timer_id"])

        self.events = {}
        self.scheduled_event_uids = []

    @staticmethod
    def get_announcement(message, reminder_offset):
        """
        Generates the announcement message

        :param str message: Message about the event
        :param number reminder_offset: Minutes in which event is about to happen
        """

        if reminder_offset == 0:
            return message
        
        pos = message.find(":")
        if pos == -1:
            activity = message.strip()
            message = f"{activity} in {reminder_offset} minutes."
        else:
            activity = message[(pos + 1) :].strip()  # noqa: E203
            person = message[0:pos].strip()
            message = f"Hello {person}, you have {activity} in {reminder_offset} minutes."

        return message

    @staticmethod
    def get_starttime(event):
        """Delegate for sorting Calendar entries by event_start time."""
        return event["DTSTART"].dt
