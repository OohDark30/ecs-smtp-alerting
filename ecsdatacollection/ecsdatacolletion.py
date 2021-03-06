"""
DELL EMC ECS API Data Collection Module.
"""
import io
import os
import json
import requests
import urllib3
import uuid
from requests.auth import HTTPBasicAuth

# Constants
MODULE_NAME = "ecs"                  # Module Name

class ECSException(Exception):
    pass


class ECSAuthentication(object):
    """
    Stores ECS Authentication Information
    """
    def __init__(self, protocol, host, username, password, port, logger):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.logger = logger
        self.logger.info('ECSAuthentication::Object instance initialization complete.')
        self.url = "{0}://{1}:{2}".format(self.protocol, self.host, self.port)
        self.token = ''

        # Disable warnings
        urllib3.disable_warnings()

    def get_url(self):
        """
        Returns an ECS Management url made from protocol, host and port.
        """
        return self.url

    def get_token(self):
        """
        Returns an ECS Management token
        """
        return self.tokens

    def connect(self):
        """
        Connect to ECS and if successful update token
        """
        self.logger.info('ECSAuthentication::connect()::We are about to attempt to connect to ECS with the following URL : '
                         + "{0}://{1}:{2}".format(self.protocol, self.host, self.port) + '/login')

        r = requests.get("{0}://{1}:{2}".format(self.protocol, self.host, self.port) + '/login',
                         verify=False, auth=HTTPBasicAuth(self.username, self.password))

        self.logger.info('ECSAuthentication::connect()::login call to ECS returned with status code: ' + str(r.status_code))
        if r.status_code == requests.codes.ok:
            self.logger.debug('ECSAuthentication::connect()::login call returned with a 200 status code.  '
                              'X-SDS-AUTH-TOKEN Header contains: ' + r.headers['X-SDS-AUTH-TOKEN'])
            self.token = r.headers['X-SDS-AUTH-TOKEN']
        else:
            self.logger.error('ECSManagementAPI::connect()::login call '
                             'failed with a status code of ' + str(r.status_code))
            self.token = None


class ECSManagementAPI(object):
    """
    Perform ECS Management API Calls
    """

    def __init__(self, authentication, logger, response_json=None, response_xml=None):
        self.ecs_authentication_failure = int('497')
        self.authentication = authentication
        self.response_json = response_json
        self.response_xml = response_xml
        self.logger = logger
        self.response_xml_file = None

    def ecs_collect_alert_data(self, tempdir, marker):

        while True:
            # Perform ECS Dashboard Alert API Call
            headers = {'X-SDS-AUTH-TOKEN': "'{0}'".format(self.authentication.token),
                       'content-type': 'application/json'}

            # Setup parameters - WE ONLY TAKE ALERTS THAT HAVE NOT BEEN ACKNOWLEDGED
            if marker:
                params_dict = {'acknowledged': False}
                params_dict["marker"] = marker
            else:
                params_dict = {'acknowledged': False}

            # Call API
            r = requests.get("{0}//vdc/alerts".format(self.authentication.url),
                             headers=headers, verify=False, params=params_dict)

            if r.status_code == requests.codes.ok:
                self.logger.debug('ECSManagementAPI::ecs_collect_alert_data()::/vdc/alerts call returned '
                                  'with a 200 status code.  Text is: ' + r.text)

                # Create a unique temp file and store the XML to it for processing
                tempfile = os.path.abspath(os.path.join(tempdir, str(uuid.uuid4()) + ".xml"))
                fo = open(tempfile, "w+")
                fo.write(r.text)

                # Close file
                fo.close()

                self.logger.debug('ECSManagementAPI::ecs_collect_alert_data()::r.text() contains: \n' + r.text)

                self.response_xml_file = tempfile
                break
            else:
                if r.status_code == self.ecs_authentication_failure:
                    # Attempt to re-authenticate
                    self.authentication.token = None
                    self.authentication.connect()

                    if self.authentication.token is None:
                        self.logger.error('ECSManagementAPI::ecs_collect_alert_data()::Token Expired.  Unable '
                                          'to re-authenticate to ECS as configured.  Please validate and try again.')
                        raise ECSException("The ECS Data Collection Module was unable to re-authenticate.")
                        break
                else:
                    self.logger.error('ECSManagementAPI::ecs_collect_alert_data()::/vdc/alerts call failed '
                                      'with a status code of ' + str(r.status_code))
                    self.response_xml_file = None
                    break

        return self.response_xml_file

    def ecs_acknowledge_alert(self, alert_id):

        while True:
            # Perform ECS Dashboard Alert Acknowledge API Call
            headers = {'X-SDS-AUTH-TOKEN': "'{0}'".format(self.authentication.token),
                       'content-type': 'application/json'}

            r = requests.put("{0}//vdc/alerts/{1}/acknowledgment".format(self.authentication.url, alert_id),
                             headers=headers, verify=False)

            if r.status_code == requests.codes.ok:
                self.logger.debug('ECSManagementAPI::ecs_acknowledge_alert()::/vdc/alerts/acknowledgment call returned '
                                  'with a 200 status code.  Text is: ' + r.text)

                alert_acknowledged = True
                break
            else:
                if r.status_code == self.ecs_authentication_failure:
                    # Attempt to re-authenticate
                    self.authentication.token = None
                    self.authentication.connect()

                    if self.authentication.token is None:
                        self.logger.error('ECSManagementAPI::ecs_collect_alert_data()::Token Expired.  Unable '
                                          'to re-authenticate to ECS as configured.  Please validate and try again.')
                        alert_acknowledged = False
                        raise ECSException("The ECS Data Collection Module was unable to re-authenticate.")

                else:
                    self.logger.error('ECSManagementAPI::ecs_collect_alert_data()::/vdc/alerts/latest call failed '
                                      'with a status code of ' + str(r.status_code))
                    alert_acknowledged = False
                    break

        return alert_acknowledged

    def get_ecs_detail_data(self, field, metric_list=[], metric_values={}):
        # Valid 'metric_list' is a list of dictionary items
        # { 't' : '<epoch time>', '<units of measure>' : '<data>' }
        if len(metric_list):
            # Check if this is a valid list of timestamped data points
            # If so, iterate through the list of data points
            if 't' in metric_list[0]:
                for items in metric_list:
                    # Gets the timestamp for this data point
                    epoch_time = items.pop('t')
                    # Get the data point
                    for units in items:
                        data = float(items[units])
                    # Data key'ed to time then field : data
                    if epoch_time in metric_values:
                        metric_values[epoch_time][field] = data
                    else:
                        metric_values[epoch_time] = {}
                        metric_values[epoch_time][field] = data

    def get_ecs_summary_data(self, field, current_epoch, summary_dict={}, summary_values={}):
        # Valid 'summary_dict' is a dictionary of three keys
        # 'Min' and 'Max' which is a list with a single item containing
        # { 't' : '<epoch time>', '<units of measure>' : '<data>' }
        # Third key is 'Avg' which just has a value
        for keys in summary_dict:
            self.logger.debug('ECSManagementAPI::get_ecs_summary_data()::'
                              'Key in summary_dict being processed is: ' + keys)

            if type(summary_dict[keys]) is list:
                # Check non-empty list. Since list is only item we can address
                # the value directly using [0]
                if len(summary_dict[keys]):
                    epoch_time = summary_dict[keys][0].pop('t')
                    for units in summary_dict[keys][0]:
                        data = float(summary_dict[keys][0][units])
                    # Data key'ed to time, then field+keys : data
                    # E.g. field+keys "chunksEcRateSummaryMin"
                    if epoch_time in summary_values:
                        summary_values[epoch_time][field+keys] = data
                    else:
                        summary_values[epoch_time] = {}
                        summary_values[epoch_time][field+keys] = data
            # "Avg" value which is just key : value
            else:
                if current_epoch in summary_values:
                    summary_values[current_epoch][field+keys] = \
                        float(summary_dict[keys])
                else:
                    summary_values[current_epoch] = {}
                    summary_values[current_epoch][field+keys] = \
                        float(summary_dict[keys])


class ECSUtility(object):
    """
    ECS Utility Class
    """

    def __init__(self, authentication, logger, vdc_lookup_file):
        self.authentication = authentication
        self.logger = logger
        self.vdc_lookup = vdc_lookup_file
        self.vdc_json = None

        if vdc_lookup_file is None:
            raise ECSException("No file path to the ECS VDC Lookup configuration provided.")

        if not os.path.exists(vdc_lookup_file):
            raise ECSException("The ECS VDC Lookup configuration file path does not exist: " + vdc_lookup_file)

        # Attempt to open configuration file
        try:
            with open(vdc_lookup_file, 'r') as f:
                self.vdc_json = json.load(f)
        except Exception as e:
            raise ECSException("The following unexpected exception occurred in the "
                               "ECS Data Collection Module attempting to parse "
                               "the ECS VDC Lookup configuration file: " + e.message)
