import hassapi as hass
from datetime import datetime
import AppUtils

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
#     - entity: Sensor id e.g. sensor.yahoofinance_xyz (required)
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
        self.unit_of_measurement = self.args.get("unit_of_measurement", "$").upper()
        self.decimal_places = self.args.get("decimal_places", 2)

        # self._skip_updates = False

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

            purchases = item.get("purchases")
            sales = item.get("sales")

            if (purchases is None) and (sales is None):
                raise Exception(f"No `purchases` or `sales` defined for {entity}")
            elif len(purchases) == 0 and len(sales) == 0:
                raise Exception(f"Empty `purchases` and `sales` defined for {entity}")

            quantity = item.get("quantity")
            self.entities_map[entity] = (quantity, purchases, sales)
            self.handle_list.append(
                self.listen_state(self.entity_change, entity, attribute="all")
            )

        # Force update
        self.update_total()

    def entity_change(self, entity, attribute, old, new, kwargs=None):
        if self.callback is None:
            # self.log(f"setting callback for {key}")
            self.callback = self.run_in(self.run_callback, UPDATE_BATCH_TIMER)

    def run_callback(self, kwargs):
        self.callback = None
        self.update_total()

    def update_total(self):
        market_value = float(0)
        cost_basis = float(0)
        day_change = float(0)
        previous_market_value = float(0)

        for entity, (quantity, purchases, sales) in self.entities_map.items():
            current_price = self.get_state(entity)
            symbol_attributes = self.get_state(entity, attribute="all")["attributes"]

            if current_price is None:
                continue

            current_price = AppUtils.to_float(current_price)
            previous_price = AppUtils.to_float(
                self.get_state(entity, attribute="regularMarketPreviousClose")
            )

            quantity_from_purchases = 0

            if purchases:
                for purchase in purchases:
                    purchase_quantity = purchase["quantity"]
                    purchase_price = purchase["price"]

                    purchase_date = purchase.get("date")
                    if purchase_date:
                        purchase_date = datetime.strptime(purchase_date, "%m-%d-%Y")

                    quantity_from_purchases += purchase_quantity

                    # self.log(f"{entity} {purchase_quantity} @ {purchase_price} on {purchase_date.strftime('%-m/%-d/%y')}")
                    cost_basis += purchase_quantity * purchase_price

            if sales:
                for sale in sales:
                    sale_quantity = sale["quantity"]
                    sale_price = sale["price"]

                    sale_date = sale.get("date")
                    if sale_date:
                        sale_date = datetime.strptime(sale_date, "%m-%d-%Y")

                    quantity_from_purchases -= sale_quantity

                    # self.log(f"Sold {entity} {sale_quantity} @ {sale_price} on {sale_date.strftime('%-m/%-d/%y')}")
                    cost_basis -= sale_quantity * sale_price

            # Use the quantity from purchases, if it is not defined at symbol level.
            if quantity is None:
                quantity = quantity_from_purchases

            if quantity is None:
                raise Exception("No `purchases > quantity` or `quantity` defined")

            market_value += quantity * current_price
            previous_market_value += quantity * previous_price

            # Save off quantity in attributes
            symbol_attributes["quantity"] = quantity
            self.set_state(entity, state=current_price, attributes=symbol_attributes)

        gain = market_value - cost_basis
        gain_percent = ((gain * 100) / cost_basis) if cost_basis != 0 else cost_basis
        day_change = market_value - previous_market_value
        day_change_percent = (
            ((day_change * 100) / previous_market_value)
            if previous_market_value != 0
            else previous_market_value
        )

        self.log(f"gain={gain}")

        # if current_state is not None:
        if market_value < previous_market_value:
            trending = "down"
        elif market_value > previous_market_value:
            trending = "up"
        else:
            trending = "neutral"

        # unit_prefix = f" {self.unit_of_measurement}" if self.unit_of_measurement else ""
        market_value = "{:,.2f}".format(
            AppUtils.round_float(market_value, self.decimal_places)
        )

        # Round values before setting them
        attributes = {
            "cost_basis": "{:,.2f}".format(cost_basis),
            "day_change": "{:+,.2f}".format(day_change),
            "day_change_percent": "{:+,.2f}".format(
                AppUtils.round_float(day_change_percent, self.decimal_places)
            )
            + " %",
            "friendly_name": self.friendly_name,
            "gain_percent": "{:,.2f}".format(
                AppUtils.round_float(gain_percent, self.decimal_places)
            )
            + " %",
            "icon": f"mdi:trending-{trending}",
            "market_value": market_value,
            "trending": trending,
            "unit_of_measurement": self.unit_of_measurement,
            "previous_close": "{:,.2f}".format(
                AppUtils.round_float(previous_market_value, self.decimal_places)
            ),
        }

        # self.log(attributes)

        self.set_state(
            self.total_entity,
            state=AppUtils.round_float(gain, self.decimal_places),
            attributes=attributes,
            replace=True,
        )

        # First day of the month
        if self.datetime(True).day == 1:
            self.set_state(
                "sensor.ameriprise_stocks_value_month_start", state=market_value
            )

    def unsubscribe_entities(self):
        for handle in self.handle_list:
            self.cancel_listen_state(handle)
        self.handle_list = []
