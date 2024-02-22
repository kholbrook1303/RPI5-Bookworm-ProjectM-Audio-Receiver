#!/bin/bash

# Source profile for mic and aux;  If either does not have a device just put null
# To see a list of devices run 'pactl list sources short'
SOURCE_MIC_DEVICE="alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono"     # This is only for mic.  If none set to null
SOURCE_AUX_DEVICE="alsa_input.usb-C-Media_Electronics_Inc._USB_Audio_Device-00.mono-fallback"       # This is only for aux.  If none set to null

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

MICDEVICE=false
AUXDEVICE=false
SNKDEVICE=false

# Check for user configured source devices
while read line
  do
    devices=($(echo $line | grep -Po "(\d+)\s+(.*?)\s+"))
    echo "Found source device: ${devices[1]}"
    if [[ ${devices[1]} == $SOURCE_MIC_DEVICE ]]; then
      MICDEVICE=true
      echo "Identified user mic device: $SOURCE_MIC_DEVICE"
    elif [[ ${devices[1]} == $SOURCE_AUX_DEVICE ]]; then
      AUXDEVICE=true
      echo "Identified user aux device: $SOURCE_AUX_DEVICE"
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
        echo "Sink: ${devices[1]}"
        if [[ ${devices[1]} == $sink ]]; then
          SNKDEVICE=true
          echo "Identified sink device: $sink"

          # Enable the configured Sink
          pactl set-default-sink "$sink"

          break
        fi
      done<<EOF
        $(pactl list sinks short)
EOF
    if [[ $SNKDEVICE == true ]]; then
      break
    fi
done

# Check if both a mic and aux are connected.  This is currently not supported.
if [[ $MICDEVICE == true && $AUXDEVICE == true ]]; then
  echo "Currently only 1 capture device is supported at a time!"
  exit 1
elif [[ $SNKDEVICE == false ]]; then
  echo "No sink device detected!"
  exit 1
fi

# Start the projectMSDL visualizations
#/opt/ProjectMSDL/projectMSDL --beatSensitivity=2.0 &>/dev/null & disown;
/usr/bin/python3.11 /opt/ProjectMSDL/projectmWrapper.py &>/dev/null & disown;

# Handle audio based on connected device
if [ $MICDEVICE == true ]
then
  pactl set-default-source "$SOURCE_MIC_DEVICE"
  amixer sset 'Capture' 100%    # Increase the default capture device to 100% to increase sound capture
elif [ $AUXDEVICE == true ]
then
  pactl set-default-source "$SOURCE_AUX_DEVICE"
  amixer sset 'Capture' 75%     # Drop the default capture device to 75% to avoid distortion
  arecord --format=S16_LE --rate=44100 | aplay --format=S16_LE --rate=44100
else
  echo "No matching device found!"
  exit 1
fi