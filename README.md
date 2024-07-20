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

## Hardware Requirements:

- Raspberry Pi 5 - 8GB
- 5v/5A USB-C Power Supply
- SanDisk 32GB Extreme PRO microSD
- Case with active cooling (The following are my recommendations)
    - Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan
    - Argon ONE V3 Case for Raspberry Pi 5 w/ Argon BLSTR DAC with Ground Loop Isolator
- HDMI Cable with Micro HDMI adapter or Micro HDMI to HDMI cable
- Input device of your choosing (You can always use built in Bluetooth; just know there is potential for interference with built in card)
    - USB Microphone
    - USB Line in/Aux

## Software Requirements:
- Raspberry Pi OS Bookworm:
  - Desktop with Wayland Display
  - Desktop with X11
  - Lite

## Initial Setup
This step assumes you have already imaged your SD card.  If you need help getting Raspberry Pi OS setup refer to: [Install Raspberry Pi OS using Raspberry Pi Imager](https://www.raspberrypi.com/software/)

Make sure the OS is up-to-date
```
sudo apt update
sudo apt upgrade
```

## Building ProjectM and Dependencies
It is advised to only use the releases tested here as they are version controlled to ensure a seamless experience.

<details>
<summary><b>Building libprojectM</b></summary>

### Install the build tools and dependencies
Get the mandatory packages:
```
sudo apt install build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git
```

### Download and extract the source package
The current build this project uses is 4.0.0.  There is currently a bug in later releases that impact performance on the Raspberry Pi.
```
cd ~
wget https://github.com/projectM-visualizer/projectm/archive/refs/tags/v4.0.0.tar.gz
tar xf v4.0.0.tar.gz
cd ~/projectm-4.0.0/
mkdir build
cd build
cmake -DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local ..
cmake --build . --parallel && sudo cmake --build . --target install
```

</details>

<details>
<summary><b>Building libPico</b></summary>

### Download, build and install libPico-dev
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

</details>

<details>
<summary><b>Building frontend-sdl2</b></summary>

### Install the dependencies
Get the mandatory packages:
```
sudo apt install libsdl2-dev libfreetype-dev cmake
```

### Download the SDL2 Frontend sources
```
cd ~
git clone https://github.com/kholbrook1303/frontend-sdl2.git
```

### Build and install SDL2 Frontend

```
cd frontend-sdl2/
git submodule init
git submodule update
mkdir cmake-build
cmake -S . -B cmake-build -DCMAKE_BUILD_TYPE=Release
cmake --build cmake-build --config Release
cd cmake-build
make
```

Copy build application to standard directory
```
sudo mkdir /opt/ProjectMSDL
sudo cp -r ~/frontend-sdl2/cmake-build/src/* /opt/ProjectMSDL/
sudo chmod 777 -R /opt/ProjectMSDL
```

Adjust /opt/ProjectMSDL/projectMSDL.properties to suit the Raspberry Pi.  Change the following configurations to the below:
```
window.fullscreen = true
projectM.meshX = 64
projectM.meshY = 32
```

Open the '/etc/environment' file to set environment variables
```
sudo nano /etc/environment
```

Add the following entry
```
MESA_GL_VERSION_OVERRIDE=4.5
```

Reboot

</details>

<details>
<summary><b>ProjectM Presets and Textures</b></summary>

## Setup textures and presets
The preset files define the visualizations via pixel shaders and Milkdrop-style equations and parameters.  The projectM library does not ship with any presets or textures so you want to grab them and deploy them:

***Note:** I am currently hand selecting presets that are not only appealing and mostly reactive, but will play seamlessly on the Raspberry Pi.  This will available in the coming weeks.*

### Presets and Textures for the Raspberry Pi 5:
*Special thank you to [mickabrig7](https://github.com/mickabrig7/projectM-presets-rpi5) for benchmarking 11,233 presets to narrow down a package specially for the Raspberry Pi 5!*

Textures / Presets - https://github.com/mickabrig7/projectM-presets-rpi5.git

### General Presets and Textures:
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

</details>

## Setup ProjectM Audio Receiver
If you prefer to manage audio devices yourself, there is no need for the ProjectM Audio Receiver portion of this guide.  
The ProjectM Audio Receiver manages your default sources/sinks and will route audio through loopback when necessary.  

<details>
<summary><b>Setup dependencies</b></summary>
<br/>

xautomation is currently used to persist preset shuffling in projectmWrapper.py as I have observed a bug causing it to hang.

```
sudo apt install xautomation pulseaudio
```

Check to ensure your device is configured for PulseAudio by going to sudo raspi-config, then select Advanced Options - Audio Config - Pipewire (Reboot if you made any changes)

</details>

<details>
<summary><b>Download and setup ProjectM Audio Receiver from source</b></summary>

### Obtain the latest source
Pull the sources from Github
```
cd ~
git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git
```

Copy the projectMAR bash script to the ProjectMSDL installation directory
```
cp -r ~/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMSDL/
```

### Setup Python virtual environment
Install the virtual environment
```
cd /opt/ProjectMSDL/
python3 -m venv env
```

### Get all Python dependencies
Install all Python dependencies
```
/opt/ProjectMSDL/env/bin/python3 -m pip install -r requirements.txt
```

### Configure ProjectM Audio Receiver
Select the audio receiver mode.  Automatic will handle connected devices without any user configuration
Manual will allow you to be more granular with your devices (As well as switch between mic and aux devices)
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

## Environment Specific Instructions

  <details>
  <summary><b>RPI OS Desktop Instructions</b></summary>
  
  ### Setup the auto start on boot

  Add ProjectMAR to autostart
  ```
  sudo nano /etc/xdg/autostart/projectm.desktop
  ```

  Add the following configuration
  ```
  [Desktop Entry]
  Name=ProjectMAR
  Exec=/opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
  Type=Application
  ```
  </details>

  <details>
  <summary><b>RPI Lite OS Instructions</b></summary>
 
  ### Setup the auto start on boot

  Enable autologon if using the lite version of RPI OS

  Enable auto-logon.  Run the following command and then navigate to System Options -> Boot / Auto Logon -> Console Auto Logon
  ```
  sudo raspi-config
  ```

  Enfore a resolution for Raspberry Pi OS Lite.  Edit the boot cmdline.txt.
  ```
  sudo nano /boot/firmware/cmdline.txt
  ```

  Add the device, resolution, and refresh rate to the end of the cmdline.txt
  ```
  video=HDMI-A-1:1280x720M@60 video=HDMI-A-2:1280x720M@60
  ```
  </details>

</details>

## Optional Features

<details>
<summary><b>Setup A2DP Bluetooth audio receiver </b></summary>

### Get Bluetooth dependencies

Acquire all the necessary dependecies
```
sudo apt-get install pulseaudio-module-bluetooth
```

### Configure Bluetooth functionality
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
bluetoothctl power on
bluetoothctl discoverable on
bluetoothctl pairable on
bluetoothctl agent on
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

### Configure Bluetooth agent service
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

Enable and start the Bluetooth service
```
sudo systemctl enable bt-agent
sudo systemctl start bt-agent
```
</details>

<details>
<summary><b>Setup AirPlay receiver</b></summary>
Setup and build Shairport Sync

* It is advised to follow the most recent build steps from https://github.com/mikebrady/shairport-sync/blob/master/BUILD.md

### Get Shairport-Sync dependencies
Install required dependencies
```
sudo apt install --no-install-recommends build-essential git autoconf automake libtool libpulse-dev \
    libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev libssl-dev libsoxr-dev \
    libplist-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev uuid-dev libgcrypt-dev xxd
```

### Obtain the latest source
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
* It is advised to follow the most recent build steps from https://github.com/mikebrady/nqptp

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

### Setup the auto start on boot

Add Shairport to autostart
```
sudo nano /etc/xdg/autostart/shairport.desktop
```

Add the following configuration
```
[Desktop Entry]
Name=Shairport
Exec=/usr/local/bin/shairport-sync
Type=Application
```
</details>

<details>
<summary><b>Setup Plexamp Receiver</b></summary>

### Get PlexAmp and NodeJS

```
wget https://plexamp.plex.tv/headless/Plexamp-Linux-headless-v4.11.0.tar.bz2
tar -xvjf Plexamp-Linux-headless-v4.11.0.tar.bz2
cd plexamp
sudo apt-get install -y ca-certificates curl gnupg && sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
NODE_MAJOR=20
echo deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt-get update && sudo apt-get install -y nodejs
```

### Setup your Plexamp token

Initialize Plexamp for the first time
```
node ~/plexamp/js/index.js
```

Obtain your claim token.  In a seperate browser goto:
https://plex.tv/claim

Paste the claim code in the terminal window and proceed with naming your player

### Setup Plexamp

Launch Plexamp
```
node ~/plexamp/js/index.js
```

On a system with a web browser navigate to your Plexamp system
```
http://<RaspberryPi_IP>:32500
```

Login with your PlexPass credentials

### Setup the auto start on boot

Add Plexamp to autostart
```
sudo nano /etc/xdg/autostart/plexamp.desktop
```

Add the following configuration
```
[Desktop Entry]
Name=Plexamp
Exec=/usr/bin/node /home/<USERNAME>/plexamp/js/index.js
Type=Application
```

</details>