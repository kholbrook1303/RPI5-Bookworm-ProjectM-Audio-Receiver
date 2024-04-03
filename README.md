# Raspberry Pi 5 - ProjectM Audio Receiver

![ProjectMAR Device](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/device.png)
![ProjectMAR Preview 1](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview1.png)
![ProjectMAR Preview 2](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview2.png)
![ProjectMAR Preview 3](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview3.png)
![ProjectMAR Preview 4](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview4.png)

## What is this?
The ProjectM Audio Receiver concept will enable your Raspberry Pi to project visualizations through HDMI that react to audio provided by an input device of your choosing.  

## But why?
The background history behind this was to have visualizations on the television that reacted to a turntable that was playing in the same room.  Growing up I used to enjoy using Winamp with the Milkdrop visualizations build by Ryan Geiss.  These visualizations were proprietary on Windows but have since been ported to other OSs with the help of the ProjectM team.  Since the release of the Raspberry Pi 5, there is now adequate processing power to run allot of these visualizations.

## Hardware Requirements:
```
Raspberry Pi 5 with an SD card and power supply
Case with cooling fan (I used the Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan)
HDMI Cable
Input device of your choosing.  The following are supported:
 - USB Microphone
 - USB to Line in
 - Bluetooth (No harware is needed unless you dont use the built in bluetooth chip)
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
KillSignal=SIGUSR1

[Install]
WantedBy=bluetooth.target
```

## Setup ProjectM Audio Receiver
### Install dependencies
xautomation is currently used to persist preset shuffling in projectmWrapper.py as I have observed a bug causing it to hang
```
sudo apt install xautomation
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
mkdir /opt/ProjectMSDL/
cp ~/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMSDL/
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
For Debian Bookworm they are now using Wayland so you will need to edit the ~/.config/wayfire.ini file to include ProjectM Audio Receiver

Edit the wayfire.ini file to include the startup entry:
```
[autostart]
par = /opt/ProjectMSDL/env/bin/python3 /opt/ProjectMSDL/projectMAR.py
```

