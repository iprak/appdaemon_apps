"""App to check emails from MyPoints"""
import hassapi as hass
from datetime import datetime, timedelta
import requests
import urllib.parse

from imapclient import IMAPClient
from packages.mailparser import MailParser
from bs4 import BeautifulSoup


GMX_PREFIX = "https://deref-gmx.com/mail/client/Xd-wFjnrIUA/dereferrer/?redirectUrl="


class MyPoints(hass.Hass):
    def initialize(self):
        self.servers = self.args["servers"]
        # for item in servers:
        #    self.log(f'{item["server"]} {item["email"]} {item["passwd"]} {item["folder"]}')

        self.run_every(self.check, "now", 4 * 3600)  # Every 4 hours
        # self.log("Initialized")

    def check(self, kwargs=None):
        for item in self.servers:
            self.check_emails(item["server"], item["email"], item["passwd"], item["folder"])

    def valid_email(self, from_):
        email_from = list(from_)
        email_from_tuple = email_from[0]  # Use first tuple

        for item in email_from_tuple:
            # self.log(f"Checking {item}")

            if item.find("@mypoints.com") != -1:
                return True
        return False

    def valid_link(self, link):
        if not link:
            return False
        return link.find("mypoints.com/?cmd=oh-offer-click") != -1

        # if link.find("account-settings#close-account") != -1:
        #     return False
        # if link.find("mp-ac-email-unsub") != -1:
        #     return False
        # if link.find("mp-ac-email-client-optout") != -1:
        #     return False
        # if link.find("mypoints.com/account-statement") != -1:
        #     return False

    def fix_link(self, link: str):
        if link.find(GMX_PREFIX) != -1:
            link = link[len(GMX_PREFIX) :]

        # https://stackoverflow.com/questions/8689795/how-can-i-remove-non-ascii-characters-but-leave-periods-and-spaces-using-python
        link = link.encode("ascii", errors="ignore").decode()
        return urllib.parse.unquote(link)

    def check_emails(self, server, email, passwd, folder):
        flag = "ALL"
        # 'UNSEEN'

        try:
            client = IMAPClient(server, use_uid=True)
        except Exception as error:
            self.log(f"{server}: Unable to connect to {server}: {error}")
            return

        try:
            client.login(email, passwd)
        except Exception as error:
            self.log(f"{server}: IMAPClient login error for {email}/{passwd}: {error}")
            return

        try:
            client.select_folder(folder, readonly=False)
        except Exception as error:
            self.log(f"{server}: Error selecting folder {error}")

            client.logout()
            return

        # emails = []
        unique_links = {}
        today = datetime.today()
        cutoff = (today - timedelta(days=1)).strftime("%d-%b-%Y")
        self.log(f"{server}: Connected, getting  emails since {cutoff}")

        try:
            # messages = client.search(flag)
            messages = client.search(["SINCE", cutoff])

            message_items = client.fetch(messages, "RFC822").items()
            self.log(f"{server}: {len(message_items)} messages since {cutoff}")

            for uid, message_data in message_items:
                try:
                    mail = MailParser.from_bytes(message_data[b"RFC822"])

                    # mail.from_, mail.subject, mail.body
                    if not self.valid_email(mail.from_):
                        continue

                    soup = BeautifulSoup(mail.body, "html.parser")
                    links = [link.get("href") for link in soup.find_all("a")]
                    for link in links:
                        if not self.valid_link(link):
                            continue

                        unique_links[self.fix_link(link)] = uid

                except Exception as err:
                    self.log(f"{server}: Parsing error: {err}")

        except Exception as err:
            self.log(f"{server}: IMAPClient error {err}")

        if len(unique_links):
            # self.log(f"{server}: {len(unique_links)} links")
            uids_to_delete = []
            for link in unique_links:
                uid = unique_links[link]
                headers = {
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36"
                }
                response = requests.get(link, headers=headers)

                if response.status_code == 200:
                    uids_to_delete.append(uid)
                else:
                    # self.log(response.text)
                    self.log(f"{server} {link} => {response.status_code}")

            if uids_to_delete:
                try:
                    self.log(f"{server}: Deleting {uids_to_delete}")
                    client.delete_messages(uids_to_delete)

                    # Deleting does not seem to actually delete the messsage. Manually moving it to Trash folder.
                    # client.move(uids_to_delete, "Trash")
                except Exception as err:
                    self.log(f"{server}: Error deleting {err}")

        # self.log(f"{server}: Logout")
        client.logout()
