# Raspberry Pi 5 - ProjectM Audio Receiver (Visualizations Projector)

## What is this?
The ProjectM Audio Receiver concept will enable your Raspberry Pi to project visualizations through HDMI that react to audio provided by either a microphone input (capturing surrounding audio) or an auxiliary input (capturing audio through 3.5mm audio cable).  

## But why?
The background history behind this was to have visualizations on the television that reacted to a turntable that was playing in the same room.  Growing up I used to enjoy using Winamp with the Milkdrop visualizations build by Ryan Geiss.  These visualizations were proprietary on Windows but have since been ported to other OSs with the help of the ProjectM team.  Since the release of the Raspberry Pi 5, there is now adequate processing power to run allot of these visualizations.

## Coming Soon...
* Better handling/setup of devices used
* A2DP Audio Streaming: There is still work to be doe to see if the onboard Bluetooth chip is capable of A2DP audio streaming.  A2DP streaming needs to be supported whether it be with the onboard chip or a USB dongle.
* User Interface:  Include an optional startup UI with a selection for the input/output devices the user would like to connect to allowing multiple devices to be connected simultaneously.

## Hardware Requirements:
```
Raspberry Pi 5 with an SD card and power supply
Case with cooling fan (I used the Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan)
HDMI Cable
USB Microphone (Can be a USB microphone or a USB 3.5mm audio input)
```

## Software Requirements:
```
Raspberry Pi OS Bookworm or Ubuntu Desktop for Raspberry Pi 23.10
```

## Initial Setup
Make sure the OS is up-to-date
```
sudo apt update
sudo apt upgrade
```

## Building libprojectM 
### Install the build tools and dependencies
Get the mandatory packages:
```
sudo apt install build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git
```

Install additional features:
```
sudo apt install libsdl2-dev # for building the integrated developer test UI
sudo apt install llvm-dev # for using the experimental LLVM Jit
```

### Download the projectM sources
Clone the latest branch and update external dependencies
```
git clone https://github.com/projectM-visualizer/projectm.git ~/ProjectM/
cd ~/ProjectM/
git fetch --all --tags
git submodule init
git submodule update
```

### Build and install projectM
Configure the project
```
mkdir build
cd build
cmake -DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local ..
cmake --build . --parallel && sudo cmake --build . --target install
```

## Building libPico-dev
Because the current repository contains a problematic version of libPico-dev, we must build from source.

Obtain a tested working build of libPico-dev
```
cd ~
wget https://pocoproject.org/releases/poco-1.12.5/poco-1.12.5-all.tar.bz2
tar -xjf poco-1.12.5-all.tar.bz2
cd poco-1.12.5-all/
mkdir cmake-build
cd cmake-build
cmake ..
cmake --build . --config Release
sudo cmake --build . --target install
```
You will have to move the libs for projectMSDL frontend to work (Needs further investigation)
```
sudo cp /usr/local/lib/libPoco* /usr/lib/
```
## Building ProjectM SDL2 Frontend
### Download the SDL2 Frontend sources
```
cd ~
git clone https://github.com/projectM-visualizer/frontend-sdl2.git
```

### Build and install SDL2 Frontend
```
cd frontend-sdl2/
mkdir build
cd build
cmake ..
make
```

Copy build application to standard directory
```
sudo mkdir /opt/ProjectMSDL
sudo chmod 777 -R /opt/ProjectMSDL
cp -r ~/frontend-sdl2/build/src/* /opt/ProjectMSDL/
```

Adjust projectMSDL.properties to suit the Raspberry Pi.  Change the following configuratios to the below:
```
window.fullscreen = true
projectM.meshX = 64
projectM.meshY = 32
```

## Setup A2DP bluetooth audio receiver
Make the Pi permanently discoverable as an A2DP Sink.
```
sudo nano /etc/bluetooth/main.conf
```

And add / uncomment / change
```
...
Class = 0x41C
...
DiscoverableTimeout = 0
```

```
sudo systemctl restart bluetooth
```

```
bluetoothctl
[bluetooth]# power on
[bluetooth]# discoverable on
[bluetooth]# pairable on
[bluetooth]# agent on
```

Reboot
```
sudo reboot
```

```
bluetoothctl
```
Pair your device then trust it when you see Device <MAC> Connected: yes
```
trust DC:DC:E2:FF:04:A1
```

Auto pairing / trusting / no PIN
```
sudo apt-get install bluez-tools
```

```
sudo nano /etc/systemd/system/bt-agent.service
```

```
[Unit]
Description=Bluetooth Auth Agent
After=bluetooth.service
PartOf=bluetooth.service

[Service]
Type=simple
ExecStart=/usr/bin/bt-agent -c NoInputNoOutput

[Install]
WantedBy=bluetooth.target
```

## Setup ProjectM Audio Receiver
### Install dependencies
xautomation is currently used to persist preset shuffling in projectmWrapper.py as I have observed a bug causing it to hang
```
sudo apt install xautomation
```

### Download the ProjectM Audio Receiver sources
```
cd ~
git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git
```

Copy the projectMAR bash script to the ProjectMSDL installation directory
```
cp ~/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMSDL/
sudo chmod +x /opt/ProjectMSDL/projectMAR.sh
```

### Add Devices to ProjectM Audio Receiver startup script
You will need to edit the bash script to include the device name(s) that you are connecting.

Update /opt/ProjectMSDL/projectMAR.sh to include the devices for the following parameters:
```
# To see a list of devices run 'pactl list sources short'
SOURCE_MIC_DEVICE="<Full Device Name>"          # This is only for mic.  If none set to null
SOURCE_AUX_DEVICE="<Full Device Name>"          # This is only for aux.  If none set to null

# Sink profile for audio output
# To see a list of devices run 'pactl list sinks short'
SINK_DEVICEs=("<Full Device Name>" "<Full Device Name>")
```

### Test to ensure there are no issues
Run the following to execute ProjectM Audio Receiver:
```
/opt/ProjectMSDL/projectMAR.sh
```

If all is well close the window
```
alt+F4 (or 'sudo killall projectMSDL' from terminal)
```

## Create startup entry
For Debian Bookworm they are now using Wayland so you will need to edit the ~/.config/wayfire.ini file to include ProjectM Audio Receiver

Edit the wayfire.ini file to include the startup entry:
```
[autostart]
par = /opt/ProjectMSDL/projectMAR.sh
```

