import hassapi as hass
from datetime import datetime, timedelta

#
# App to calculate gain based on yahoofinance stock sensors.
#
# The gain sensor's state represents the gain/loss. It will have these attributes:
#   "cost_basis": Sum of (purchase_price * quantity)
#   "day_change": Overall change based on "regularMarketPreviousClose" of individual stocks
#   "day_change_percent": Overall daily change percentage
#   "friendly_name": Specified friendly name
#   "gain_percent": Gain/loss percentage
#   "icon": Icon based on trending status
#   "market_value": Overall market value
#   "trending": Trending status (up/neutral/down)
#   "unit_of_measurement": Specified Unit of measurement
#   "previous_close": Total based on "regularMarketPreviousClose" of individual stocks

#
# Args:
#
#   total_entity: id of the generated entity (required)
#   friendly_name: Friendly name of the generated entity
#   unit_of_measurement: Unit of measurement (currency) of the generated entity (default=USD)
#   decimal_places: Number of decimal places (default=2)
#   entities: List of tracked yahoo finance sensors (required)
#     - entity: Sensor id e.g. yahoofinance.xyz (required)
#       quantity: Number of stocks currently held. Quanity from purchases is used if this is not defined.
#       purchases: List of purchases
#         - quantity: Number of stocks purchased (required)
#           price: Purchase price (required)
#           date: Purchase date (%m-%d-%Y) (required)
#


# Delay after which calculations are performed when sensors change. Since sensors change individually
# so this prevent duplicate calculations.
UPDATE_BATCH_TIMER = 2


class StockAggregator(hass.Hass):
    """Represents the StockAggregator app."""

    def initialize(self):
        self.handle_list = []
        self.callback = None
        self.entities_map = {}

        self.entities = self.args["entities"]
        self.total_entity = self.args["total_entity"]
        self.friendly_name = self.args.get("friendly_name", "")
        self.unit_of_measurement = self.args.get("unit_of_measurement", "USD").upper()
        self.decimal_places = self.args.get("decimal_places", 2)

        self.subscribe_entities()

    def terminate(self):
        self.unsubscribe_entities()

        if self.callback is not None:
            self.cancel_timer(self.callback)
            self.callback = None

    def subscribe_entities(self):
        self.log("Subscribing")

        for item in self.entities:
            entity = item["entity"].lower()
            purchases = item["purchases"]
            quantity = item.get("quantity")
            self.entities_map[entity] = (quantity, purchases)
            self.handle_list.append(self.listen_state(self.entity_change, entity))

        # Force update
        self.update_total()

    def entity_change(self, entity, attribute, old, new, kwargs=None):
        if self.callback is None:
            # self.log(f"setting callback for {key}")
            self.callback = self.run_in(self.run_callback, UPDATE_BATCH_TIMER)

    def run_callback(self, kwargs):
        self.callback = None
        self.update_total()

    def to_float(self, value):
        try:
            return float(value)
        except:
            return 0

    def round(self, value):
        """Return formatted value based on decimal_places."""
        if value is None:
            return None

        if self.decimal_places < 0:
            return value
        if self.decimal_places == 0:
            return int(value)

        return round(value, self.decimal_places)

    def update_total(self):
        market_value = float(0)
        cost_basis = float(0)
        day_change = float(0)
        previous_market_value = float(0)

        for entity, (quantity, purchases) in self.entities_map.items():
            current_price = self.get_state(entity)
            if current_price is None:
                continue

            current_price = self.to_float(current_price)
            previous_price = self.to_float(
                self.get_state(entity, attribute="regularMarketPreviousClose")
            )

            quantity_from_purchases = 0
            for purchase in purchases:
                purchase_quantity = purchase["quantity"]
                purchase_price = purchase["price"]
                date = datetime.strptime(purchase["date"], "%m-%d-%Y")
                quantity_from_purchases += purchase_quantity

                self.log(f"{entity} {purchase_quantity} @ {purchase_price} on {date}")
                cost_basis += purchase_quantity * purchase_price

            # Use the quantity from purchases, if it is not defined at symbol level
            if quantity is None:
                quantity = quantity_from_purchases

            market_value += quantity * current_price
            previous_market_value += quantity * previous_price

        gain = market_value - cost_basis
        gain_percent = (gain * 100) / cost_basis
        day_change = market_value - previous_market_value
        day_change_percent = (day_change * 100) / previous_market_value

        self.log(f"gain={gain}")

        # if current_state is not None:
        if gain < previous_market_value:
            trending = "down"
        elif gain > previous_market_value:
            trending = "up"
        else:
            trending = "neutral"

        icon = f"mdi:trending-{trending}"

        # Round values before setting them
        attributes = {
            "cost_basis": self.round(cost_basis),
            "day_change": self.round(day_change),
            "day_change_percent": self.round(day_change_percent),
            "friendly_name": self.friendly_name,
            "gain_percent": self.round(gain_percent),
            "icon": icon,
            "market_value": self.round(market_value),
            "trending": trending,
            "unit_of_measurement": self.unit_of_measurement,
            "previous_close": self.round(previous_market_value),
        }

        self.log(attributes)

        self.set_state(
            self.total_entity,
            state=gain,
            attributes=attributes,
            replace=True,
        )

    def unsubscribe_entities(self):
        for handle in self.handle_list:
            self.cancel_listen_state(handle)
        self.handle_list = []
