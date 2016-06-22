import httplib2
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import util


class OAuth:
    def __init__(self, client_id, client_secret, credentials_file, setup=False):
        self.client_id = client_id
        self.client_secret = client_secret
        self.credentials_file = credentials_file
        self.scope = 'https://www.googleapis.com/auth/youtube'
        self.credentials = None
        self.device_code = None
        self.user_code = None
        self.verification_url = None
        self.retry_interval = None
        self.max_retries = 60

        # Make sure we have a valid access token to work with
        if self.authorize_credentials(setup):
            logging.debug('Authorized credentials')
        else:
            if setup:
                logging.critical('Failed to get new credentials, exiting')
            else:
                logging.critical('Failed to get new credentials, please manually run yt-music-dl with the --setup flag')
            sys.exit()

    def access_token_valid(self):
        # If we have no credentials, we have no access token
        if self.credentials is None:
            return False

        # Declare URL to get TokenInfo
        url = 'https://www.googleapis.com/oauth2/v3/tokeninfo'

        # Supply the access token we have to check validity
        params = {
            'access_token': self.credentials['access_token']
        }

        # Encode and parse data for request
        request_data = urllib.parse.urlencode(params)
        request_data = request_data.encode('ascii')

        try:
            # Request TokenInfo for current access token
            response = urllib.request.urlopen(url, request_data)
        except urllib.error.HTTPError as e:
            # If access token is invalid, a HTML code 400 is returned
            if e.code == 400:
                logging.debug('Access token: invalid')
                return False
            else:
                logging.exception('Received unexpected response from API server while checking access token validity')
                sys.exit()

        try:
            # Decode and parse json response
            str_response = response.read().decode('utf-8')
            data = json.loads(str_response)

            # If the returned client id matches ours, then the access token is valid
            if 'aud' in data:
                if data['aud'] == self.client_id:
                    logging.debug('Access token: valid')
                    return True

            logging.debug('Access token: invalid')
            return False
        except KeyError or TypeError:
            logging.exception('Received unexpected response from API server while checking access token validity')
            sys.exit()

    def authorize_credentials(self, setup=False):
        # During first-time setup, get new credentials instead of looking for existing ones
        if setup:
            logging.debug('Getting new credentials...')
            return self.get_new_credentials(setup)

        # Get locally stored credentials from file
        logging.debug('Getting credentials from file...')
        if self.get_credentials_from_file():
            # If we got credentials from file, check if they are valid
            if self.access_token_valid():
                return True
            else:
                # If credentials are invalid, try to refresh them
                logging.debug('Refreshing credentials...')
                if self.refresh_credentials():
                    if self.access_token_valid():
                        return True

                # If access token is either invalid or we failed to refresh,
                # get new credentials through user intervention
                logging.debug('Getting new credentials...')
                if self.get_new_credentials():
                    return self.access_token_valid()
                else:
                    return False
        else:
            # If we can't read any credentials from file, we need to get new ones
            logging.debug('Getting new credentials...')
            if self.get_new_credentials():
                return self.access_token_valid()
            else:
                return False

    def get_credentials_from_file(self):
        # Check if credentials file exists
        if os.path.isfile(self.credentials_file):
            try:
                with open(self.credentials_file) as file:
                    self.credentials = json.load(file)
            except FileNotFoundError:
                logging.debug('Credentials file not found')
                return False
            except PermissionError:
                logging.debug('Could not read credentials from file')
                return False

            return True
        else:
            return False

    def refresh_credentials(self):
        # Declare target URL
        host = 'accounts.google.com'

        # Create a httplib2 connection to the specified URL
        conn = httplib2.HTTPSConnectionWithTimeout(host)

        # Declare parameters to refresh credentials
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.credentials['refresh_token'],
            'grant_type': 'refresh_token'
        }

        # Declare authentication header
        headers = {
            'Content-type': 'application/x-www-form-urlencoded'
        }

        # Add params and header to POST request
        conn.request(
            'POST',
            '/o/oauth2/token',
            urllib.parse.urlencode(params),
            headers
        )

        try:
            # Request credentials refresh
            response = conn.getresponse()
        except httplib2.HttpLib2Error:
            logging.debug('Received unexpected response from API server while refreshing credentials')
            return False

        # Check if request was accepted
        if response.status == 200:
            try:
                # Get refreshed credentials from response data
                data = json.loads(response.read().decode('utf-8'))
                if 'access_token' in data:
                    self.credentials = {
                        'access_token': data['access_token'],
                        'expires_in': data['expires_in'],
                        'token_type': data['token_type'],
                        'refresh_token': self.credentials['refresh_token']
                    }
            except KeyError or TypeError:
                logging.debug('Received unexpected response from API server while refreshing credentials')
                return False

            # Write new credentials to file and return success state
            self.store_credentials()
            return True
        else:
            # If response code is not 200, something is wrong
            return False

    def get_new_credentials(self, setup=False):
        if not setup:
            # We can't get new credentials if the user isn't manually running
            return False

        # Get code that user has to enter on google's user conscent page
        if not self.user_code:
            self.get_user_code()

        # Declare parameters to request access token
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': self.device_code,
            'grant_type': 'http://oauth.net/grant_type/device/1.0'
        }

        # Encode and parse data for request
        params = urllib.parse.urlencode(params)
        params = params.encode('ascii')

        tries = 0
        while tries <= self.max_retries:
            tries += 1

            try:
                # Poll google to get new credentials as soon as user enters code
                # We are polling once before even showing the user the code,
                # because we don't want to print the code if we can't access the server anyways
                response = urllib.request.urlopen('https://accounts.google.com/o/oauth2/token', params)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    logging.error('Could not get new credentials with user code, '
                                  'check if your client ID and client secret are correct in the config file')
                    return False
                else:
                    logging.exception('Could not get new credentials with user code')
                    return False

            # Show the user the code and verification url, but only once
            if tries == 1:
                print(
                        'Please visit {} and enter the following code: {}'
                        .format(
                            self.verification_url,
                            str(self.user_code)
                        )
                )

            # Decode and parse json response
            str_response = response.read().decode('utf-8')
            data = json.loads(str_response)

            if 'access_token' in data:
                self.credentials = data
                self.store_credentials()
                return True
            elif 'error' in data:
                if data['error'] == 'authorization_pending':
                    # Indicate that we are waiting for user to grant permission
                    util.print_loading_dots('Authorization pending', tries-1)

            # Wait for the given amount of time before trying again
            time.sleep(self.retry_interval)

        return False

    def get_user_code(self):
        # Declare URL
        url = 'https://accounts.google.com/o/oauth2/device/code'

        # Declare parameters to request user code
        params = {
            'client_id': self.client_id,
            'scope': self.scope
        }

        # Encode and parse data for request
        request_data = urllib.parse.urlencode(params)
        request_data = request_data.encode('ascii')

        try:
            # Request auth codes
            response = urllib.request.urlopen(url, request_data)
        except urllib.error.HTTPError:
            logging.error('Could not get user code for authentication')
            return False

        try:
            # Decode and parse json response
            str_response = response.read().decode('utf-8')
            data = json.loads(str_response)

            # Get data from json
            self.device_code = data['device_code']
            self.user_code = data['user_code']
            self.verification_url = data['verification_url']
            self.retry_interval = data['interval']
        except KeyError or TypeError:
            logging.exception('Received unexpected response from API server while getting user code for authentication')
            return False

        return True

    def store_credentials(self):
        try:
            with open(self.credentials_file, 'w') as outfile:
                # Write credentials to file
                json.dump(self.credentials, outfile)
        except FileNotFoundError:
            logging.exception('Could not find file: "' + os.path.basename(self.credentials_file) + '"')
            sys.exit()
        except PermissionError:
            logging.exception('No permission to write to file: "' + os.path.basename(self.credentials_file) + '"')
            sys.exit()
