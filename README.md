script.kodi.raspbee.ambilight
=========================

A Kodi add-on that controls Raspbee Bridge. In "Theater mode" the add-on dims the the lights as soon as a movie starts playing, and turns the lights back on once the movie is done. "Ambilight mode" turns your lights in a room-sized ambilight.

`script.kodi.raspbee.ambilight` project is a Raspbee specialized fork of @cees-elzinga 's and @michaelrcarroll 's original work.

1.0 Release
==================
Check out the release version in the [Releases](https://github.com/fatihboy/script.kodi.raspbee.ambilight/releases) section. 

Debugging
---------
Please turn on Debug Logging through the addon (Configure -> Advanced Settings -> Debug Logging) and follow the procedure at http://kodi.wiki/view/Log_file/Easy to upload a log file. Provide a link to your logfile in the issue.

Installation
------------

The add-on depends on the Kodi add-on "requests" for the ambilight mode.

**Kodi add-on script.module.requests**

 - Download the add-on as a ZIP file from https://github.com/beenje/script.module.requests
  - (Right click on the "ZIP" icon and select "Download Linked File").
 - Open Kodi
 - Go to `System -> Settings -> Add-ons -> Install from zip file`
 - Select the zip file.

**Kodi add-on script.kodi.raspbee.ambilight**

 - Download the add-on as a ZIP file from the top of this page
   - (Right click on the "ZIP" icon and select "Download Linked File")
 - Open Kodi
 - Go to `System -> Settings -> Add-ons -> Install from zip file`
 -  Restart Kodi and configure the add-on:
   - `System -> Settings -> Add-ons -> Enabled add-ons -> Services -> Kodi Philips Hue`
   - Run `Start auto discovery of bridge IP, bridge Port and User`.

Note for Raspberry Pi users:

 - Save the add-on configuration by exiting Kodi before shutting down the Pi completely
 - Ambilight mode doesn't work on a Raspberry Pi due to the way it renders video