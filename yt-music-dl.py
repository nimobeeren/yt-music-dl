#!/usr/bin/env python3

# Credits:
# http://guy.carpenter.id.au/gaugette/2012/11/06/using-google-oauth2-for-devices/

# TODO: Progress indication during downloading/converting
# TODO: Custom tagging in config file (maybe too complex for this kind of app)
# TODO: Add more tagging fields (?)
# TODO: Album art from video thumbnail
# TODO: Consistent use of either httplib2 or urllib

import argparse
import atexit
import configparser
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import youtube_dl

import auth
import tagging
import util

# region Globals
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(CURRENT_DIR, 'yt-music-dl.log')
CONFIG_FILE = os.path.join(CURRENT_DIR, 'config.ini')
CREDENTIALS_FILE = os.path.join(CURRENT_DIR, 'credentials.json')
PID_FILE = os.path.join(tempfile.gettempdir(), 'yt-music-dl.pid')
# endregion


def main():
    # Parse command line arguments
    args = init_args()

    # Configure logging options
    configure_logger(args.debug)

    # Check if process is already running
    if os.path.isfile(PID_FILE):
        logging.debug("Process is already running, exiting")
        sys.exit()
    else:
        pid = str(os.getpid())
        try:
            with open(PID_FILE, 'w') as file:
                file.write(pid)
        except PermissionError:
            logging.exception('No permission to create PID file, make sure you are running as root')
            sys.exit()
    
    # Configure cleanup at exit
    atexit.register(cleanup)

    # Read the configuration file
    config = configparser.ConfigParser()
    if not os.path.isfile(CONFIG_FILE):
        logging.critical('Could not find config file "' + os.path.basename(CONFIG_FILE) + '"')
        sys.exit()
    try:
        config.read(CONFIG_FILE)
    except FileNotFoundError:
        logging.exception('Could not find config file "' + os.path.basename(CONFIG_FILE) + '"')
        sys.exit()
    except PermissionError:
        logging.exception('No permission to read config file "' + os.path.basename(CONFIG_FILE) + '"')
        sys.exit()

    # Get some data from the config file
    try:
        output_dir = config['GENERAL']['OutputDirectory']
        playlist_id = config['GENERAL']['PlaylistID']
        client_id = config['AUTHENTICATION']['ClientID']
        client_secret = config['AUTHENTICATION']['ClientSecret']
    except KeyError:
        logging.exception(
            'Something is wrong with the content of the config file "' + os.path.basename(CONFIG_FILE) + '"'
        )
        sys.exit()
    logging.debug('Read config file')

    # Check if any essential config fields are empty
    if not output_dir:
        logging.critical('Please enter an output directory in the config file.')
        return

    if not playlist_id:
        logging.critical('Please enter a playlist ID in the config file.')
        return

    if not client_id or not client_secret:
        logging.critical('Please enter your client ID and client secret in the config file.')
        return

    # If setup flag is passed, run first-time setup and exit
    if args.setup:
        logging.debug('Running setup...')
        setup(client_id, client_secret, CREDENTIALS_FILE)
        return

    # Log the start of the run
    logging.info('[START] Started run')

    # Get credentials to access API
    oauth = auth.OAuth(client_id, client_secret, CREDENTIALS_FILE)

    # Get content of YouTube playlist
    playlist_items = get_playlistitems(oauth, playlist_id)
    logging.debug('Got playlist content')

    for playlist_item in playlist_items:
        # Get some info about the playlist item
        video_id = playlist_item['snippet']['resourceId']['videoId']
        video_title = playlist_item['snippet']['title']
        channel = get_channel_name(oauth, video_id)
        url = util.get_url(video_id)

        # Configure temporary storage location
        temp_dir = tempfile.gettempdir()
        temp_name = video_id + '.mp3'
        temp_path = os.path.join(temp_dir, temp_name)

        # Download video and extract audio
        logging.info('Downloading video: {} ({})'.format(video_title, video_id))
        download_audio(url, temp_dir)

        # Apply tags
        try:
            autotag(temp_path, video_title, config, channel)
            logging.debug('Tagged mp3')
        except KeyError:
            logging.error('Could not tag mp3 file')

        # Move file to network storage
        try:
            # Get month based subdir value from config file
            create_subfolder = config['GENERAL'].getboolean('MonthBasedSubdir')
        except KeyError:
            logging.exception(
                'Something is wrong with the content of the config file "' + os.path.basename(CONFIG_FILE) + '"'
            )
            sys.exit()

        # Join subdir with original output dir, if preferred
        if create_subfolder:
            final_dir = os.path.join(output_dir, util.get_formatted_date())
        else:
            final_dir = output_dir

        # Get filename and path from video title and above mentioned (sub)directory
        final_name = util.remove_illegal_characters(video_title + '.mp3')
        final_path = os.path.join(final_dir, final_name)

        # Create directory if it doesn't already exist
        if not os.path.exists(final_dir):
            try:
                os.makedirs(final_dir)
            except PermissionError:
                logging.exception('No permission to create output directory "' + final_dir + '"')
                sys.exit()

        # Move file to final destination
        try:
            shutil.copy(temp_path, final_path)
            os.remove(temp_path)
        except PermissionError:
            logging.exception('No permission to create output directory "' + final_dir + '"')
            sys.exit()
        except FileNotFoundError:
            logging.exception('Could not find output directory or downloaded file has gone missing.' +
                              'Check "' + os.path.basename(CONFIG_FILE) + '" to see if OutputDirectory is correct.')
            sys.exit()

        logging.debug('Moved file to final destination')

        # Delete the playlistitem after downloading
        delete_playlist_item(oauth, playlist_item)
        logging.debug('Deleted playlist item')

    # If the queue is emtpy, log it
    if len(playlist_items) == 0:
        logging.info('Download queue is empty')

    # Log the end of the run
    logging.info('[END] Finished run')


def progress_hook(d):
    if d['status'] == 'finished':
        logging.info('Converting video')


def configure_logger(debug):
    # Get root logger object so that we can add handlers to it
    logger = logging.getLogger()

    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Create logging handler for log file
    try:
        handler = logging.FileHandler(LOG_FILE)
    except PermissionError:
        logging.exception('No permission to write to log file')
        sys.exit()
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Create lgging handler for stdout
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt='[%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def get_channel_name(oauth, video_id):
    url = 'https://www.googleapis.com/youtube/v3/videos'

    params = {
        'part': 'snippet',
        'id': video_id,
    }

    # Header contains authorization data
    header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}

    # Encode and parse parameters into URL
    params = urllib.parse.urlencode(params)
    full_url = url + '?' + params

    # Create request object and add authentication header
    req = urllib.request.Request(full_url)
    for k in header:
        req.add_header(k, header[k])

    # Get response from API request
    try:
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Get a new access token
            oauth.authorize_credentials()

            # Update authorization header for request
            req.remove_header('Authorization')
            header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}
            for k in header:
                req.add_header(k, header[k])

            # Retry request with new access token
            try:
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError:
                logging.exception('Could not complete API request to get channel name')
                sys.exit()
        else:
            logging.exception('Could not complete API request to get channel name')
            sys.exit()

    # Decode and parse json response
    str_response = response.read().decode('utf-8')
    data = json.loads(str_response)

    # Return the channel title
    try:
        return data['items'][0]['snippet']['channelTitle']
    except KeyError:
        logging.exception('Received unexpected response from API server while getting channel name')
        sys.exit()


def get_playlistitems(oauth, playlist_id):
    # Declare request URL
    url = 'https://www.googleapis.com/youtube/v3/playlistItems'

    # Declare header with authorization info
    header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}

    # Declare parameters
    params = {
        'part': 'snippet',
        'playlistId': playlist_id,
        'maxResults': 50  # 0 - 50 are accepted
    }

    # Encode and parse parameters into URL
    params = urllib.parse.urlencode(params)
    full_url = url + '?' + params

    # Create request object and add authentication header
    req = urllib.request.Request(full_url)
    for k in header:
        req.add_header(k, header[k])

    try:
        # Get response from API request
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Get a new access token
            oauth.authorize_credentials()

            # Update authorization header for request
            req.remove_header('Authorization')
            header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}
            for k in header:
                req.add_header(k, header[k])

            try:
                # Retry request with new access token
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError:
                logging.exception('Could not complete API request to get playlist content')
                sys.exit()
        elif e.code == 404:
            logging.critical('Could not complete API request to get playlist content, ' + 
                             'check if playlist ID in "' + os.path.basename(CONFIG_FILE) + '" is correct')
            sys.exit()
        else:
            logging.exception('Could not complete API request to get playlist content')
            sys.exit()

    try:
        # Decode and parse json response
        str_response = response.read().decode('utf-8')
        playlistitems_list = json.loads(str_response)

        # Return the items from the list
        return playlistitems_list['items']
    except KeyError:
        logging.exception('Received unexpected response from API server while getting playlist content')
        sys.exit()


def download_audio(url, out_dir):
    # Set options for youtube-dl
    ydl_opts = {
        'outtmpl': os.path.join(out_dir, '%(id)s.%(ext)s'),
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
        'logger': logging.getLogger(),
        'progress_hooks': [progress_hook]
    }

    # Download and extract audio from url
    try:
        youtube_dl.YoutubeDL(ydl_opts).download([url])
    except PermissionError:
        logging.exception('No permission to run youtube_dl, try running as root')
        sys.exit()


def autotag(path, video_title, config, channel=None):
    # Compile regex
    p = re.compile(r'(.*)(?:\s+-\s+)(.*)')

    # Match regex against YouTube video title
    m = p.match(video_title)

    # Check if regex matches. If not, don't tag anything at all
    if m:
        # Get artist and title tags from regex
        artist = m.group(1)
        title = m.group(2)
        genre = None

        # Set genre based on channel
        logging.debug('Channel name: ' + channel.lower())
        for key in config['CHANNELS']:
            if channel.lower() == str(key).lower():
                genre = config['CHANNELS'][key]

        # Create tag objects and add them to a list
        tags = [
            tagging.Tag('artist', artist),
            tagging.Tag('title', title),
            tagging.Tag('genre', genre)
        ]

        # tags = tagging.Tag('artist', artist)

        # Output debug tagging info
        # <Field>: <Value>
        for tag in tags:
            logging.debug(str(tag.fieldname) + ': ' + str(tag.value))

        # Apply tags to MP3 file
        tagging.apply_tags(tags, path)


def delete_playlist_item(oauth, playlist_item):
    # Get the unique id of the playlist item
    pi_id = playlist_item['id']

    # Declare request URL
    url = 'https://www.googleapis.com/youtube/v3/playlistItems'

    # Declare header with authorization info
    header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}

    # Declare parameters for request
    params = {'id': pi_id}

    # Encode and parse parameters into URL
    params = urllib.parse.urlencode(params)
    full_url = url + '?' + params

    # Create opener object
    # TODO: Try without opener object
    opener = urllib.request.build_opener(urllib.request.HTTPHandler)

    # Create request object
    req = urllib.request.Request(full_url)

    # Add authentication header
    for k in header:
        req.add_header(k, header[k])

    # Set request method to DELETE
    req.get_method = lambda: 'DELETE'

    try:
        # Get response from API request
        opener.open(req)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Get a new access token
            oauth.authorize_credentials()

            # Update authorization header for request
            req.remove_header('Authorization')
            header = {'Authorization': (oauth.credentials['token_type'] + ' ' + oauth.credentials['access_token'])}
            for k in header:
                req.add_header(k, header[k])

            # Retry request with new access token
            try:
                opener.open(req)
            except urllib.error.HTTPError:
                logging.exception('Received unexpected response from API server while deleting playlist item')
                sys.exit()
        else:
            logging.exception('Received unexpected response from API server while deleting playlist item')
            sys.exit()


def setup(client_id, client_secret, credentials_file):
    # If either client id or client secret are missing, tell the user to go get them and exit
    if client_id.isspace() or client_secret.isspace():
        print('Please enter your client ID and client secret in the config.ini file, and run this setup again.')
        return

    # Get new credentials
    auth.OAuth(client_id, client_secret, credentials_file, True)

    logging.info('Setup completed. This program can now run autonomously.')


def init_args():
    parser = argparse.ArgumentParser(description='Automatically download and tag music from a YouTube playlist')
    parser.add_argument('-d', '--debug', action='store_true', help='Write debug info to stdout and log file')
    parser.add_argument('--setup', action='store_true', help='Perform first-time setup so that the program can run autonomously')
    return parser.parse_args()


def cleanup():
    os.unlink(PID_FILE)


if __name__ == '__main__':
    main()
