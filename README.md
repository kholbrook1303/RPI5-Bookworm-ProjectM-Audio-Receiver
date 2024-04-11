# Raspberry Pi 5 - ProjectM Audio Receiver

![ProjectMAR Device](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/device.png)

## What is this?
The ProjectM Audio Receiver will enable your Raspberry Pi to project visualizations through HDMI that react to audio provided by an input device of your choosing.  

## But why?
Growing up I used to enjoy using Winamp with the Milkdrop visualizations built by Ryan Geiss.  These visualizations were proprietary on Windows (DirectX), but have since been ported to other operating systems with the help of the [ProjectM](https://github.com/projectM-visualizer/projectm/tree/master) team.  Since the release of the Raspberry Pi 5, there is now adequate processing power to run allot of these visualizations.

Originally the intention was to add a video signal to the Phono input of my Marantz receiver that would react to the rooms surrounding audio.  As it progressed, I figure why not also control the sources/sinks of the Raspberry pi to support various audio input devices (Line in, Mic, Bluetooth, etc...).

## Screenshots
![ProjectMAR Screenshot 1](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview1.png)
![ProjectMAR Screenshot 2](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview2.png)
![ProjectMAR Screenshot 3](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview3.png)
![ProjectMAR Screenshot 4](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview4.png)

## Video Preview
[![ProjectMAR Video 1](https://img.youtube.com/vi/8kj53j3EDec/0.jpg)](https://www.youtube.com/watch?v=8kj53j3EDec)

# Index
**Requirements:**
- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)

**Prepare the Raspberry Pi:**
- [Initial Setup](#initial-setup)

**Build the ProjectM dependencies:**
- [Building libprojectM](#building-libprojectm)
- [Building libPico-dev](#building-libpico-dev)
- [Building ProjectM SDL2 Frontend](#building-projectm-sdl2-frontend)
- [Setup textures and presets](#setup-textures-and-presets)

**Setup ProjectM Audio Receiver:**
- [Setup ProjectM Audio Receiver](#setup-projectm-audio-receiver)
- [Create startup entry](#create-startup-entry)

**Add optional components:**
- [Setup A2DP bluetooth audio receiver](#setup-a2dp-bluetooth-audio-receiver) (Optional)
- [Setup AirPlay audio receiver](#setup-airplay-receiver) (Optional)

## Hardware Requirements:

- Raspberry Pi 5 - 8GB
- 5v/5A USB-C Power Supply
- SanDisk 32GB Extreme PRO microSD
- Case with active cooling (The following are my recommendations in order of preference)
    - Argon ONE V3 Case for Raspberry Pi 5 w/ Argon BLSTR DAC with Ground Loop Isolator (This is going to get costly and is not necessary for basic audio)
    - Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan
- HDMI Cable with Micro HDMI adapter or Micro HDMI to HDMI cable
- Input device of your choosing (You can always use built in Bluetooth; just know there is potential for interference with built in card)
    - USB Microphone
    - USB Line in/Aux

## Software Requirements:
```
Raspberry Pi OS Bookworm (Desktop Mode)
```
***Note:** For reasons unknown (Possibly even SD Card performance), Lite is worse in performance than desktop and requires auto login with autostart mechanism.  Further testing is required to complete this.*

## Initial Setup
This step assumes you have already imaged your SD card.  If you need help getting Raspberry Pi OS setup refer to: [Install Raspberry Pi OS using Raspberry Pi Imager](https://www.raspberrypi.com/software/)

Make sure the OS is up-to-date
```
sudo apt update
sudo apt upgrade
```

## Building libprojectM 
* It is advised to follow the most recent build steps from https://github.com/projectM-visualizer/projectm/wiki/Building-libprojectM*

### Install the build tools and dependencies
Get the mandatory packages:
```
sudo apt install build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git libsdl2-dev
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

Obtain a tested working build of libPico-dev and build.  ***Note:** This is going to take some time to install*
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
* It is advised to follow the most recent build steps from https://github.com/projectM-visualizer/frontend-sdl2*

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
sudo cp -r ~/frontend-sdl2/build/src/* /opt/ProjectMSDL/
sudo chmod 777 -R /opt/ProjectMSDL
```

Adjust /opt/ProjectMSDL/projectMSDL.properties to suit the Raspberry Pi.  Change the following configuratios to the below:
```
window.fullscreen = true
projectM.meshX = 64
projectM.meshY = 32
```

## Setup textures and presets
The preset files define the visualizations via pixel shaders and Milkdrop-style equations and parameters.

The projectM library does not ship with any presets or textures so you want to grab them and deploy them:
***Note:** I am currently hand selecting presets that are not only appealing and mostly reactive, but will play seamlessly on the Raspberry Pi.  This will available in the coming weeks.*

Textures:
- [Base Milkdrop texture pack](https://github.com/projectM-visualizer/presets-milkdrop-texture-pack) - Recommended for
  use with _any_ preset pack!

Presets:
- [Cream of the Crop Pack](https://github.com/projectM-visualizer/presets-cream-of-the-crop) - A collection of about 10K
  presets compiled by Jason Fletcher. Currently, projectM's default preset pack.
- [Classic projectM Presets](https://github.com/projectM-visualizer/presets-projectm-classic) - A bit over 4K presets
  shipped with previous versions of projectM.
- [Milkdrop 2 Presets](https://github.com/projectM-visualizer/presets-milkdrop-original) - The original preset
  collection shipped with Milkdrop and Winamp.
- [En D Presets](https://github.com/projectM-visualizer/presets-en-d) - About 50 presets created by "En D".


## Setup ProjectM Audio Receiver
### Install dependencies
xautomation is currently used to persist preset shuffling in projectmWrapper.py as I have observed a bug causing it to hang

Additionally PulseAudio may need to be installed (Currently audio control is managed to PulseAudio.  There are future plans make this optional)
```
sudo apt install xautomation pulseaudio
```

### Set OpenGL version globally.
First open the '/etc/environment' file to set environment variables
```
sudo nano /etc/environment
```

Add the following entry
```
MESA_GL_VERSION_OVERRIDE=4.5
```

Reboot

### Download the ProjectM Audio Receiver sources
```
cd ~
git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git
```

Copy the projectMAR bash script to the ProjectMSDL installation directory
```
cp -r ~/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMSDL/
```

### Setup python venv
```
cd /opt/ProjectMSDL/
python3 -m venv env
```

### Install all Python dependencies
```
/opt/ProjectMSDL/env/bin/python3 -m pip install -r requirements.txt
```

### Setup the ProjectM Audio Receiver configuration
Select the audio receiver mode.  Automatic will handle connected devices without any user configuration
Manual will allow you to be more granular with your devices
```
ar_mode=manual
```

if using automatic mode, ensure you have specified the appropriate audio mode.
if you want the input audio routed to the output device, select aux, otherwise to only listen to environmental sound use mic mode.
An example of mic mode would be a receiver playing a phono input while playing video from the pi
```
audio_mode=aux
```

If using manual mode, update /opt/ProjectMSDL/projectMAR.conf to include the input/output devices.
To get the devices, connect them and run 'pactl list sources/sinks short' and take note of the device name
```
mic_devices=
aux_devices=
sink_devices=
```

### Test to ensure there are no issues
Run the following to execute ProjectM Audio Receiver:
```
/opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
```

If all is well close ProjectMSDL
```
alt+F4 (or 'sudo killall projectMSDL' from terminal)
```

## Create startup entry

### RPI OS Desktop Instructions
For Debian Bookworm they are now using Wayland so you will need to edit the ~/.config/wayfire.ini file to include ProjectM Audio Receiver

if using the Desktop version, edit the wayfire.ini file to include the startup entry:
```
[autostart]
par = /opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
```

### RPI OS Lite Instructions
If using the headless version, create a user service to start the application and enable autologon

Enable auto-logon.  Run the following command and then navigate to System Options -> Boot / Auto Logon -> Console Auto Logon
```
sudo raspi-config
```

Create a service by running
```
sudo nano /etc/systemd/user/projectm.service
```

Add the following contents, then press 'ctrl+x' to exit and press 'y' to accept changes
```
[Unit]
Description=ProjectMAR

[Service]
Type=simple
ExecStart=/opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
Restart=on-failure

[Install]
WantedBy=default.target
```

Enable the service
```
systemctl --user enable projectm
```

## Setup A2DP bluetooth audio receiver (Optional)
Acquire all the necessary dependecies
```
sudo apt-get install pulseaudio-module-bluetooth
```

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
KillSignal=SIGUSR1

[Install]
WantedBy=bluetooth.target
```

### Enable and start the bluetooth service
```
sudo systemctl enable bt-agent
sudo systemctl start bt-agent
```

## Setup AirPlay receiver (Optional)

### Setup and build Shairport Sync
* It is advised to follow the most recent build steps from https://github.com/mikebrady/shairport-sync/blob/master/BUILD.md*

Install required dependencies
```
sudo apt install --no-install-recommends build-essential git autoconf automake libtool libpulse-dev \
    libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev libssl-dev libsoxr-dev \
    libplist-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev uuid-dev libgcrypt-dev xxd
```

Clone and build shairport-sync
```
cd ~
git clone https://github.com/mikebrady/shairport-sync.git
cd shairport-sync
autoreconf -fi
./configure --sysconfdir=/etc --with-alsa \
    --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2 --with-pa
make
sudo make install
```

### Setup and build NQPTP
* It is advised to follow the most recent build steps from https://github.com/mikebrady/nqptp*

Clone and build nqptp
```
cd ~
git clone https://github.com/mikebrady/nqptp.git
cd nqptp
autoreconf -fi
./configure --with-systemd-startup
make
sudo make install
```

### Enable Services
```
sudo systemctl enable nqptp
sudo systemctl start nqptp
```

### Add a startup entry to run shairport-sync as a daemon

### RPI OS Desktop Instructions
Edit the wayfire.ini file and add shairport-sync as an autostart entry:
```
shairport = /usr/local/bin/shairport-sync
```

### RPI OS Lite Instructions
If using the headless version, create a user service to start the application

Create a service by running
```
sudo nano /etc/systemd/user/shairport.service
```

Add the following contents, then press 'ctrl+x' to exit and press 'y' to accept changes
```
[Unit]
Description=Shairport-Sync

[Service]
Type=simple
ExecStart=/usr/local/bin/shairport-sync
Restart=on-failure
StandardOutput=file:%h/log_file

[Install]
WantedBy=default.target
```

Enable the service
```
systemctl --user enable shairport
systemctl --user start shairport
```