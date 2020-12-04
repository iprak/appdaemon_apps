"""App to announce reminders based on calendar feed.

Samples:
    "Robert: maths" will generate the notification "Hello Robert, you have maths in 2 minutes."
    "Family zoom" will generate the notification "Family zoom in 2 minutes."

 Args:
    feed: iCal feed url (required)
    alexa_devices: Alexa devices to send announcement
    google_devices: Google devices to send announcement
    reminder_sensor: sensor to update with next reminder details (required)
    fetch_interval: Minutes between calendar fetch (default = 10 minutes)
    reminder_offset: Minutes before the event for sending notification (default = 2 minutes)
    skip_days: Array of weekdays on which to skip reminders (default = Saturday, Sunday)
    skip_dates: Array of dates on which to skip reminders
    start_hour: starting hour for the day (default = 8 AM)
    end_hour: ending hour for the day (default = 4 PM)

"""

import os
from datetime import datetime, timedelta

import adbase as ad
import hassapi as hass
import icalendar
import pytz
import recurring_ical_events
import requests


DEFAULT_FETCH_INTERVAL = 10  # 10 minutes
DEFAULT_REMINDER_OFFSET = 2  # 2 minutes

DEFAULT_SKIP_DAYS = [5, 6]  # Saturday and Sunday
DEFAULT_START_HOUR = 8  # 8 AM
DEFAULT_END_HOUR = 16  # 4 PM


class Reminders(hass.Hass):
    data_fetch_timer = None
    events = None  # Events for today
    scheduled_event_uids = None

    def initialize(self):
        self.feed = self.args["feed"]
        self.alexa_devices = self.args.get("alexa_devices")
        self.google_devices = self.args.get("google_devices")
        self.reminder_sensor = self.args.get("reminder_sensor")
        self.fetch_interval = self.args.get(
            "fetch_interval", DEFAULT_FETCH_INTERVAL
        )
        self.reminder_offset = self.args.get(
            "reminder_offset", DEFAULT_REMINDER_OFFSET
        )
        self.skip_days = self.args.get("skip_days", DEFAULT_SKIP_DAYS)
        self.skip_dates = get_static_skip_dates(self.args.get("skip_dates"))
        self.start_hour = self.args.get("start_hour", DEFAULT_START_HOUR)
        self.end_hour = self.args.get("end_hour", DEFAULT_END_HOUR)

        # In test mode, data is downloaded once and saved to a local file "basic.ics" for future use.
        # No announcements are send. This mode can be combined with "time travel" flags for testing.
        # https://appdaemon.readthedocs.io/en/latest/INSTALL.html?highlight=Time%20Travel#appdaemon-arguments
        self.test_mode = self.args.get("test_mode", False)

        if self.fetch_interval <= self.reminder_offset:
            raise Exception(
                f"fetch_interval '{self.fetch_interval}' should be more than reminder_offset '{self.reminder_offset}'."
            )

        # now = self.get_now()
        # localTZ = pytz.timezone(self.get_timezone())
        # self.log(now)
        # self.log(now.astimezone(localTZ))
        # This is the same as before
        self.log(
            f"Initialized at {self.datetime(True)} skipping days {self.skip_days}"
        )

        if self.test_mode:
            CURR_DIR = os.path.dirname(os.path.realpath(__file__))
            data_file = os.path.join(CURR_DIR, "basic.ics")

            if os.path.exists(data_file):
                f = open(data_file, "r")
                self.test_cached_feed_text = f.read()
                self.log("Read cached data")

        self.events = {}
        self.scheduled_event_uids = []

        self.set_recurring_fetch()

    def get_current_instant(self):
        # now = datetime.now()
        now = self.datetime(True)
        return now

    def terminate(self):
        self.cancel_reminders()
        self.cancel_recurring_fetch()

    def cancel_recurring_fetch(self):
        """Cancel the recurring fetch timer"""
        if self.data_fetch_timer is not None:
            self.cancel_timer(self.data_fetch_timer)
            self.data_fetch_timer = None

    def set_recurring_fetch(self):
        """Set the recurring fetch timer"""
        next_fetch_at = self.get_fetch_starting(self.get_current_instant())

        # Cancel previous reminders since we might not fetch data right away
        # self.cancel_reminders()
        self.set_state(
            self.reminder_sensor,
            state="None",
            attributes={"friendly_name": "School reminder"},
        )

        # self.log(
        #    f"Scheduled recurring fetch starting '{next_fetch_at}', reminder_sensor reset"
        # )
        self.data_fetch_timer = self.run_every(
            self.fetch_data, next_fetch_at, self.fetch_interval * 60
        )

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
                hour = start_time.hour

                # If before START_HOUR, then event_start at START_HOUR
                if hour < self.start_hour:
                    return start_time.replace(
                        hour=self.start_hour, minute=0, second=0, microsecond=0
                    )
                else:
                    # If after 4 PM, then event_start tomorrow
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
        # current_time = localTZ.localize(self.get_current_instant())
        current_time = self.get_current_instant()

        if (
            current_time.hour >= self.end_hour
        ):  # If after 4 PM, adjust next fetch
            self.cancel_recurring_fetch()
            self.set_recurring_fetch()
            return

        # Always fetch from school starting time
        start_time = current_time.replace(
            hour=self.start_hour, minute=0, second=0, microsecond=0
        )
        end_time = start_time.replace(hour=self.end_hour)

        self.log(f"[{current_time}]")

        try:
            if self.test_mode and self.test_cached_feed_text:
                feed_text = self.test_cached_feed_text
                self.log("Using cached feed text")
            else:
                feed_text = requests.get(self.feed).text

                if self.test_mode:
                    self.test_cached_feed_text = feed_text
        except () as error:
            self.log(f"Error getting calendar feed {error}")
            return

        # recurring_ical_events supports recurring events
        calendar = icalendar.Calendar.from_ical(feed_text)

        reminder_state_set = False
        events = recurring_ical_events.of(calendar).between(
            start_time, end_time
        )
        events.sort(key=get_starttime)

        self.log(f"Found {len(events)} events from {start_time} - {end_time}")

        for event in events:
            summary = event["SUMMARY"]
            event_start = event["DTSTART"].dt
            UID = event["UID"]

            # event_start can sometime in UTC, convert it to local for comparison
            event_start = event_start.astimezone(localTZ)
            # self.log(f"{summary} @ {event_start}")

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
                continue
            if self.events[UID]["scheduled"]:
                reminder_state_set = True
                continue

            if current_time <= event_start:
                # Schedule a reminder task 2 min before it starts
                remind_at = event_start + timedelta(
                    minutes=-self.reminder_offset
                )
                remind_time = remind_at.time()
                message = get_announcement(summary, self.reminder_offset)
                reminder_sensor_state = f"{message} [{remind_time}]"

                if current_time < remind_at:
                    # self.log(f"Scheduling '{message}' at {remind_time}")

                    # run_once schedules a task for today
                    timer_id = self.run_once(
                        self.remind, remind_time, message=message, UID=UID
                    )
                    self.events[UID]["scheduled"] = True
                    self.events[UID]["timer_id"] = timer_id
                    self.events[UID]["sensor_state"] = reminder_sensor_state
                    self.scheduled_event_uids.append(UID)

                    if not reminder_state_set:
                        reminder_state_set = True
                        self.set_state(
                            self.reminder_sensor,
                            state=reminder_sensor_state,
                            attributes={"friendly_name": "School reminder"},
                        )
                else:
                    # Send reminder right away if we have passed reminder_offset period (probably due to app restart).
                    # But if there is a reminder scheduled and data was reloaded in that 2 minute period, then don't send
                    # another reminder right away.
                    if (
                        self.get_state(self.reminder_sensor)
                        != reminder_sensor_state
                    ):
                        self.log(
                            f'Sending reminder right away "{reminder_sensor_state}"'
                        )
                        self.remind({"message": message, "UID": UID})
            else:
                self.log(f"Event '{summary}' has passed")
                self.events[UID]["done"] = True
                self.events[UID]["scheduled"] = False

        # No reminder, clear the sensor
        if not reminder_state_set:
            self.set_state(
                self.reminder_sensor,
                state="None",
                attributes={"friendly_name": "School reminder"},
            )

    @ad.app_lock
    def remind(self, kwargs):
        """Invokes various services to send reminder notifications"""

        message = kwargs["message"]
        UID = kwargs["UID"]

        self.events[UID]["done"] = True
        self.events[UID]["scheduled"] = False
        self.events[UID]["timer_id"] = None

        # The first item in scheduled_event_uids should be UID
        self.scheduled_event_uids.pop(0)

        if self.scheduled_event_uids:
            next_UID = self.scheduled_event_uids[0]
            reminder_state = self.events[next_UID]["sensor_state"]
        else:
            reminder_state = "None"

        self.log(f"** Announcing ** '{message}', next '{reminder_state}'")

        if self.test_mode:
            return

        self.call_service("notify/mybot", message=message)

        for device in self.alexa_devices:
            self.call_service(
                "notify/alexa_media",
                target=device,
                data={"type": "announce"},
                message=message,
            )

        for device in self.google_devices:
            self.call_service(
                "tts/google_say", entity_id=device, message=message
            )

        self.set_state(
            self.reminder_sensor,
            state=reminder_state,
            attributes={"friendly_name": "School reminder"},
        )

    def cancel_reminders(self):
        """Cancel all scheduled reminders"""

        if self.events:
            self.log("Cancelling current reminders")

            for UID in self.events:
                if self.events[UID]["timer_id"] is not None:
                    self.cancel_timer(self.events[UID]["timer_id"])

        self.events = {}
        self.scheduled_event_uids = []


def get_announcement(message, reminder_offset):
    """
    Generates the announcement message

    :param str message: Message about the event
    :param number reminder_offset: Minutes in which event is about to happen
    """

    pos = message.find(":")
    if pos == -1:
        activity = message.strip()
        message = f"{activity} in {reminder_offset} minutes."
    else:
        activity = message[pos + 1 :].strip()
        person = message[0:pos].strip()
        message = f"Hello {person}, you have {activity} in {reminder_offset} minutes."

    return message


def get_starttime(event):
    """Delegate for sorting Calendar entries by event_start time"""
    return event["DTSTART"].dt


def get_static_skip_dates(skip_dates):
    """Get list of dates on which there are no events"""
    dates = set()  # Start as set to avoid duplicates

    skip_dates = skip_dates or []
    for value in skip_dates:
        rangePos = value.find("-")

        if rangePos == -1:
            dates.add(datetime.strptime(value, "%m/%d/%Y").date())
        else:
            ranges = value.split("-")
            start_date = datetime.strptime(ranges[0], "%m/%d/%Y")
            end_date = datetime.strptime(ranges[1], "%m/%d/%Y")
            day_delta = timedelta(days=1)

            while start_date <= end_date:
                dates.add(start_date.date())
                start_date += day_delta

    values = list(dates)
    values.sort()
    return values
