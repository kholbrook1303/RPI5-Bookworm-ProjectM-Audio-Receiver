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
- Case with active cooling (The following are my recommendations in order of preference)
    - Argon ONE V3 Case for Raspberry Pi 5 w/ Argon BLSTR DAC with Ground Loop Isolator (This is going to get costly and is not necessary for basic audio)
    - Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan
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
It is advised to follow the most recent build steps from the source.  Additionally please only use the releases tested here:
- https://github.com/projectM-visualizer/projectm/wiki/Building-libprojectM*
- https://github.com/projectM-visualizer/frontend-sdl2*

<details>
<summary><b>Building libprojectM</b></summary>

### Install the build tools and dependencies
Get the mandatory packages:
```
sudo apt install build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git libsdl2-dev
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

Adjust /opt/ProjectMSDL/projectMSDL.properties to suit the Raspberry Pi.  Change the following configurations to the below:
```
window.fullscreen = true
projectM.meshX = 64
projectM.meshY = 32
```

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

<details>
<summary><b>Install dependencies</b></summary>
<br/>

xautomation is currently used to persist preset shuffling in projectmWrapper.py as I have observed a bug causing it to hang.  Additionally PulseAudio may need to be installed (Currently audio control is managed to PulseAudio.  There are future plans make this optional)

```
sudo apt install xautomation pulseaudio
```

</details>

<details>
<summary><b>Set OpenGL version globally</b></summary>
</br>

First open the '/etc/environment' file to set environment variables
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
<summary><b>Download the ProjectM Audio Receiver sources</b></summary>
</br>

Pull the sources from Github
```
cd ~
git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git
```

Copy the projectMAR bash script to the ProjectMSDL installation directory
```
cp -r ~/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMSDL/
```
</details>

<details>
<summary><b>Setup Python venv and dependencies</b></summary>
</br>

Install the virtual environment
```
cd /opt/ProjectMSDL/
python3 -m venv env
```

Install all Python dependencies
```
/opt/ProjectMSDL/env/bin/python3 -m pip install -r requirements.txt
```
</details>

<details>
<summary><b>Configure ProjectM Audio Receiver</b></summary>
</br>

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

#### RPI OS Desktop with Wayland Display Instructions:
For Debian Bookworm they are now using Wayland so you will need to edit the ~/.config/wayfire.ini file to include ProjectM Audio Receiver

if using the Desktop version, edit the wayfire.ini file to include the startup entry:
```
[autostart]
par = /opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
```

#### RPI Desktop OS with X11 Display and RPI Lite OS Instructions:

Create a service by running
```
sudo nano /etc/systemd/user/projectm.service
```

Create a user service to start the application.  Add the following contents, then press 'ctrl+x' to exit and press 'y' to accept changes
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

#### RPI Lite OS Instructions:
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

## Optional Components

<details>
<summary><b>Setup A2DP Bluetooth audio receiver </b></summary>
</br>

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

### Enable and start the Bluetooth service
```
sudo systemctl enable bt-agent
sudo systemctl start bt-agent
```
</details>

<details>
<summary><b>Setup AirPlay receiver</b></summary>
</br>
Setup and build Shairport Sync
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

#### RPI OS Desktop with Wayland Display Instructions:
Edit the wayfire.ini file and add shairport-sync as an autostart entry:
```
shairport = /usr/local/bin/shairport-sync
```

#### RPI Desktop OS with X11 Display or RPI Lite OS Instructions:
If using the lite version, create a user service to start the application

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
</details>