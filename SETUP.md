# ProjectM Audio Receiver Installation Guide

## Initial Raspberry Pi Setup
This step assumes you have already imaged your SD card.  If you need help getting Raspberry Pi OS setup refer to: [Install Raspberry Pi OS using Raspberry Pi Imager](https://www.raspberrypi.com/software/)

Make sure the OS is up-to-date before proceeding!
```
sudo apt update
sudo apt upgrade -y
```

<details>
<summary><b>Automated Installation</b></summary>

### Install projectM and projectMAR using the new setup script

ProjectMAR installer is comprised of 2 optional installation modes:
- minimal: This will install everything but configure nothing.  This is a more advanced approach.
- optimal: This will set all of the projectMSDL configurations accordingly as well as set you resolution for ProjectMAR.  This is for users that just want it to function out-of-box.

ProjectMAR installer also supports the following optional plugins:
- a2dp: Bluetooth audio
- shairport-sync: Airplay casting support
- plexamp: PlexAmp casting support and web UI for library control (Requires Plex Pass)
- spotifyd: Spotify Connect (Requires premium subscription)

See below for usage instructions and examples.

#### Installer Usage:
```
Usage: install.sh [-m <value>] [-p <value>]
- a     Instructs the installer to setup an autostart entry for projectMAR (Default: false)
- m     Specifies the mode to install.
        The following modes are supported:
        - minimal           Base installtion for ProjectMAR)
        - optimized         Installtion with optimized configuration for ProjectMAR)
- p     Specifies the plugins you want installed (comma seperated list)
        The following plugins are supported:
        - a2dp              Bluetooth audio
        - shairport-sync    Airplay
        - spotifyd          Spotify Connect (Premium Subscription Required)
        - plexamp           Plexamp (Plex Pass Subscription Required)
```

#### Minimal Installation
```
curl -sSL https://raw.githubusercontent.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/main/bin/install.sh | sudo bash -s -- -m minimal
```

#### Optimized Installation with Startup
```
curl -sSL https://raw.githubusercontent.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/main/bin/install.sh | sudo bash -s -- -m optimized -a
```

#### Optimized Installation with Startup and plugins
```
curl -sSL https://raw.githubusercontent.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/main/bin/install.sh | sudo bash -s -- -m optimized -a -p a2dp,shairport-sync,spotifyd,plexamp
```

#### Uninstall
```
curl -sSL https://raw.githubusercontent.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/main/bin/install.sh | sudo bash -s -- -m uninstall
```

<i><b>Note:</b> Once the script has completed the system will be rebooted.  
If you enabled autostart on the installer the system should come up ready to go, otherwise
- Desktop OS: Run the projectMAR.sh shortcut on the desktop or run '/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py' to execute projectMAR.  
- Lite OS: Run '/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py' to execute projectMAR</i>
</details>

<details>
<summary><b>Manual Installation</b></summary></br>

Lets add a directory to store our builds so we dont clutter the home directory
```
mkdir -p /tmp/Builds
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
<summary><b>Installing ProjectMAR</b></summary>

### Install the dependencies
Install ProjectMAR dependencies
```
sudo apt install pulseaudio python3-dev gcc vlc
```

Ensure that your account has permissions to input
```
sudo usermod -aG input $USER
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

### Force the Open GL version

Open the '/etc/environment' file to set environment variables
```
sudo nano /etc/environment
```

Add the following entry
```
MESA_GL_VERSION_OVERRIDE=4.5
```

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


<details>
<summary><b>Setup ProjectM Presets and Textures</b></summary></br>

***Note:** If you ran the automated installation you already have my presets applied.  Proceed if you would like to add or change anything.*

The preset files define the visualizations via pixel shaders and Milkdrop-style equations and parameters.  The projectM library does not ship with any presets or textures so you want to grab them and deploy them.

There are many options available to you for presets and textures.  In the following I have outlined 3 options:
<details>
<summary><b>GitHub Repo - RPI5-ProjectM-Presets-Textures</b> <i>My hand selected presets and textures for the latest libprojectM release for the Raspberry Pi 5</i></summary>

### Download and move the presets and textures
```
mkdir -p /tmp/Builds
cd /tmp/Builds
git clone https://github.com/kholbrook1303/RPI5-ProjectM-Presets-Textures.git
cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/presets/ /opt/ProjectMAR/ -R
cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/textures/ /opt/ProjectMAR/ -R
```

</details>

<details>
<summary><b>GitHub Repo - projectM-presets-rpi5</b> <i>Presets and textures repository managed by mickabrig7, and benchmarked for the Raspberry Pi 5</i></summary>

### Download and move the presets and textures
*Special thank you to [mickabrig7](https://github.com/mickabrig7/projectM-presets-rpi5) for benchmarking 11,233 presets to narrow down a package specially for the Raspberry Pi 5!*
```
mkdir -p /tmp/Builds
cd /tmp/Builds
git clone https://github.com/mickabrig7/projectM-presets-rpi5.git
cp /tmp/Builds/projectM-presets-rpi5/presets/ /opt/ProjectMAR/ -R
cp /tmp/Builds/projectM-presets-rpi5/textures/ /opt/ProjectMAR/ -R
```

Adjust /opt/ProjectMAR/conf/projectMAR.conf to include the preset and texture directories
```
projectM.presetPath = /opt/ProjectMAR/presets
projectM.texturePath = /opt/ProjectMAR/textures
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

</details>

</details>

## Configuration

<details>
<summary><b>ProjectMAR Configuration</b></summary>

### Core Configuration
By default, ProjectMAR is set to automatic (/opt/ProjectMAR/conf/projectMAR.conf).  This means that it will handle the audio devices automatically so you do not need to have advanced knowledge of your devices.

If you prefer to define your devices and their feature sets, switch the audio_mode to manual and proceed with device configuration in the following configuration files:
- audio_cards.conf
- audio_sources.conf
- audio_sinks.conf

Plugins are installed if selected by the installer and is also covered in the optional features section, otherwise your free to define plugins in /conf/audio_plugins.conf.  This simply requires an application path and any command line arguments the application requires.

### projectM SDL Configuration
***Note:** If you ran the automated installation you already have the appropriate settings applied.  Only proceed if you would like to apply additional configurations.*


Adjust /opt/ProjectMAR/projectMAR.conf to suit the Raspberry Pi.  Change the following configurations to the below:
```
window.fullscreen = true

# If using a Raspberry Pi 4, ensure this is set to no more than 720x480 and the projectM.fps is set to 30
window.width = 1280
window.height = 720

projectM.presetPath = /opt/ProjectMAR/presets
projectM.texturePath = /opt/ProjectMAR/textures

## This setting is optional
projectM.displayDuration = 60

## This setting is optional
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

Reboot
```
sudo reboot
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
mkdir -p /tmp/Builds
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
mkdir -p /tmp/Builds
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
Open projectMAR.conf and navigate to the 'general' section.  Ensure that plugin_ctrl is set to 'True'.
```
plugin_ctrl=True
```

Open /conf/audio_plugins.conf add an additional plugins with a unique name to audio_plugins
```
audio_plugins=plugin1
```

Beneath the 'general' section in /conf/audio_plugins.conf, add a new section using the unique plugin name you created, then add the necessary parameters
```
[plugin1]
name=Shairport-Sync
path=/usr/local/bin/shairport-sync
arguments=
restore=true
```

</details>

<details>
<summary><b>Setup Plexamp</b> <i>(Requires PlexPass)</i></summary>

### Get PlexAmp and NodeJS

```
mkdir -p /tmp/Builds
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

Open projectMAR.conf and navigate to the 'general' section.  Ensure that plugin_ctrl is set to 'True'.
```
plugin_ctrl=True
```

Open /conf/audio_plugins.conf add an additional plugins with a unique name to audio_plugins
```
audio_plugins=plugin2
```

Beneath the 'general' section in /conf/audio_plugins.conf, add a new section using the unique plugin name you created, then add the necessary parameters
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
mkdir -p /tmp/Builds
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

Open projectMAR.conf and navigate to the 'general' section.  Ensure that plugin_ctrl is set to 'True'.
```
plugin_ctrl=True
```

Open /conf/audio_plugins.conf add an additional plugins with a unique name to audio_plugins
```
audio_plugins=plugin3
```

Beneath the 'general' section in /conf/audio_plugins.conf, add a new section using the unique plugin name you created, then add the necessary parameters
```
[plugin3]
name=Spotify
path=/usr/local/bin/spotifyd
arguments=--no-daemon --backend pulseaudio
```

## Instructions for casting
Once running goto Spotify on your mobile device and select the devices button.  In the menu of systems select the hostname of your Raspberry Pi to broadcast music.

</details>

##  Hyperion Ambient Lighting
Hyperion can be installed allongside ProjectMAR to control LED controllers to extend the visualizations beyond the screen (via USB Capture Card or Screen Capture).

### Caveats
Screen capture only works on a Desktop environment running X11.  Because of this you have to go into `raspi-config` -> `Advanced Options` -> `Wayland` and choose `x11`.

USB capture cards in my experience have only worked when setting USB to maximum voltage.  You can do that by editing the `/boot/firmware/config.txt` with a line at the end for `usb_max_current_enable=1`.  Reboot when done.

Capture picture decimation should be set at minimum of 4, and the refresh rate should not exceed 30 to ensure you dont overload the system.

### Installation
First run the Hyperion installer to obtain the latest version:
```
curl -sSL https://releases.hyperion-project.org/install | bash
```

Once done you will need to disable the system service if you want to enable screen :
```
sudo systemctl disable hyperion@.service
```

Now create an XDG autostart entry so that when hyperion runs it inherits the user environment allowing QT screen capture.  

Run `sudo nano /etc/xdg/autostart/hyperion.desktop` and add the following execution details:
```
[Desktop Entry]
Name=Hyperion
Exec=/usr/bin/hyperiond
Type=Application
```

Reboot the application and you should be able to load the hyperion web UI at http://<SYSTEM_IP>:8090/

## Composite Video

### Video overscan
If you notice that the composite display is wider that your screen, you can set the kernel parameters to adjust the margins of the screen to fit your display.  To do this edit the /boot/firmware/cmdline.txt and add the following to the end of the first line:
```
sudo nano /boot/firmware/cmdline.txt
```

#### Composite:
```
video=Composite-1:720x576@60,margin_left=10,margin_right=18,margin_top=10,margin_bottom=20
```

#### HDMI with composite video conversion adapter:
```
video=HDMI-A-1:720x576@60,margin_left=10,margin_right=18,margin_top=10,margin_bottom=20
```
***Note:** This is just an example.  Ensure you are specifying the device/resolution you have chosen for your setup.*

