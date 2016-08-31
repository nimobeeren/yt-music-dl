# yt-music-dl
Command-line program to easily download and tag music from a YouTube playlist.

## Installation
1. Clone the repo, preferably onto a system that is running most of the time.

2. Install the [dependencies](#dependencies).

3. Open the [Google Cloud Console](https://console.cloud.google.com) and log in to a Google account. If you're not already there, go to [IAM & Admin](https://console.cloud.google.com/iam-admin) --> [All projects](https://console.cloud.google.com/iam-admin/projects). Click 'Create project', give it a name, such as `yt-music-dl`, and click 'Create'.

4. Go to [API Manager](https://console.cloud.google.com/apis) --> [Library](https://console.cloud.google.com/apis/library) and click on YouTube Data API. Click the 'Enable' button at the top-left.

5. In the left-hand menu, go to [Credentials](https://console.cloud.google.com/apis/credentials). Click 'Create credentials' and select 'OAuth client ID'. Click 'Configure consent screen' and fill in a name you like. Save, select application type 'Other' and enter a name for the device the yt-music-dl will be running on. Click the Create button.
<br>You will now be presented with a client ID and a client secret. Open the `config.ini` file from the repo and copy these strings to their respective places in the `AUTHENTICATION` section.

6. Create a playlist on YouTube and copy the ID, which is the part after `?list=` in the URL. Paste this ID to `PlaylistID` in the `config.ini` file. Fill in an output directory and configure the program however you like.

7. Run the first-time setup by typing `sudo python3 yt-music-dl --setup`.
<br>You must log in to the same Google account you use for YouTube, but that does not have to be the same account as used in step 3.

Whenever you run yt-music-dl.py, the program will download any video you put in your playlist as MP3, tag it, and then remove it from the playlist. To automatically download video's without user intervention, see [Scheduling](#scheduling).

### Scheduling

You can schedule the program to run periodically, by using `cron`. This way songs added to your playlist will be downloaded without any manual intervention.

Run `sudo crontab -e` and add a line such as this:

`*/15 * * * * /path/to/python3 /path/to/yt-music-dl.py`

Check out [this how-to](https://help.ubuntu.com/community/CronHowto) if you want to learn more about `cron`.

## Dependencies

This program requires the following Python libraries to run:

* `mutagen`
* `youtube-dl`

Install these dependencies by typing `sudo pip3 install <package name>`. The program will not function correctly without them.

## Usage

`yt-music-dl.py [-h] [-d] [--setup]`

Optional arguments:
```
  -h, --help   Show this help message and exit
  -d, --debug  Write debug info to stdout and log file
  --setup      Perform first-time setup so that the program can run autonomously
```

## Credits
Thanks to Guy Carpenter, for sharing [his knowledge](http://guy.carpenter.id.au/gaugette/2012/11/06/using-google-oauth2-for-devices/) about OAuth for devices.

## Author
Nimo Beeren (nimobeeren@gmail.com)

## License
MIT License

Copyright (c) 2016 Nimo Beeren

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
