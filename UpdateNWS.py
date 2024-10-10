import hassapi as hass
import datetime
from dateutil.parser import parse
import copy

#
# App to update weather entity based on NWS weather daynight entity
#
# Args:
#
# source = NWS daynight entity
# destination = Generated weather entity
#


class UpdateNWS(hass.Hass):
    def initialize(self):
        self.source_entity = self.args["source"]
        self.destination_entity = self.args["destination"]

        self.listen_state(self.state_change, self.source_entity)
        self.update_from_nws()

    def state_change(self, entity, attribute, old, new, kwargs):
        self.log("NWS entity changed")
        self.update_from_nws()

    def update_from_nws(self):
        attributes = self.get_state(self.source_entity, attribute="all")[
            "attributes"
        ]

        forecast_list = attributes.get("forecast")
        if forecast_list is None:  # forecast can sometimes is missing
            return

        new_forecasts = {}
        # self.log(f'forecast_list={forecast_list}')
        first_temperature = None

        for forecast in forecast_list:
            datetime = parse(forecast["datetime"])
            date = datetime.date()

            # Convert to midnight
            date = datetime.combine(date, datetime.min.time())

            date_string = date.astimezone().isoformat()

            if date_string in new_forecasts:
                # self.log(f'existing new_forecasts[{date_string}]= {new_forecasts[date_string]}')

                self.set_templow(new_forecasts[date_string], forecast)
                self.combine_precipitation(
                    new_forecasts[date_string], forecast
                )
            else:
                new_forecasts[date_string] = copy.deepcopy(forecast)
                # self.log(f'new_forecasts[{date_string}]= {new_forecasts[date_string]}')

                # Use the temperature as the templow
                new_forecasts[date_string]["templow"] = forecast["temperature"]

                if first_temperature is None:
                    first_temperature = forecast["temperature"]

                # new_forecasts[date_string]["datetime"] = date_string
                del new_forecasts[date_string]["is_daytime"]
                del new_forecasts[date_string]["detailed_description"]

        # self.log(f'new_forecasts={new_forecasts}')

        # Copy entity attributes and then delete previous forecast
        new_attributes = copy.deepcopy(attributes)
        del new_attributes["forecast"]
        # del new_attributes["friendly_name"]  #Keep friendly name
        new_attributes["forecast"] = list(new_forecasts.values())

        # Use the first temperature as the temperature if it is missing
        new_attributes["temperature"] = new_attributes.get(
            "temperature", first_temperature
        )

        # self.log(new_attributes)

        self.set_state(
            self.destination_entity,
            state=self.get_state(self.source_entity),
            attributes=new_attributes,
            replace=True,
        )

    def set_templow(self, daily_forecast, forecast):
        previous_value = daily_forecast.get("temperature", None)
        if previous_value is None:
            return

        value = forecast.get("temperature", None)
        if value is None:
            return

        # self.log(f'set_templow {previous_value} {value}')
        daily_forecast["templow"] = min(previous_value, value)

    def extract_precipitation(self, value):
        if value is None:
            return None

        if isinstance(value, dict):
            return value.get("value", None)

        return value

    def combine_precipitation(self, daily_forecast, forecast):
        #Sample values:
        #precipitation_probability:
        #    unitCode: wmoUnit:percent
        #    value: null
        #precipitation_probability: 50

        previous_value = self.extract_precipitation(daily_forecast.get("precipitation_probability", None))
        if previous_value is None:
            return

        value = self.extract_precipitation(forecast.get("precipitation_probability", None))
        if value is None:
            return

        # self.log(f'combine_precipitation {previous_value} {value}')
        daily_forecast["precipitation_probability"] = max(
            previous_value, value
        )
