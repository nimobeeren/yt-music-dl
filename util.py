import datetime
import re


def remove_illegal_characters(filename):
    return re.sub("[/\\`*|;\"'’:<>]", "", filename)


def remove_quotes(string):
    return re.sub("[\"'’]", "", string)


def get_formatted_date():
    # Get current datetime
    now = datetime.datetime.now()

    # Make sure the month is a two-digit number
    if now.month < 10:
        month = "0" + repr(now.month)
    else:
        month = repr(now.month)

    return repr(now.year) + "-" + month


def get_url(video_id):
    return "https://www.youtube.com/watch?v=" + video_id


def print_loading_dots(message, count):
    i = count % 3
