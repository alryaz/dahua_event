# Dahua event listener for home-assistant (http://home-assistant.io)



1. Install following
```bash
sudo apt install libcurl4-openssl-dev libssl-dev
```
2. Install pycurl on home assistant env
```bash
pip3 install pycurl
```
Code borrowed from https://github.com/johnnyletrois/dahua-watch and made into a home-assistant component

Copy the file your custom_components folder and add your configuration.
The component depends on pycurl, if that won't load, check your dependencies.

You can work with multiple camera's or NVR's
For a device, the only required config item is the host, all other values default to the ones below.
------------

  * Clone or copy the root of the repository into `<config dir>/custom_components/dahua_event`

```bash

  If you are using Windows:
  * Download the zip file and extract the folder inside to your custom_components folder.

```
```yaml
dahua_event:
#
  - name: Laundry
    protocol: http
    host: !secret laundry_cam_ip
    port: 80
    user: !secret nvr_username
    password: !secret nvr_passsword
    events: CrossLineDetection,CrossRegionDetection,LeftDetection,TakenAwayDetection,FaceDetection,AudioMutation,AudioAnomaly
#
  - name: kitchen
    protocol: http
    host: !secret kitchen_cam_ip
    port: 80
    user: !secret nvr_username
    password: !secret nvr_passsword
    events: CrossLineDetection,CrossRegionDetection,LeftDetection,TakenAwayDetection,FaceDetection,AudioMutation,AudioAnomaly
``` 

You can also assign names to channels, if multiple channels are reported by a device.
Just add them at the end of your dahua_event device config:
``` yaml
channels:
    - number: 0
      name: Kitchen
    - number: 2
      name: Garage
``` 


According to the API docs, these events are available:
(availability depends on your device and firmware)
- VideoMotion: motion detection event
- VideoLoss: video loss detection event
- VideoBlind: video blind detection event.
- AlarmLocal: alarm detection event.
- CrossLineDetection: tripwire event
- CrossRegionDetection: intrusion event
- LeftDetection: abandoned object detection
- TakenAwayDetection: missing object detection
- VideoAbnormalDetection: scene change event
- FaceDetection: face detect event
- AudioMutation: intensity change
- AudioAnomaly: input abnormal
- VideoUnFocus: defocus detect event
- WanderDetection: loitering detection event
- RioterDetection: People Gathering event
- ParkingDetection: parking detection event
- MoveDetection: fast moving event
- MDResult: motion detection data reporting event. The motion detect window contains 18 rows and 22 columns. The event info contains motion detect data with mask of every row.
- HeatImagingTemper: temperature alarm event

And here are some events that might work:
- TemperatureAlarm
- BatteryLowPower
- IPConflict
- HotPlug
- StorageLowSpace
- StorageFormat
- StorageNotExist
- ChassisIntruded
