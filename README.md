# appdaemon_apps

Collection of some appdaemon apps.

# Reminders

App to announce notifications on Alexa and Google devices based on calendar feed.

- The events need to be 15 minutes apart and for 15 minutes duration.

Event subject format:

- Event of the subject "Robert: maths" will generate the notification "Hello Robert, you have maths in 2 minutes."
- "Family zoom" will generate the notification "Family zoom in 2 minutes."

Args:

```yaml
feed: iCal feed url (required)
alexa_devices: Alexa devices to send announcement
google_devices: Google devices to send announcement
reminder_sensor: sensor to update with next reminder details (required)
fetch_interval: Minutes between calendar fetch (default = 10 minutes)
reminder_offset: Minutes before the event for sending notification (default = 2 minutes)
skip_days: Array of weekdays on which to skip reminders (default = Saturday, Sunday)
skip_dates: Array of dates on which to skip reminders, the dates can be a range
start_hour: starting hour for the day (default = 8 AM)
end_hour: ending hour for the day (default = 4 PM)
```

Sample configuration:

```yaml
Reminders:
  module: Reminders
  class: Reminders
  feed: !secret school_calendar_feed
  google_devices:
    - media_player.living_room_speaker
  reminder_sensor: sensor.next_school_reminder
  skip_dates: ["11/12/2020", "11/25/2020-11/27/2020"]
```

# UpdateCounters

App to update group count values based on the `state` value.

For battery sensors, define `"battery": True` instead of `state`. The default low battery threshold is 25. For the count sensor, `friendly_name` for the sensor is required but `icon` is optional.

Sample configurations:

```yaml
UpdateCounters:
  module: UpdateCounters
  class: UpdateCounters
  groups_map:
    {
      "lights":
        {
          "state": "on",
          "sensor": "lights_on_count",
          "friendly_name": "Lights on",
        },
    }
```

```yaml
UpdateCounters:
  module: UpdateCounters
  class: UpdateCounters
  battery_threshold: 20
  groups_map:
    {
      "device_batteries":
        {
          "battery": True,
          "sensor": "low_battery_count",
          "friendly_name": "Low battery",
          "icon": "battery-alert-variant-outline",
        },
    }
```
