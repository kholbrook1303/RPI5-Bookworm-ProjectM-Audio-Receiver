#!/bin/bash

# Check current HDMI configuration and set the resultion to 1280x720.
# With minor slowness you can set to 1920x1080 however I find this to be more seamless 
RESOLUTION="1280x720"
while read line
    do
    #echo "wlr-randr line: $line"
    device=($(echo $line | grep -Po "(HDMI-\w{1}-\d{1})"))
    if [[ -z "${device[1]}" ]]; then
        :
    else
        echo "Found display device ${device[1]}"
        echo "Setting resolution to $RESOLUTION"
        wlr-randr --output  ${device[1]} --mode $RESOLUTION
    fi
    done<<EOF
    $(wlr-randr)
EOF

# Source profile for mic and aux;  If either does not have a device just put null
# To see a list of devices run 'pactl list sources short'
SOURCE_MIC_DEVICES=(
    "alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono"
)       # This is only for mic.  If none leave parenthesis empty
SOURCE_AUX_DEVICES=(
    "alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback"
)       # This is only for aux.  If none leave parenthesis empty

# Sink profile for audio output
# To see a list of devices run 'pactl list sinks short'
# Note: this is a priority list
SINK_DEVICES=(
    "alsa_output.platform-107c701400.hdmi.hdmi-stereo" 
    "alsa_output.platform-107c706400.hdmi.hdmi-stereo" 
    "alsa_output.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.analog-stereo"
)                                   # HDMI Port 2

# Force OpenGL to use 4.5 instead of 3.0
MESA_GL_VERSION_OVERRIDE=4.5
export MESA_GL_VERSION_OVERRIDE=4.5

# Processes to check to ensure we aren't running twice'
ARVPPROCESSES=("aplay" "arecord" "projectMSDL")

# Close any processes that already running
for process in "${ARVPPROCESSES[@]}"
do
  if pgrep -f "$process" &> /dev/null ; then
    echo "Process $process is running!  Attempting to kill it..."
    sudo killall $process
  fi
done

MIC_DEVICE=false
MIC_DEVICE_SOURCE=null

AUX_DEVICE=false
AUX_DEVICE_SOURCE=null

SNK_DEVICE=false
SNK_DEVICE_SOURCE=null

# Check for user configured source devices
while read line
  do
    devices=($(echo $line | grep -Po "(\d+)\s+(.*?)\s+"))
    echo "Found source device: ${devices[1]}"

    if [[ $MIC_DEVICE == false ]]; then
        for mic in "${SOURCE_MIC_DEVICES[@]}"
        do
          if [[ ${devices[1]} == $mic ]]; then
            MIC_DEVICE=true
            MIC_DEVICE_SOURCE=$mic
            echo "Setting user mic device: $mic"
          fi
        done
    fi
    if [[ $AUX_DEVICE == false ]]; then
        for aux in "${SOURCE_AUX_DEVICES[@]}"
        do
          if [[ ${devices[1]} == $aux ]]; then
            AUX_DEVICE=true
            AUX_DEVICE_SOURCE=$aux
            echo "Setting user aux device: $aux"
          fi
        done
    fi
  done<<EOF
    $(pactl list sources short)
EOF

# Check for a user configured sink device
for sink in "${SINK_DEVICES[@]}" 
do
    while read line
      do
        devices=($(echo $line | grep -Po "(\d+)\s+(.*?)\s+"))
        echo "Found sink device: ${devices[1]}"

        if [[ $SNK_DEVICE == false ]]; then
          if [[ ${devices[1]} == $sink ]]; then
            SNK_DEVICE=true
            SNK_DEVICE_SOURCE=$sink
            echo "Identified sink device: $sink"
          fi
        fi
      done<<EOF
        $(pactl list sinks short)
EOF
done

# Check if both a mic and aux are connected.  This is currently not supported.
if [[ $MIC_DEVICE == true && $AUX_DEVICE == true ]]; then
  echo "Currently only 1 capture device is supported at a time!"
  exit 1
elif [[ $SNK_DEVICE == false ]]; then
  echo "No sink device detected!"
  exit 1
fi

# Enable the configured Sink
pactl set-default-sink "$SNK_DEVICE_SOURCE"

# Increase the default playback device to 100%
amixer sset 'Master' 100%

# Start the projectMSDL visualizations
#/opt/ProjectMSDL/projectMSDL --beatSensitivity=2.0 &>/dev/null & disown;
/usr/bin/python3.11 /opt/ProjectMSDL/projectmWrapper.py &>/dev/null & disown;

# Handle audio based on connected device
if [ $MIC_DEVICE == true ]
then
  pactl set-default-source "$MIC_DEVICE_SOURCE"
  amixer sset 'Capture' 100%    # Increase the default capture device to 100% to increase sound capture
elif [ $AUX_DEVICE == true ]
then
  pactl set-default-source "$AUX_DEVICE_SOURCE"
  amixer sset 'Capture' 75%     # Drop the default capture device to 75% to avoid distortion
  arecord --format=S16_LE --rate=44100 --nonblock | aplay --format=S16_LE --rate=44100
else
  echo "No matching device found!"
  exit 1
fi