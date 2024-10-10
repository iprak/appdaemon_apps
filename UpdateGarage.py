import hassapi as hass
import requests

FETCH_INTERVAL = 30
REQUEST_TIMEOUT = 5


class UpdateGarage(hass.Hass):
    def initialize(self):
        self.entity_id = "sensor.garage_door"
        self.garage_address = "192.168.1.200"
        self.api_key = "ED935AA4950CCCC1"
        self.url = (
            f"http://{self.garage_address}/api/door?apikey={self.api_key}"
        )

        self.state_switcher = {
            "1": "open",
            "2": "closed",
            "3": "opening",
            "4": "closing",
            "5": "stopped",
        }

        self.log(
            f"Checking {self.garage_address} every {FETCH_INTERVAL} seconds"
        )
        self.callback = self.run_every(self.fetchData, "now", FETCH_INTERVAL)
        self.fetching_data = False

    def terminate(self):
        if self.callback:
            self.cancel_timer(self.callback)
            self.callback = None

    def fetchData(self, kwargs=None):
        # self.log("Fetching data")

        if self.fetching_data:
            return

        self.fetching_data = True

        try:
            data = requests.get(self.url, timeout=REQUEST_TIMEOUT).text
            # self.log(data)

            pcs = data.split("/")
            state = self.state_switcher.get(pcs[0], "closed")
            curState = self.get_state(self.entity_id)
            if curState != state:
                self.log(f"Updating state to {state}")
        except (
            requests.Timeout,
            requests.ConnectTimeout,
            requests.ReadTimeout,
        ):
            self.log(f"Timeout out while connecting.")
        # except requests.RequestException:
        #    self.log(f"Error connecting to {self.garage_address}.")
        except Exception as e:
            if hasattr(e, "message"):
                self.log(f"Error connecting: {e.message}")
            else:
                self.log(f"Error connecting: {e}")

        self.fetching_data = False