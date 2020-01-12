# Dahua Camera Event For HassIO

## HACS installation
(Work in progress)

## Manual installation (via GitHub)
1. Clone repository to a spare directory
1. Create `custom_components` folder inside your configuration directory
1. Copy contents of `custom_components` folder from the repository to the new folder from the previous step
1. Add configuration similar to example shown below

## Example configuration
### Configure devices
```yaml
dahua_events:
#
  - name: Laundry
    protocol: http
    host: !secret laundry_cam_ip
    port: 80
    user: !secret nvr_username
    password: !secret nvr_passsword
    events:
      - CrossLineDetection
      - CrossRegionDetection
      - LeftDetection
      - TakenAwayDetection
      - FaceDetection
      - AudioMutation
      - AudioAnomaly
    channels:
      - number: 1
        name: Laundromat
#
  - name: Home
    protocol: http
    host: !secret home_nvr_ip
    port: 80
    user: !secret nvr_username
    password: !secret nvr_passsword
    events: [CrossLineDetection,CrossRegionDetection,LeftDetection,TakenAwayDetection,FaceDetection,AudioMutation,AudioAnomaly]
    channels: [1,2,3,4]
```

### Create automations
```yaml
automation:
#
  - alias: 'Dahua camera event'
    initial_state: 'on'
    trigger:
      - platform: event
        event_type: dahua_event_received
        event_data:
          code: VideoMotion
          action: Start
    action:
      - service: notify.html5
        data_template:
          title: "Camera Event"
          message: "Movement detected at {{ trigger.event.data.channel_name }}"
```
