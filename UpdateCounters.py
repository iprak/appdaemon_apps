"""App to update group count values"""
import hassapi as hass
import datetime


# Interval after which count is calculated when an entity change notification is received
COUNT_UPDATE_BATCH_TIMER = 2
DEFAULT_BATTERY_THRESHOLD = 25


class UpdateCounters(hass.Hass):
    def initialize(self):
        self.handle_list = []
        self.callbacks = {}

        self.battery_threshold = self.args.get(
            "battery_threshold", DEFAULT_BATTERY_THRESHOLD
        )
        self.groups_map = self.args["groups_map"]
        self.log(self.groups_map)

        self.subscribe_entities()
        self.listen_event(self.ha_service_invoked, "call_service")

        # Groups are created on HASS reconnection which triggers ha_service_invoked updating the counters
        # So we don't need to subscribe to "ha_plugin_started"

    def ha_service_invoked(self, event_name, data, kwargs):
        # Re-subscribe if groups reloaded
        if (data["domain"] == "group") and (data["service"] == "reload"):
            self.unsubscribe_entities()
            self.subscribe_entities()

    def terminate(self):
        self.unsubscribe_entities()

        if self.callbacks:
            for key, value in self.callbacks.items():
                self.cancel_timer(value)
            self.callbacks = None

    def subscribe_entities(self):
        self.log("Subscribing")
        for key in self.groups_map:
            group_id = "group." + key
            group_attributes = self.get_state(group_id, attribute="all")
            if group_attributes is None:
                continue

            entities = group_attributes["attributes"]["entity_id"]
            if entities:
                for entity_id in entities:
                    # self.log("listen_state {%s}", entity_id)
                    self.handle_list.append(
                        self.listen_state(
                            self.entity_change,
                            entity_id,
                            key=key,
                        )
                    )

            # Force update based on the first group item
            self.entity_change("", "", "", "", {"key": key})

    def entity_change(self, entity, attribute, old, new, kwargs):
        key = kwargs["key"]

        # Entities in a group can change quicky so use a 2 second timer for count
        if key not in self.callbacks:
            # self.log(f"setting callback for {key}")
            self.callbacks[key] = self.run_in(
                self.run_callback, COUNT_UPDATE_BATCH_TIMER, key=key
            )

    def run_callback(self, kwargs):
        key = kwargs["key"]

        del self.callbacks[key]

        group_id = "group." + key
        self.update_count(group_id, self.groups_map[key])

    def update_count(self, group_id, group_map_item):
        # self.log(group_id)
        entity_list = self.get_state(group_id, attribute="all")["attributes"][
            "entity_id"
        ]

        # count_sensor = "variable." + group_map_item["sensor"]
        count_sensor = "sensor." + group_map_item["sensor"]

        count = 0
        if entity_list:
            if group_map_item.get("battery"):
                for entity_id in entity_list:
                    batteryState = self.get_state(entity_id)
                    #self.log("batteryState %s=%s", entity_id, batteryState)

                    # Safeguard against uninitialized entity
                    if not (batteryState is None) and not (
                        batteryState == "unavailable"
                    ):
                        if int(batteryState) < self.battery_threshold:
                            count = count + 1
            else:
                matchValue = group_map_item.get("state")

                # self.log(entity_list)
                for entity_id in entity_list:
                    if self.get_state(entity_id) == matchValue:
                        count = count + 1

        new_attributes = {"friendly_name": group_map_item["friendly_name"]}

        if "icon" in group_map_item:
            new_attributes["icon"] = "mdi:" + group_map_item["icon"]

        self.set_state(count_sensor, state=count, attributes=new_attributes)
        #self.log("Counter %s = %d", count_sensor, count)

    def unsubscribe_entities(self):
        if self.handle_list:
            for handle in self.handle_list:
                self.cancel_listen_state(handle)
        self.handle_list = []

    def log_notify(self, message, level="INFO"):
        if "verbose_log" in self.args:
            self.log(message)
        if "notify" in self.args:
            self.notify(message, globals.notify, name=globals.notify)
