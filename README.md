# Raspberry Pi 5 - ProjectM Audio Receiver

## ProjectMAR News:

### In this latest update:
<i><b>Note: </b>This update can break your existing configuration so take caution when updating</i>

- All new installer to alleviate the hastle of installing projectMAR and dependencies

- All new configurations which are now located in /opt/ProjectMAR/conf/.  The primary projectMAR.conf has been drastically reduced by moving the sources|sinks|cards|plugins to seperate configurations that are only necessary for manual audio configuration.  The primary purpose for this is to simplify the experience for users that prefer to run the audio control in automatic mode.  Additional example annotations have been added for manual audio configurations.

- Card profile management has been enhanced and also now works in automatic mode by providing some additional configurations:
  ```
  [automatic]
  # card_device_type defines the type of card added supporting (input|input-output|output)
  # card_device_modes defines the type of formats accepted
  card_device_type=input-output
  card_device_modes=analog-stereo,mono-fallback,stereo-fallback,hmdi-stereo
  ```

- Added support for multiple preset paths in projectMSDL.properties

### Recently there have been many improvements:

- Added an option to manage card profiles.  This is primarily for those using a DAC/ADC hat to ensure the input/output profile is loaded accordingly.

- Added Spotify service to the supported plugins list with instructions for users with Spotify premium.  Due to the streaming services popularity I went ahead and purchased a month so I could test premium Spotify with the Spotify Connect feature.  I ended up going with Spotifyd over Raspotify as I encountered allot of issues trying to get Raspotify to work seamlessly while also being picked up by the visualizer.

- Updated builds for libprojectM and projectMSDL.  There have been numerous improvements to libprojectM since the 4.0 release however I have been hesitant to update to it due to a performance impact.  I have decided the performance impact is worth it for the issues it fixes, <b>so you may have to remove some presets if they exhibit low fps</b>.  To alleviate the work I have a new option for hand selected presets!

- Hand selected presets are now available (Took me a while to go through the 10K batch)!  These presets and textures are hosted on a new repository with instructions on how to get them applied.

- Various improvements and some bug fixes.  Because some of the configuration settings have changed, please migrate with caution.  Furthermore I have updated to install instructions to avoid clutter in the user home directory and to also split up the projectMSDL and projectMAR installation directories

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

- Raspberry Pi 5 - 2GB, 4GB, or 8GB
- 5v/5A USB-C Power Supply
- SanDisk 32GB Extreme PRO microSD
- Case with active cooling (The following are my recommendations)
    - Hifiberry Steel case for RP5 w/active cooling and w/DAC+ ADC card for analog input/output
    - Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan
- HDMI Cable with Micro HDMI adapter or Micro HDMI to HDMI cable
- Input device of your choosing (You can always use built in Bluetooth; just know there is potential for interference with built in card)
    - USB Microphone
    - USB Line in/Aux

## Software Requirements:
- Raspberry Pi OS Bookworm:
  - Desktop with labwc (I have seen some sporadic issues when booting the desktop environment, however no issues were observed with ProjectMAR)
  - Desktop with Wayland Display
  - Desktop with X11
  - Lite

## Initial Raspberry Pi Setup
This step assumes you have already imaged your SD card.  If you need help getting Raspberry Pi OS setup refer to: [Install Raspberry Pi OS using Raspberry Pi Imager](https://www.raspberrypi.com/software/)

Make sure the OS is up-to-date
```
sudo apt update
sudo apt upgrade
```

## ProjectMAR Installation

<details>
<summary><b>Automated Installation</b></summary>

### Install projectM, frontend SDL, and projectMAR using the new setup script
```
curl -sSL https://raw.githubusercontent.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/refs/heads/dev/install.sh | sudo bash
```

Check to ensure your device is configured for PulseAudio by going to sudo raspi-config, then select Advanced Options - Audio Config - PulseAudio (Reboot if you made any changes)

</details>

<details>
<summary><b>Manual Installation</b></summary></br>

  Lets add a directory to store our builds so we dont clutter the home directory
  ```
  mkdir /tmp/Builds
  ```

  ### Building ProjectM and Dependencies
  It is advised to only use the releases tested here as they are version controlled to ensure a seamless experience.

  <details>
  <summary><b>Building libprojectM</b></summary>

  ### Install the build tools and dependencies
  Get the mandatory packages:
  ```
  sudo apt install build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git
  ```

  ### Download/extract/build libprojectM
  The current build this project uses is 4.0.0.  There is currently a bug in later releases that impact performance on the Raspberry Pi.
  ```
  cd /tmp/Builds
  wget https://github.com/projectM-visualizer/projectm/releases/download/v4.1.4/libprojectM-4.1.4.tar.gz
  tar xf libprojectM-4.1.4.tar.gz
  cd /tmp/Builds/libprojectM-4.1.4/
  mkdir build
  cd build
  cmake -DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local ..
  cmake --build . --parallel && sudo cmake --build . --target install
  ```

  </details>

  <details>
  <summary><b>Building libPoco</b></summary>

  ### Download/extract/build libPoco-dev
  Because the current repository contains a problematic version of libPoco-dev, we must build from source.

  Obtain a tested working build of libPoco-dev and build.  ***Note:** This is going to take some time to install*
  ```
  cd /tmp/Builds
  wget https://github.com/pocoproject/poco/archive/refs/tags/poco-1.12.5p2-release.tar.gz
  tar xf poco-1.12.5p2-release.tar.gz
  cd poco-poco-1.12.5p2-release/
  mkdir cmake-build
  cd cmake-build
  cmake ..
  cmake --build . --config Release
  sudo cmake --build . --target install
  ```

  You will have to move the libs for projectMSDL frontend to work
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

  ### Download/build frontend-sdl2

  ```
  cd /tmp/Builds
  git clone https://github.com/kholbrook1303/frontend-sdl2.git
  cd frontend-sdl2/
  git submodule init
  git submodule update
  mkdir cmake-build
  cmake -S . -B cmake-build -DCMAKE_BUILD_TYPE=Release
  cmake --build cmake-build --config Release
  cd cmake-build
  make
  ```

  Copy build application to standard directory (Make sure you replace $GROUP:$USER with the appropriate user and group)
  ```
  sudo mkdir /opt/ProjectMSDL
  sudo cp -r /tmp/Builds/frontend-sdl2/cmake-build/src/projectMSDL /opt/ProjectMSDL/
  sudo cp -r /tmp/Builds/frontend-sdl2/cmake-build/src/projectMSDL.properties /opt/ProjectMSDL/
  sudo chown $GROUP:$USER /opt/ProjectMSDL/ -R
  sudo chmod 777 -R /opt/ProjectMSDL
  ```
  
  ### Force the Open GL version

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
  <summary><b>Installing ProjectMAR</b></summary>

  ### Install the dependencies
  Install pulseaudio sound server
  ```
  sudo apt install pulseaudio
  ```

  Check to ensure your device is configured for PulseAudio by going to sudo raspi-config, then select Advanced Options - Audio Config - PulseAudio (Reboot if you made any changes)

  ### Download and setup ProjectM Audio Receiver from source
  Pull the sources from Github and copy files to installation directory (Make sure you replace $GROUP:$USER with the appropriate user and group)
  ```
  cd /tmp/Builds
  git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git
  sudo mkdir /opt/ProjectMAR
  sudo cp -r /tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMAR/
  sudo chown $GROUP:$USER /opt/ProjectMAR/ -R
  sudo chmod 777 -R /opt/ProjectMAR
  ```

  ### Setup Python virtual environment
  Install the virtual environment
  ```
  cd /opt/ProjectMAR/
  python3 -m venv env
  ```

  ### Get all Python dependencies
  Install all Python dependencies
  ```
  /opt/ProjectMAR/env/bin/python3 -m pip install -r requirements.txt
  ```

  ### Build additional python dependencies
  <i><b>Note: </b>This section is not necessary if you choose not to leverage this feature.  This feature is solely to avoid a bug in projectM that causes the preset to get stuck.</i>

  It has been observed that presets can persist (hang) despite the projectM.displayDuration setting in projectMSDL.properties.  Because of this we are going to install uinput to handle keyboard automation to goto the next preset.

  Build and install python-uinput
  ```
  wget https://github.com/pyinput/python-uinput/archive/refs/tags/1.0.1.tar.gz
  tar xf 1.0.1.tar.gz
  cd python-uinput-1.0.1/
  /opt/ProjectMAR/env/bin/python3 setup.py build
  /opt/ProjectMAR/env/bin/python3 setup.py install
  ```

  Add you user to a new uinput group for secure access (Make sure you replace $USER with the appropriate user)
  ```
  sudo addgroup uinput
  sudo usermod -a -G uinput $USER
  sudo chown :uinput /dev/uinput
  sudo chmod 660 /dev/uinput
  ```

  Create a new udev rule to allow access to the new group using the following command
  ```
  sudo nano /etc/udev/rules.d/99-uinput.rules
  ```

  Add the rule
  ```
  KERNEL=="uinput", MODE="0660", GROUP="uinput"
  ```

  Reload the new rule
  ```
  sudo udevadm control --reload-rules
  sudo systemctl restart udev
  ```

  Edit the modules to include an additional startup module
  ```
  sudo nano /etc/modules
  ```

  Add the uinput module at the end of the file
  ```
  uinput
  ```

  Reboot the system

  ## Environment Specific Startup Instructions
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
    Exec=/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py
    Type=Application
    ```
    </details>

    <details>
    <summary><b>RPI OS Lite Instructions</b></summary>
  
    ### Setup the auto start on boot

    Enable autologon if using the lite version of RPI OS

    Enable auto-logon.  Run the following command and then navigate to System Options -> Boot / Auto Logon -> Console Auto Logon
    ```
    sudo raspi-config
    ```

    ### Create a startup service
    Create a service by running
    ```
    sudo nano /etc/systemd/user/projectm.service
    ```

    ```
    [Unit]
    Description=ProjectMAR

    [Service]
    Type=simple
    ExecStart=/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py
    Restart=on-failure

    [Install]
    WantedBy=default.target
    ```

    Enable and start the service
    ```
    systemctl --user enable projectm
    systemctl --user start projectm
    ```
    </details>

  </details>

</details>

## Optional Features

<details>
<summary><b>Setup A2DP Bluetooth audio </b></summary>

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
Class = 0x41C

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
<summary><b>Setup AirPlay</b></summary>


### Setup and build Shairport Sync

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

cd /tmp/Builds
wget https://github.com/mikebrady/shairport-sync/archive/refs/tags/4.3.7.tar.gz
tar xf 4.3.7.tar.gz
cd /tmp/Builds/shairport-sync-4.3.7/
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
cd /tmp/Builds
wget https://github.com/mikebrady/nqptp/archive/refs/tags/1.2.4.tar.gz
tar xf 1.2.4.tar.gz
cd /tmp/Builds/nqptp-1.2.4
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

## Startup Instructions
Open projectMAR.conf and navigate to the 'audio_receiver' section.  Ensure that plugin_ctrl is set to 'True' and add an additional plugin with a unique name to plugins
```
plugin_ctrl=True
plugins=plugin1
```

Beneath the 'audio_receiver' section, add a new section using the unique plugin name you created, then add the necessary parameters replacing the 'USER' with your username
```
[plugin1]
name=Shairport-Sync
path=/usr/local/bin/shairport-sync
arguments=
```

</details>

<details>
<summary><b>Setup Plexamp</b> <i>(Requires PlexPass)</i></summary>

### Get PlexAmp and NodeJS

```
cd /tmp/Builds
wget https://plexamp.plex.tv/headless/Plexamp-Linux-headless-v4.11.5.tar.bz2
tar -xvjf Plexamp-Linux-headless-v4.11.5.tar.bz2
sudo cp /tmp/Builds/plexamp/ /opt/ -r
cd /opt/plexamp
sudo apt-get install -y ca-certificates curl gnupg && sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
NODE_MAJOR=20
echo deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt-get update && sudo apt-get install -y nodejs
```

### Setup your Plexamp token

Initialize Plexamp for the first time
```
node /opt/plexamp/js/index.js
```

Obtain your claim token.  In a seperate browser goto:
https://plex.tv/claim

Paste the claim code in the terminal window and proceed with naming your player

## Startup Instructions

Open projectMAR.conf and navigate to the 'audio_receiver' section.  Ensure that plugin_ctrl is set to 'True' and add an additional plugin with a unique name to plugins
```
plugin_ctrl=True
plugins=plugin1,plugin2
```

Beneath the 'audio_receiver' section, add a new section using the unique plugin name you created, then add the necessary parameters
```
[plugin2]
name=PlexAmp
path=/usr/bin/node
arguments=/opt/plexamp/js/index.js
```

## Instructions for casting
Once running goto PlexAmp on your mobile device and select the cast button.  In the menu of systems select the hostname of your Raspberry Pi to broadcast music.

## Instructions for using without casting
On a system with a web browser navigate to your Plexamp system
```
http://<RaspberryPi_IP>:32500
```

Login with your PlexPass credentials and you can now control PlexAmp music on your pi

</details>

<details>
<summary><b>Setup Spotify Connect</b> <i>(Requires Spotify Premium)</i></summary>

### Get Spotifyd

```
cd /tmp/Builds
wget https://github.com/Spotifyd/spotifyd/releases/download/v0.4.0/spotifyd-linux-aarch64-default.tar.gz
tar xzf spotifyd-linux-aarch64-default.tar.gz
chmod +x spotifyd
sudo chown root:root spotifyd
sudo mv spotifyd /usr/local/bin/spotifyd
```

### Advanced Configurations

Spotify should work out of the box with defaults but you can also fine tune your setup.  To do so first create a configuration file in /etc/
```
sudo nano /etc/spotifyd.conf
```

Goto the following site and you can see an example confirguration to copy and paste.  Any configurations you want to customize, just uncomment the parameter.

https://docs.spotifyd.rs/configuration/index.html

## Startup Instructions

Open projectMAR.conf and navigate to the 'audio_receiver' section.  Ensure that plugin_ctrl is set to 'True' and add an additional plugin with a unique name to plugins
```
plugin_ctrl=True
plugins=plugin1,plugin2,plugin3
```

Beneath the 'audio_receiver' section, add a new section using the unique plugin name you created, then add the necessary parameters
```
[plugin3]
name=Spotify
path=/usr/local/bin/spotifyd
arguments=--no-daemon --backend pulseaudio
```

## Instructions for casting
Once running goto Spotify on your mobile device and select the devices button.  In the menu of systems select the hostname of your Raspberry Pi to broadcast music.

</details>

## ProjectMAR Configuration

<details>
<summary><b>Setup ProjectM Presets and Textures</b></summary></br>
The preset files define the visualizations via pixel shaders and Milkdrop-style equations and parameters.  The projectM library does not ship with any presets or textures so you want to grab them and deploy them.  

There are many options available to you for presets and textures.  In the following I have outlined 3 options:
  <details>
  <summary><b>GitHub Repo - RPI5-ProjectM-Presets-Textures</b> <i>My hand selected presets and textures for the latest libprojectM release for the Raspberry Pi 5</i></summary>

  ### Download and move the presets and textures
  ```
  cd /tmp/Builds
  git clone https://github.com/kholbrook1303/RPI5-ProjectM-Presets-Textures.git
  cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/presets/ /opt/ProjectMSDL/ -R
  cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/textures/ /opt/ProjectMSDL/ -R
  ```

  </details>

  <details>
  <summary><b>GitHub Repo - projectM-presets-rpi5</b> <i>Presets and textures repository managed by mickabrig7, and benchmarked for the Raspberry Pi 5</i></summary>

  ### Download and move the presets and textures
  *Special thank you to [mickabrig7](https://github.com/mickabrig7/projectM-presets-rpi5) for benchmarking 11,233 presets to narrow down a package specially for the Raspberry Pi 5!*
  ```
  cd /tmp/Builds
  git clone https://github.com/mickabrig7/projectM-presets-rpi5.git
  cp /tmp/Builds/projectM-presets-rpi5/presets/ /opt/ProjectMSDL/ -R
  cp /tmp/Builds/projectM-presets-rpi5/textures/ /opt/ProjectMSDL/ -R
  ```

  Adjust /opt/ProjectMSDL/projectMSDL.properties to include the preset and texture directories
  ```
  projectM.presetPath = /opt/ProjectMSDL/presets
  projectM.texturePath = /opt/ProjectMSDL/textures
  ```

  </details>


  <details>
  <summary><b>Manual Method</b> <i>Resources to obtain community presets and textures</i></summary>

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

  </br></details>

</details>

<details>
<summary><b>ProjectMSDL Configuration</b></summary></br>
Adjust /opt/ProjectMSDL/projectMSDL.properties to suit the Raspberry Pi.  Change the following configurations to the below:

***Note:** I have performed testing of this in Desktop with the resolution set higher but with fullscreen exclusive set to 1280x720 however the performance did not improve.  Furthermore when exclusive mode is enabled but not fullscreen, you will get a cursor that can only be removed by hitting escape.  While this also sounds strange, only set the window size resolution.*

```
window.fullscreen = true

window.fullscreen.exclusiveMode = true

window.width = 1280
window.height = 720

projectM.presetPath = /opt/ProjectMSDL/presets
projectM.texturePath = /opt/ProjectMSDL/textures

## This setting is optional
projectM.displayDuration = 60

## This setting is optional (ProjectMAR has its own advanced shuffling that allows you to go back to previous)
projectM.shuffleEnabled = false

projectM.meshX = 64
projectM.meshY = 32

projectM.transitionDuration = 0

## These settings are optional (When enabled a preset transition will occur on a "hard cut")
projectM.hardCutsEnabled = true
projectM.hardCutDuration = 30
```

</details>

<details>
<summary><b>ProjectMAR Configuration</b></summary></br>
  By default, ProjectMAR is set to automatic (/opt/ProjectMAR/conf/projectMAR.conf).  This means that it will handle the audio devices automatically so you do not need to have advanced knowledge of your devices.

  If you prefer to define your devices and their feature sets, switch the audio_mode to manual and proceed with device configuration in the following configuration files:
  - audio_cards.conf
  - audio_sources.conf
  - audio_sinks.conf
  - audio_plugins.conf
</details>

<details>
<summary><b>PulseAudio Configuration</b></summary></br>
To enable higher sample rates in Pulseaudio (Specifically for various DACs) ensure you add the following to Pulseaudio daemon config (/etc/pulse/daemon.conf)
```
resample-method = soxr-vhq
avoid-resampling = true
default-sample-format = s24le
default-sample-rate = 44100
alternate-sample-rate = 48000
```

Either restart or you can run 
```
systemctl --user restart pulseaudio.socket
systemctl --user restart pulseaudio.service

```
</details>