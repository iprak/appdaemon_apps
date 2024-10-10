# import appdaemon.appapi as appapi
import hassapi as hass
import os
from datetime import datetime

#
# App to display a Persistent Notification on the Front End whenever AppDaemon has encountered
# an error
#
# Args: (set these in appdaemon.cfg)
# path_to_errorlog = full path of location of errorlog
# refresh_interval = time in seconds to check for new errors
#
#
# EXAMPLE appdaemon.cfg entry below
#
# # Apps
#
# [error_notifier]
# module = error_notifier
# class = ErrorNotifier
# path_to_errorlog = /home/homeassistant/.homeassistant/appdaemon/conf/errfile.log
# refresh_interval = 5
#


# class ErrorNotifier(appapi.AppDaemon):
class ErrorNotifier(hass.Hass):
    def initialize(self):
        self.last_update = None
        self.error_log = self.args.get("path_to_errorlog")

        self.run_every(
            self.get_last_file_update,
            start=self.datetime(),
            interval=int(self.args.get("refresh_interval", 5)),
        )

    def get_last_file_update(self, kwargs):
        last_update_seconds = os.stat(self.error_log).st_mtime
        last_update = datetime.fromtimestamp(last_update_seconds)

        if (self.last_update is None) or (last_update > self.last_update):
            self.last_update = last_update

            if os.stat(self.error_log).st_size > 0:
                self.notify_frontend()

    def notify_frontend(self):
        pretty_timestamp = self.last_update.strftime("%A, %x @ %X")

        self.call_service(
            "notify/mybot",
            message=(
                "On {}, we found at least one new error in the error log!\nYou should go check to"
                "see what went wrong.".format(pretty_timestamp)
            ),
        )
