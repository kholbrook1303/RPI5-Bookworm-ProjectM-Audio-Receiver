#!/usr/bin/env bash

retry_function() {
    local retries=$2
    local delay=$3
    local count=0
    local command="$1"

    while true; do
        $command
        if [ $? -eq 0 ]; then
            echo "Command '$command' successful"
            break
        else
            count=$((count + 1))
            echo "Command '$command' failed, retrying in $delay seconds... ($count/$retries)"
            if [ $count -ge $retries ]; then
                echo "Max retries reached. Command '$command' failed."
                return 1
            fi
            sleep $delay
        fi
    done
}

# Make sure we are not running in the background
killall python3
killall projectMSDL

# Check for sudo user account
if [ -n "$SUDO_USER" ]; then
	echo "Current user: $username"
else
	echo "Unable to identify SUDO_USER"
	exit 1
fi

# Setup a temp build location
_TMP_BUILDS="/tmp/Builds"
mkdir -p "$_TMP_BUILDS"

_PROJECTM_SDL_PATH="/opt/ProjectMSDL"
_PROJECTM_AR_PATH="/opt/ProjectMAR"

ldconfigOutput=$(ldconfig -v)

# Update repositories
apt update

# Install package dependencies
apt install pulseaudio

# Switch system to use pulseaudio
systemctl --user unmask pulseaudio
systemctl --user --now disable pipewire-media-session.service
systemctl --user --now disable pipewire pipewire-pulse
systemctl --user --now enable pulseaudio.service pulseaudio.socket
apt remove pipewire-audio-client-libraries pipewire

projectMCurrent="4.1.4"
if [[ "$ldconfigOutput" =~ "libprojectM-4.so.$projectMCurrent" ]]; then
	echo "libprojectM $projectMCurrent is already installed"
else
	# Install projectM package dependencies
	apt install -y build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git

	# Download/extract/build libprojectM
	wget "https://github.com/projectM-visualizer/projectm/releases/download/v$projectMCurrent/libprojectM-$projectMCurrent.tar.gz" -P "$_TMP_BUILDS"
	tar xf "$_TMP_BUILDS/libprojectM-$projectMCurrent.tar.gz" -C "$_TMP_BUILDS"
	mkdir -p "$_TMP_BUILDS/libprojectM-$projectMCurrent/cmake-build"
	cmake DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -S "$_TMP_BUILDS/libprojectM-$projectMCurrent" -B "$_TMP_BUILDS/libprojectM-$projectMCurrent/cmake-build"
	cmake --build "$_TMP_BUILDS/libprojectM-$projectMCurrent/cmake-build" --parallel && cmake --build "$_TMP_BUILDS/libprojectM-$projectMCurrent/cmake-build" --target install
fi

libPocoCurrent="1.12.5p2"
if [[ "$ldconfigOutput" =~ "libPocoXML.so.95" ]]; then
	echo "libprojectM $libPocoCurrent is already installed"
else
	# Download/extract/build libPoco-dev
	wget "https://github.com/pocoproject/poco/archive/refs/tags/poco-$libPocoCurrent-release.tar.gz" -P "$_TMP_BUILDS"
	tar xf "$_TMP_BUILDS/poco-$libPocoCurrent-release.tar.gz" -C "$_TMP_BUILDS"
	mkdir -p "$_TMP_BUILDS/poco-poco-$libPocoCurrent-release/cmake-build"
	cmake -S "$_TMP_BUILDS/poco-poco-$libPocoCurrent-release" -B "$_TMP_BUILDS/poco-poco-$libPocoCurrent-release/cmake-build"
	cmake --build "$_TMP_BUILDS/poco-poco-$libPocoCurrent-release/cmake-build" --config Release
	cmake --build "$_TMP_BUILDS/poco-poco-$libPocoCurrent-release/cmake-build" --target install

	# Transfer the libs to /user/lib/
	cp /usr/local/lib/libPoco* /usr/lib/
fi

# Install frontend-sdl2 package dependencies
apt install -y libsdl2-dev libfreetype-dev

# Download/build frontend-sdl2
git clone https://github.com/kholbrook1303/frontend-sdl2.git "$_TMP_BUILDS/frontend-sdl2"
git config --global --add safe.directory "$_TMP_BUILDS/frontend-sdl2"
git -C "$_TMP_BUILDS/frontend-sdl2" submodule init
retry_function "git -C $_TMP_BUILDS/frontend-sdl2 submodule update" 10 5
mkdir -p "$_TMP_BUILDS/frontend-sdl2/cmake-build"
cmake -S "$_TMP_BUILDS/frontend-sdl2" -B "$_TMP_BUILDS/frontend-sdl2/cmake-build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$_TMP_BUILDS/frontend-sdl2/cmake-build" --config Release

# Move SDL build to opt
mkdir -p "$_PROJECTM_SDL_PATH"

cp -r "$_TMP_BUILDS/frontend-sdl2/cmake-build/src/projectMSDL" "$_PROJECTM_SDL_PATH/projectMSDL"
if ! [ -f "$_PROJECTM_SDL_PATH/projectMSDL.properties" ];then
  cp -r "$_TMP_BUILDS/frontend-sdl2/cmake-build/src/projectMSDL.properties" "$_PROJECTM_SDL_PATH/projectMSDL.properties"

  # Set projectMSDL.properties configuration
  sed -i 's/.*window.fullscreen =.*/window.fullscreen = true/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*window.fullscreen.exclusiveMode =.*/window.fullscreen.exclusiveMode = true/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*window.width =.*/window.width = 1280/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*window.height =.*/window.height = 720/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.presetPath =.*/projectM.presetPath = \/opt\/ProjectMSDL\/presets/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.texturePath =.*/projectM.fullscreen = \/opt\/ProjectMSDL\/textures/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.displayDuration =.*/projectM.displayDuration  = 60/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.shuffleEnabled =.*/projectM.shuffleEnabled  = false/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.meshX =.*/projectM.meshX = 64/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.meshY =.*/projectM.meshY = 32/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.transitionDuration =.*/projectM.transitionDuration = 0/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.hardCutsEnabled =.*/projectM.hardCutsEnabled = true/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*projectM.hardCutDuration =.*/projectM.hardCutDuration = 30/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
  sed -i 's/.*logging.channels.file.path =.*/logging.channels.file.path = \/opt\/ProjectMSDL\/ProjectMSDL.log/' "$_PROJECTM_SDL_PATH/projectMSDL.properties"
fi

# Setup textures and presets
git clone https://github.com/kholbrook1303/RPI5-ProjectM-Presets-Textures.git /tmp/Builds/RPI5-ProjectM-Presets-Textures
cp "$_TMP_BUILDS/RPI5-ProjectM-Presets-Textures/presets/" "$_PROJECTM_SDL_PATH" -R
cp "$_TMP_BUILDS/RPI5-ProjectM-Presets-Textures/textures/" "$_PROJECTM_SDL_PATH" -R

# Set permissions on projectMSDL
chown $SUDO_USER "$_PROJECTM_SDL_PATH" -R
chmod 777 -R "$_PROJECTM_SDL_PATH"

# Force the Open GL version
if ! grep -q "MESA_GL_VERSION_OVERRIDE=4.5" "/etc/environment"; then
	echo -e "\nMESA_GL_VERSION_OVERRIDE=4.5" >> /etc/environment
fi

# Download and configure ProjectMAR
git clone -b dev https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git "$_TMP_BUILDS/RPI5-Bookworm-ProjectM-Audio-Receiver"
mkdir -p "$_PROJECTM_AR_PATH"

# Check for old config and move to backup file
if ! [ -f "$_PROJECTM_AR_PATH/projectMAR.conf" ];then
  mv "$_PROJECTM_AR_PATH/projectMAR.conf" "$_PROJECTM_AR_PATH/projectMAR.conf.bak"
fi

# Check for new configs and move to backup file
if [ -f "$_PROJECTM_AR_PATH/conf/projectMAR.conf" ];then
  mv "$_PROJECTM_AR_PATH/conf/projectMAR.conf" "$_PROJECTM_AR_PATH/conf/projectMAR.conf.bak"
fi
if [ -f "$_PROJECTM_AR_PATH/conf/audio_cards.conf" ];then
  mv "$_PROJECTM_AR_PATH/conf/audio_cards.conf" "$_PROJECTM_AR_PATH/conf/audio_cards.conf.bak"
fi
if [ -f "$_PROJECTM_AR_PATH/conf/audio_sinks.conf" ];then
  mv "$_PROJECTM_AR_PATH/conf/audio_sinks.conf" "$_PROJECTM_AR_PATH/conf/audio_sinks.conf.bak"
fi
if [ -f "$_PROJECTM_AR_PATH/conf/audio_sources.conf" ];then
  mv "$_PROJECTM_AR_PATH/conf/audio_sources.conf" "$_PROJECTM_AR_PATH/conf/audio_sources.conf.bak"
fi
if [ -f "$_PROJECTM_AR_PATH/conf/audio_plugins.conf" ];then
  mv "$_PROJECTM_AR_PATH/conf/audio_plugins.conf" "$_PROJECTM_AR_PATH/conf/audio_plugins.conf.bak"
fi

cp -r /tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver/* "$_PROJECTM_AR_PATH"

# Set permissions on projectMAR
chown $SUDO_USER "$_PROJECTM_AR_PATH" -R
chmod 777 -R "$_PROJECTM_AR_PATH"

# Setup python env
python3 -m venv "$_PROJECTM_AR_PATH/env"

# Get all Python dependencies
"$_PROJECTM_AR_PATH/env/bin/python3" -m pip install -r "$_PROJECTM_AR_PATH/requirements.txt"

if grep -q "stage2" "/boot/issue.txt"; then
  if ! [ -f "/etc/systemd/user/projectm.service" ];then
    echo -e "[Unit]\nDescription=ProjectMAR\n\n[Service]\nType=simple\nExecStart=$_PROJECTM_AR_PATH/env/bin/python3 $_PROJECTM_AR_PATH/projectMAR.py\nRestart=on-failure\n\n[Install]\nWantedBy=default.target" > /etc/systemd/user/projectm.service
  fi
else
  if ! [ -f "/etc/xdg/autostart/projectm.desktop" ];then
    echo -e "[Desktop Entry]\nName=ProjectMAR\nExec=$_PROJECTM_AR_PATH/env/bin/python3 $_PROJECTM_AR_PATH/projectMAR.py\nType=Application" > /etc/xdg/autostart/projectm.desktop
  fi
fi

uinputCurrent="1.0.1"
pythonPackages=$("$_PROJECTM_AR_PATH/env/bin/python3" -m pip list)
if [[ "$pythonPackages" =~ "python-uinput $inputCurrent" ]]; then
  echo "uinput is already installed"
else
  echo "uinput is not installed!!!!!"
  # Setup additional python dependencies
  wget "https://github.com/pyinput/python-uinput/archive/refs/tags/$uinputCurrent.tar.gz" -P "$_TMP_BUILDS"
  tar xf "$_TMP_BUILDS/$uinputCurrent.tar.gz" -C "$_TMP_BUILDS"
  cd "$_TMP_BUILDS/python-uinput-$uinputCurrent"
  "$_PROJECTM_AR_PATH/env/bin/python3" "$_TMP_BUILDS/python-uinput-$uinputCurrent/setup.py" build
  "$_PROJECTM_AR_PATH/env/bin/python3" "$_TMP_BUILDS/python-uinput-$uinputCurrent/setup.py" install
  
  # Create a new udev user group
  if ! getent group "groupname" > /dev/null 2>&1; then
  	addgroup uinput
	  usermod -a -G uinput $SUDO_USER
	  chown :uinput /dev/uinput
	  chmod 660 /dev/uinput
  fi
  
  # Create secure udev access rule
  if ! grep -q "uinput" "/etc/udev/rules.d/99-uinput.rules"; then
	  echo "KERNEL=""uinput"", MODE=""0660"", GROUP=""uinput""" > /etc/udev/rules.d/99-uinput.rules

	  # Restart udev
	  udevadm control --reload-rules
	  systemctl restart udev
  fi

  if ! grep -q "uinput" "/etc/modules"; then
	  echo -e "\nuinput" >> /etc/modules
  fi
fi

rm -rf "$_TMP_BUILDS"

reboot