import xbmc
import xbmcgui
import xbmcaddon
import json
import time
import sys
import colorsys
import os
import datetime
import math
import urlparse

__addon__      = xbmcaddon.Addon()
__cwd__        = __addon__.getAddonInfo('path')
__resource__   = xbmc.translatePath( os.path.join( __cwd__, 'resources', 'lib' ) )

sys.path.append (__resource__)

from settings import *
from tools import *

try:
  import requests
except ImportError:
  xbmc.log("ERROR: Could not locate required library requests")
  notify("Kodi RaspBee", "ERROR: Could not import Python requests")

xbmc.log("Kodi RaspBee service started, version: %s" % get_version())

capture = xbmc.RenderCapture()
fmt = capture.getImageFormat()
# BGRA or RGBA
# xbmc.log("Raspbee Capture Image format: %s" % fmt)
fmtRGBA = fmt == 'RGBA'

class MyMonitor( xbmc.Monitor ):
  def __init__( self, *args, **kwargs ):
    xbmc.Monitor.__init__( self )

  def onSettingsChanged( self ):
    logger.debuglog("running in mode %s" % str(raspbee.settings.mode))
    last = datetime.datetime.now()
    raspbee.settings.readxml()
    raspbee.update_settings()

monitor = MyMonitor()

class MyPlayer(xbmc.Player):
  duration = 0
  playingvideo = None

  def __init__(self):
    xbmc.Player.__init__(self)
  
  def onPlayBackStarted(self):
    if self.isPlayingVideo():
      self.playingvideo = True
      self.duration = self.getTotalTime()
      state_changed("started", self.duration)

  def onPlayBackPaused(self):
    if self.isPlayingVideo():
      self.playingvideo = False
      state_changed("paused", self.duration)

  def onPlayBackResumed(self):
    if self.isPlayingVideo():
      self.playingvideo = True
      state_changed("resumed", self.duration)

  def onPlayBackStopped(self):
    if self.playingvideo:
      self.playingvideo = False
      state_changed("stopped", self.duration)

  def onPlayBackEnded(self):
    if self.playingvideo:
      self.playingvideo = False
      state_changed("stopped", self.duration)

class Raspbee:
  params = None
  connected = None
  last_state = None
  light = None
  dim_group = None

  def __init__(self, settings, args):
    self.logger = Logger()
    if settings.debug:
      self.logger.debug()

    self.settings = settings
    self._parse_argv(args)

    if self.settings.bridge_user not in ["-", "", None] and self.connected:
      self.update_settings()

    if self.params == {}:
      if self.settings.bridge_ip not in ["-", "", None]:
        self.test_connection()
    elif self.params['action'] == "discover":
      self.logger.debuglog("Starting discovery")
      notify("Bridge discovery", "starting")
      sonuc = self.start_autodiscover()
      raspbee_ip = sonuc['ip']
      raspbee_port = sonuc['port']
      if raspbee_ip != None:
        notify("Bridge discovery", "Found bridge at: %s:%s" % (raspbee_ip,raspbee_port))
        username = self.register_user(raspbee_ip, raspbee_port)
        self.logger.debuglog("Updating settings")
        self.settings.update(bridge_ip = raspbee_ip)
        self.settings.update(bridge_port = raspbee_port)
        self.settings.update(bridge_user = username)
        notify("Bridge discovery", "Finished")
        self.test_connection()
        self.update_settings()
      else:
        notify("Bridge discovery", "Failed. Could not find bridge.")
    else:
      # not yet implemented
      self.logger.debuglog("unimplemented action call: %s" % self.params['action'])

    if self.connected:
      if self.settings.misc_initialflash:
        self.flash_lights()

  def start_autodiscover(self):
    port = 1900
    ip = "239.255.255.250"

    address = (ip, port)
    data = """M-SEARCH * HTTP/1.1
    HOST: %s:%s
    MAN: ssdp:discover
    MX: 3
    ST: upnp:rootdevice
    """ % (ip, port)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) #force udp
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    raspbee_ip = None
    raspbee_port = None
    num_retransmits = 0
    while(num_retransmits < 10) and raspbee_ip == None:
      num_retransmits += 1
      try:
        client_socket.sendto(data, address)
        recv_data, addr = client_socket.recvfrom(2048)
        self.logger.debuglog("received data during autodiscovery: "+recv_data)
        if "IpBridge" in recv_data and "description.xml" in recv_data:
        	url = recv_data.split("LOCATION: ")[1]
        	parsed_url = o = urlparse.urlparse(url)
        	raspbee_ip = parsed_url.hostname
        	raspbee_port = parsed_url.port
        time.sleep(1)
        except socket.timeout:
          break #if the socket times out once, its probably not going to complete at all. fallback to nupnp.

    if raspbee_ip == None:
      #still nothing found, try alternate api
      r=requests.get("https://dresden-light.appspot.com/discover", verify=False)
      j=r.json()
      if len(j) > 0:
        raspbee_ip=j[0]["internalipaddress"]
        raspbee_port=j[0]["internalport"]
        
        self.logger.debuglog("dresden nupnp api returned: "+raspbee_ip)
      else:
        self.logger.debuglog("dresden nupnp api did not find bridge")
        
    return { 'ip': raspbee_ip, 'port': raspbee_port }

  def register_user(raspbee_ip, raspbee_port):
    device = "kodi-raspbee-addon"
    data = '{"devicetype": "%s#%s"}' % (device, xbmc.getInfoLabel('System.FriendlyName')[0:19])
    self.logger.debuglog("sending data: %s" % data)

    r = requests.post('http://%s:%s/api' % (raspbee_ip, raspbee_port), data=data)
    response = r.text
    while "link button not pressed" in response:
      self.logger.debuglog("register user response: %s" % r)
      notify("Bridge discovery", "press link button on bridge")
      r = requests.post('http://%s:%s/api' % (raspbee_ip, raspbee_port), data=data)
      response = r.text 
      time.sleep(3)

    j = r.json()
    self.logger.debuglog("got a username response: %s" % j)
    username = j[0]['success']['username']
    
    return username

  def flash_lights(self):
    self.logger.debuglog("class RaspBee: flashing lights")
    if self.settings.light == 0:
      self.light.flash_light()
    else:
      self.light[0].flash_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].flash_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].flash_light()
    
  def _parse_argv(self, args):
    try:
        self.params = dict(arg.split("=") for arg in args.split("&"))
    except:
        self.params = {}

  def test_connection(self):
    r = requests.get('http://%s:%s/api/%s/config' % \
      (self.settings.bridge_ip, self.settings.bridge_port, self.settings.bridge_user))
    test_connection = r.text.find("name")
    if not test_connection:
      notify("Failed", "Could not connect to bridge")
      self.connected = False
    else:
      notify("Kodi Raspbee", "Connected")
      self.connected = True

  def dim_lights(self):
    self.logger.debuglog("class RaspBee: dim lights")
    self.last_state = "dimmed"
    if self.settings.light == 0:
      self.light.dim_light()
    else:
      self.light[0].dim_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].dim_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].dim_light()

        
  def brighter_lights(self):
    self.logger.debuglog("class RaspBee: brighter lights")
    self.last_state = "brighter"
    if self.settings.light == 0:
      self.light.brighter_light()
    else:
      self.light[0].brighter_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].brighter_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].brighter_light()

  def partial_lights(self):
    self.logger.debuglog("class RaspBee: partial lights")
    self.last_state = "partial"
    if self.settings.light == 0:
      self.light.partial_light()
    else:
      self.light[0].partial_light()
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1].partial_light()
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2].partial_light()

  def update_settings(self):
    self.logger.debuglog("class RaspBee: update settings")
    self.logger.debuglog(settings)
    if self.settings.light == 0 and \
        (self.light is None or type(self.light) != Group):
      self.logger.debuglog("creating Group instance")
      self.light = Group(self.settings)
    elif self.settings.light > 0 and \
          (self.light is None or \
          type(self.light) == Group or \
          len(self.light) != self.settings.light or \
          self.light[0].light != self.settings.light1_id or \
          (self.settings.light > 1 and self.light[1].light != self.settings.light2_id) or \
          (self.settings.light > 2 and self.light[2].light != self.settings.light3_id)):
      self.logger.debuglog("creating Light instances")
      self.light = [None] * self.settings.light
      self.light[0] = Light(self.settings.light1_id, self.settings)
      if self.settings.light > 1:
        xbmc.sleep(1)
        self.light[1] = Light(self.settings.light2_id, self.settings)
      if self.settings.light > 2:
        xbmc.sleep(1)
        self.light[2] = Light(self.settings.light3_id, self.settings)

class HSVRatio:
  cyan_min = float(4.5/12.0)
  cyan_max = float(7.75/12.0)

  def __init__(self, hue=0.0, saturation=0.0, value=0.0, ratio=0.0):
    self.h = hue
    self.s = saturation
    self.v = value
    self.ratio = ratio

  def average(self, h, s, v):
    self.h = (self.h + h)/2
    self.s = (self.s + s)/2
    self.v = (self.v + v)/2

  def averageValue(self, overall_value):
    if self.ratio > 0.5:
      self.v = self.v * self.ratio + overall_value * (1-self.ratio)
    else:
      self.v = (self.v + overall_value)/2
    

  def hue(self, fullSpectrum):
    if fullSpectrum != True:
      if self.s > 0.01:
        if self.h < 0.5:
          #yellow-green correction
          self.h = self.h * 1.17
          #cyan-green correction
          if self.h > self.cyan_min:
            self.h = self.cyan_min
        else:
          #cyan-blue correction
          if self.h < self.cyan_max:
            self.h = self.cyan_max

    h = int(self.h*65535) # on a scale from 0 <-> 65535
    s = int(self.s*255)
    v = int(self.v*255)
    if v < raspbee.settings.ambilight_min:
      v = raspbee.settings.ambilight_min
    if v > raspbee.settings.ambilight_max:
      v = raspbee.settings.ambilight_max
    return h, s, v

  def __repr__(self):
    return 'h: %s s: %s v: %s ratio: %s' % (self.h, self.s, self.v, self.ratio)

class Screenshot:
  def __init__(self, pixels, capture_width, capture_height):
    self.pixels = pixels
    self.capture_width = capture_width
    self.capture_height = capture_height

  def most_used_spectrum(self, spectrum, saturation, value, size, overall_value):
    # color bias/groups 6 - 36 in steps of 3
    colorGroups = settings.color_bias
    if colorGroups == 0:
      colorGroups = 1
    colorHueRatio = 360 / colorGroups

    hsvRatios = []
    hsvRatiosDict = {}

    for i in range(360):
      if spectrum.has_key(i):
        #shift index to the right so that groups are centered on primary and secondary colors
        colorIndex = int(((i+colorHueRatio/2) % 360)/colorHueRatio)
        pixelCount = spectrum[i]

        if hsvRatiosDict.has_key(colorIndex):
          hsvr = hsvRatiosDict[colorIndex]
          hsvr.average(i/360.0, saturation[i], value[i])
          hsvr.ratio = hsvr.ratio + pixelCount / float(size)

        else:
          hsvr = HSVRatio(i/360.0, saturation[i], value[i], pixelCount / float(size))
          hsvRatiosDict[colorIndex] = hsvr
          hsvRatios.append(hsvr)

    colorCount = len(hsvRatios)
    if colorCount > 1:
      # sort colors by popularity
      hsvRatios = sorted(hsvRatios, key=lambda hsvratio: hsvratio.ratio, reverse=True)
      # logger.debuglog("hsvRatios %s" % hsvRatios)
      
      #return at least 3
      if colorCount == 2:
        hsvRatios.insert(0, hsvRatios[0])
      
      hsvRatios[0].averageValue(overall_value)
      hsvRatios[1].averageValue(overall_value)
      hsvRatios[2].averageValue(overall_value)
      return hsvRatios

    elif colorCount == 1:
      hsvRatios[0].averageValue(overall_value)
      return [hsvRatios[0]] * 3

    else:
      return [HSVRatio()] * 3

  def spectrum_hsv(self, pixels, width, height):
    spectrum = {}
    saturation = {}
    value = {}

    size = int(len(pixels)/4)
    pixel = 0

    i = 0
    s, v = 0, 0
    r, g, b = 0, 0, 0
    tmph, tmps, tmpv = 0, 0, 0
    
    for i in range(size):
      if fmtRGBA:
        r = pixels[pixel]
        g = pixels[pixel + 1]
        b = pixels[pixel + 2]
      else: #probably BGRA
        b = pixels[pixel]
        g = pixels[pixel + 1]
        r = pixels[pixel + 2]
      pixel += 4

      tmph, tmps, tmpv = colorsys.rgb_to_hsv(float(r/255.0), float(g/255.0), float(b/255.0))
      s += tmps
      v += tmpv

      # skip low value and saturation
      if tmpv > 0.25:
        if tmps > 0.33:
          h = int(tmph * 360)

          # logger.debuglog("%s \t set pixel r %s \tg %s \tb %s" % (i, r, g, b))
          # logger.debuglog("%s \t set pixel h %s \ts %s \tv %s" % (i, tmph*100, tmps*100, tmpv*100))

          if spectrum.has_key(h):
            spectrum[h] += 1 # tmps * 2 * tmpv
            saturation[h] = (saturation[h] + tmps)/2
            value[h] = (value[h] + tmpv)/2
          else:
            spectrum[h] = 1 # tmps * 2 * tmpv
            saturation[h] = tmps
            value[h] = tmpv

    overall_value = v / float(i)
    # s_overall = int(s * 100 / i)
    return self.most_used_spectrum(spectrum, saturation, value, size, overall_value)

def run():
  player = None
  last = datetime.datetime.now()

  while not xbmc.abortRequested:
    
    if raspbee.settings.mode == 1: # theatre mode
      if player == None:
        logger.debuglog("creating instance of player")
        player = MyPlayer()
      xbmc.sleep(500)
    if raspbee.settings.mode == 0: # ambilight mode
      if raspbee.settings.ambilight_dim and raspbee.dim_group == None:
        logger.debuglog("creating group to dim")
        tmp = raspbee.settings
        tmp.group_id = tmp.ambilight_dim_group
        raspbee.dim_group = Group(tmp)
      
      if player == None:
        player = MyPlayer()
      else:
        xbmc.sleep(100)

      capture.waitForCaptureStateChangeEvent(1000/60)
      if capture.getCaptureState() == xbmc.CAPTURE_STATE_DONE:
        if player.playingvideo:
          screen = Screenshot(capture.getImage(), capture.getWidth(), capture.getHeight())
          hsvRatios = screen.spectrum_hsv(screen.pixels, screen.capture_width, screen.capture_height)
          if raspbee.settings.light == 0:
            fade_light_hsv(raspbee.light, hsvRatios[0])
          else:
            fade_light_hsv(raspbee.light[0], hsvRatios[0])
            if raspbee.settings.light > 1:
              xbmc.sleep(4)
              fade_light_hsv(raspbee.light[1], hsvRatios[1])
            if raspbee.settings.light > 2:
              xbmc.sleep(4)
              fade_light_hsv(raspbee.light[2], hsvRatios[2])

def fade_light_hsv(light, hsvRatio):
  fullSpectrum = light.fullSpectrum
  h, s, v = hsvRatio.hue(fullSpectrum)
  hvec = abs(h - light.hueLast) % int(65535/2)
  hvec = float(hvec/128.0)
  svec = s - light.satLast
  vvec = v - light.valLast
  distance = math.sqrt(hvec * hvec + svec * svec + vvec * vvec)
  if distance > 0:
    duration = int(3 + 27 * distance/255)
    # logger.debuglog("distance %s duration %s" % (distance, duration))
    light.set_light2(h, s, v, duration)


def state_changed(state, duration):
  logger.debuglog("state changed to: %s" % state)

  #detect pause for refresh change
  pauseafterrefreshchange = 0
  response = json.loads(xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Settings.GetSettingValue", "params":{"setting":"videoplayer.pauseafterrefreshchange"},"id":1}'))
  #logger.debuglog(isinstance(response, dict))
  if "result" in response and "value" in response["result"]:
    pauseafterrefreshchange = int(response["result"]["value"])

  if duration < 300 and raspbee.settings.misc_disableshort:
    logger.debuglog("add-on disabled for short movies")
    return

  if state == "started":
    logger.debuglog("retrieving current setting before starting")
    
    if raspbee.settings.light == 0:
      raspbee.light.get_current_setting()
    else:
      raspbee.light[0].get_current_setting()
      if raspbee.settings.light > 1:
        xbmc.sleep(1)
        raspbee.light[1].get_current_setting()
      if raspbee.settings.light > 2:
        xbmc.sleep(1)
        raspbee.light[2].get_current_setting()

    if raspbee.settings.mode == 0: # ambilight mode
      #start capture when playback starts
      capture_width = 32 #100
      capture_height = capture_width / capture.getAspectRatio()
      if capture_height == 0
        capture_height = capture_width #fix for divide by zero.
      logger.debuglog("capture %s x %s" % (capture_width, capture_height))
      capture.capture(int(capture_width), int(capture_height), xbmc.CAPTURE_FLAG_CONTINUOUS)

  if (state == "started" and pauseafterrefreshchange == 0) or state == "resumed":
    if raspbee.settings.mode == 0 and raspbee.settings.ambilight_dim: # only if a complete group
      logger.debuglog("dimming group for ambilight")
      raspbee.dim_group.dim_light()
    else:
      logger.debuglog("dimming lights")
      raspbee.dim_lights()
  elif state == "paused" and raspbee.last_state == "dimmed":
    #only if its coming from being off
    if raspbee.settings.mode == 0 and raspbee.settings.ambilight_dim:
      # Be persistent in restoring the lights 
      # (prevent from being overwritten by an ambilight update)
      for i in range(0, 3):
        logger.debuglog("partial lights")
        raspbee.dim_group.partial_lights()
        time.sleep(1)
    else:
      raspbee.partial_lights()
  elif state == "stopped":
    if raspbee.settings.mode == 0 and raspbee.settings.ambilight_dim:
      # Be persistent in restoring the lights 
      # (prevent from being overwritten by an ambilight update)
      for i in range(0, 3):
        logger.debuglog("brighter lights")
        raspbee.dim_group.brighter_light()
        time.sleep(1)
    else:
      raspbee.brighter_lights()

if ( __name__ == "__main__" ):
  settings = settings()
  logger = Logger()
  if settings.debug == True:
    logger.debug()
  
  args = None
  if len(sys.argv) == 2:
    args = sys.argv[1]
  raspbee = Raspbee(settings, args)
  while not raspbee.connected:
    logger.debuglog("not connected")
    time.sleep(1)
  run()
