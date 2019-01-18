"""
DELL EMC ECS SendGrid Email Module.
"""
import http.client
import ecssendgrid
import sendgrid
import os
from sendgrid.helpers.mail import *
import time

# Constants
MODULE_NAME = "ecssendgrid"                  # Module Name


class ECSSendGridException(Exception):
    pass


class ECSSendGridUtility(object):
    """
    Stores ECS SendGrid Email Functions
    """
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.send_grid_client = None

    def check_send_grid_access(self):
        """
        Checks if we have a valid SendGrid API Key and connect to the service
        """
        try:
            connected = True

            while not self.config:
                time.sleep(1)

            # Get SendGrid API Client
            self.send_grid_client = sendgrid.SendGridAPIClient(apikey=self.config.send_grid_api_key)

            return connected

        except Exception as e:
            self.logger.error(MODULE_NAME + '::check_send_grid_access()::The following '
                                            'unhandled exception occurred: ' + e.message)
            connected = False
            return connected

    def send_grid_send_email(self, row):
        """
        Sends an email via SendGrid
        """
        try:
            sent = True

            while not self.config:
                time.sleep(1)

            # Grab values from row parameter
            id = row[0]
            vdc = row[1]
            alertid = row[2]
            description = row[4]
            severity = row[6]
            symtomcode = row[7]
            timestamp = row[8]

            from_email = Email(self.config.send_grid_fromemail)
            to_email = Email(self.config.send_grid_toemail)
            subject = "Elastic Cloud Storage (ECS) Alert Received"

            if severity == 'WARNING':
                severity_text = """<font color="orange">""" + severity + "</font>"
            else:
                if severity == 'ERROR':
                    severity_text = """<font color="red">""" + severity + "</font>"
                else:
                    severity_text = """<font color="black">""" + severity + "</font>"

            email_content = Content("text/html", "<html><body><h1>" +
                                    "Elastic Cloud Storage (ECS) Received Alert from "
                                    "Virtual Data Center: " + vdc + "</h1><br>" +
                                    "Severity: " + severity_text + "<br>" +
                                    "Symptom Code : " + symtomcode + "<br>" +
                                    "Description : " + description + "<br>" +
                                    "Timestamp : " + timestamp + "<br>" +
                                    "</body></html>")

            mail = Mail(from_email, subject, to_email, email_content)
            response = self.send_grid_client.client.mail.send.post(request_body=mail.get())

            # Uncomment the following 3 lines for debug purposes
            #print(response.status_code)
            #print(response.body)
            #print(response.headers)

            return sent

        except Exception as e:
            self.logger.error(MODULE_NAME + '::send_grid_send_email()::The following '
                                            'unhandled exception occurred: ' + e.message)
            sent = False
            return sent

