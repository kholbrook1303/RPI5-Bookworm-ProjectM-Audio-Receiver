#!/usr/bin/env bash

# Check for sudo user account
if [ -n "$SUDO_USER" ]; then
	echo "Identified current user as: $SUDO_USER"
else
	echo "Unable to identify SUDO_USER"
	exit 1
fi

INSTALLATION_MODE=""
INSTALLATION_PLUGINS=""
INSTALLATION_AUTOSTART="false"
INSTALLATION_LOGFILE="/home/$SUDO_USER/projectMAR-installer.log"

# Check for an existing log file and move it to an indexed backup if exists
if [ -e "$INSTALLATION_LOGFILE" ]; then
  while [ -e "${INSTALLATION_LOGFILE}.${idx}" ]; do
    idx=$((idx + 1))
  done
  mv "$INSTALLATION_LOGFILE" "${INSTALLATION_LOGFILE}.${idx}"
fi

PROJECTMSDL_PATH="/opt/ProjectMSDL"
PROJECTMAR_PATH="/opt/ProjectMAR"
TMP_BUILDS="/tmp/Builds"
VIDEO_OUTPUT=""
RPI_MODEL=""

LIBPROJECTM_VERSION="4.1.4"
LIBPOCO_VERSION="1.12.5p2"
UINPUT_VERSION="1.0.1"

usage() {
    cat << EOF
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

Examples:
    install.sh -m optimized -p a2dp,shairport-sync,spotifyd,plexamp     (Everything Optimized)
    install.sh -m minimal -p a2dp,shairport-sync                        (Non premium plugins)
    install.sh -m optimized -a                                          (Autostart projectMAR; No plugins)
    install.sh -p a2dp,shairport-sync,spotifyd,plexamp                  (Only plugins)
    install.sh -m uninstall                                             (Uninstall projectMAR)
EOF
}

log() {
  echo "$(date +'%Y-%m-%d %H:%M:%S') - ProjectMAR Installer - $1" >> "$INSTALLATION_LOGFILE"
}

adjust_user_permissions() {
    chown $SUDO_USER "$1" -R
    chmod 777 -R "$1"
}

create_service() {
    if ! [ -f "/etc/systemd/$1/$2.service" ];then
        cat > "/etc/systemd/$1/$2.service" << EOF
[Unit]
Description=$3

[Service]
Type=simple
ExecStart=$4
Restart=on-failure

[Install]
WantedBy=default.target
EOF
    fi
}

retry_function() {
    local retries=$2
    local delay=$3
    local count=0
    local command="$1"

    while true; do
        $command
        if [ $? -eq 0 ]; then
            log "Command '$command' successful"
            break
        else
            count=$((count + 1))
            log "Command '$command' failed, retrying in $delay seconds... ($count/$retries)"
            if [ $count -ge $retries ]; then
                log "Max retries reached. Command '$command' failed."
                return 1
            fi
            sleep $delay
        fi
    done
}

is_desktop() {
    if grep -q "stage2" "/boot/issue.txt"; then
        return 1
    else
        return 0
    fi
}

is_library_current() {
    ldconfigOutput=$(ldconfig -v)
    if [[ "$ldconfigOutput" =~ $1 ]]; then
        return 0
    else
        return 1
    fi
}

install_libprojectm() {
    if is_library_current "libprojectM-4.so.$LIBPROJECTM_VERSION"; then
        log "libprojectM $LIBPROJECTM_VERSION is already installed"
    else
        log "Installing libprojectM $LIBPROJECTM_VERSION"

        # Install projectM package dependencies
        apt install -y build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git
        # Download/extract/build libprojectM
        wget "https://github.com/projectM-visualizer/projectm/releases/download/v$LIBPROJECTM_VERSION/libprojectM-$LIBPROJECTM_VERSION.tar.gz" -P "$TMP_BUILDS"
        tar xf "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION.tar.gz" -C "$TMP_BUILDS"
        mkdir -p "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION/cmake-build"
        cmake DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -S "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION" -B "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION/cmake-build"
        cmake --build "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION/cmake-build" && cmake --build "$TMP_BUILDS/libprojectM-$LIBPROJECTM_VERSION/cmake-build" --target install
    fi
}

install_libpoco() {
    if is_library_current "libPocoXML.so.95"; then
        log "libPoco is already installed"
    else
        log "Installing libPoco (This will take some time)"
        
        # Download/extract/build libPoco-dev
        wget "https://github.com/pocoproject/poco/archive/refs/tags/poco-$LIBPOCO_VERSION-release.tar.gz" -P "$TMP_BUILDS"
        tar xf "$TMP_BUILDS/poco-$LIBPOCO_VERSION-release.tar.gz" -C "$TMP_BUILDS"
        mkdir -p "$TMP_BUILDS/poco-poco-$LIBPOCO_VERSION-release/cmake-build"
        cmake -S "$TMP_BUILDS/poco-poco-$LIBPOCO_VERSION-release" -B "$TMP_BUILDS/poco-poco-$LIBPOCO_VERSION-release/cmake-build"
        cmake --build "$TMP_BUILDS/poco-poco-$LIBPOCO_VERSION-release/cmake-build" --config Release
        cmake --build "$TMP_BUILDS/poco-poco-$LIBPOCO_VERSION-release/cmake-build" --target install

        # Transfer the libs to /user/lib/
        cp /usr/local/lib/libPoco* /usr/lib/
    fi
}

install_frontend_sdl() {
    if ! [ -f "$PROJECTMSDL_PATH/projectMSDL" ] || ! [ -f "$PROJECTMSDL_PATH/projectMSDL.properties" ]; then
        log "Installing projectMSDL"

        # Move SDL build to opt
        mkdir -p "$PROJECTMSDL_PATH"

        # Install frontend-sdl2 package dependencies
        apt install -y libsdl2-dev libfreetype-dev

        # Download/build frontend-sdl2
        git clone https://github.com/kholbrook1303/frontend-sdl2.git "$TMP_BUILDS/frontend-sdl2"
        git config --global --add safe.directory "$TMP_BUILDS/frontend-sdl2"
        git -C "$TMP_BUILDS/frontend-sdl2" submodule init
        retry_function "git -C $TMP_BUILDS/frontend-sdl2 submodule update" 10 5
        mkdir -p "$TMP_BUILDS/frontend-sdl2/cmake-build"
        cmake -S "$TMP_BUILDS/frontend-sdl2" -B "$TMP_BUILDS/frontend-sdl2/cmake-build" -DCMAKE_BUILD_TYPE=Release
        cmake --build "$TMP_BUILDS/frontend-sdl2/cmake-build" --config Release

        # Move projectMSDL
        cp -r "$TMP_BUILDS/frontend-sdl2/cmake-build/src/projectMSDL" "$PROJECTMSDL_PATH/projectMSDL"
        cp -r "$TMP_BUILDS/frontend-sdl2/cmake-build/src/projectMSDL.properties" "$PROJECTMSDL_PATH/projectMSDL.properties"


        # Setup textures and presets
        git clone https://github.com/kholbrook1303/RPI5-ProjectM-Presets-Textures.git /tmp/Builds/RPI5-ProjectM-Presets-Textures
        cp "$TMP_BUILDS/RPI5-ProjectM-Presets-Textures/presets/" "$PROJECTMSDL_PATH" -R
        cp "$TMP_BUILDS/RPI5-ProjectM-Presets-Textures/textures/" "$PROJECTMSDL_PATH" -R

        # Set permissions on projectMSDL
        adjust_user_permissions $PROJECTMSDL_PATH
    else
        log "projectMSDL is already installed"
    fi
}

configure_frontend_sdl() {
    log "Configuring projectMSDL"

    # Set projectMSDL.properties configuration
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.fullscreen .*/window.fullscreen = true/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.fullscreen.exclusiveMode .*/window.fullscreen.exclusiveMode = true/"
    
    if [ $VIDEO_OUTPUT = "composite" ]; then
        sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.width .*/window.width = 720/"
        sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.height .*/window.height = 480/"

        if [ $RPI_MODEL = "4" ]; then
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.fps .*/projectM.fps = 30/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshX .*/projectM.meshX = 48/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshY .*/projectM.meshY = 32/"

        elif [ $RPI_MODEL = "5" ]; then
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.fps .*/projectM.fps = 60/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshX .*/projectM.meshX = 64/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshY .*/projectM.meshY = 32/"

        fi
    elif [ $VIDEO_OUTPUT = "hdmi" ]; then
        if [ $RPI_MODEL = "4" ]; then
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.width .*/window.width = 720/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.height .*/window.height = 576/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.fps .*/projectM.fps = 30/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshX .*/projectM.meshX = 48/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshY .*/projectM.meshY = 32/"

        elif [ $RPI_MODEL = "5" ]; then
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.width .*/window.width = 1280/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?window.height .*/window.height = 720/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.fps .*/projectM.fps = 60/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshX .*/projectM.meshX = 64/"
            sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.meshY .*/projectM.meshY = 32/"
        fi
    fi

    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.presetPath .*/projectM.presetPath = \/opt\/ProjectMSDL\/presets/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.texturePath .*/projectM.texturePath = \/opt\/ProjectMSDL\/textures/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.displayDuration .*/projectM.displayDuration = 60/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.shuffleEnabled .*/projectM.shuffleEnabled = false/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.transitionDuration .*/projectM.transitionDuration = 0/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.hardCutsEnabled .*/projectM.hardCutsEnabled = true/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?projectM.hardCutDuration .*/projectM.hardCutDuration = 30/"
    sed "$PROJECTMSDL_PATH/projectMSDL.properties" -i -e "s/^#\\?logging.channels.file.path .*/logging.channels.file.path = \/opt\/ProjectMSDL\/ProjectMSDL.log/"
}

install_projectmar() {
    log "Installing ProjectMAR"

    # Download and configure ProjectMAR
    git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git "$TMP_BUILDS/RPI5-Bookworm-ProjectM-Audio-Receiver"
    mkdir -p "$PROJECTMAR_PATH"
    
    appItems=("conf" "lib" "projectMAR.py" "requirements.txt")
    for appItem in "${appItems[@]}"; do
        if [ "$appItem" = "conf" ]; then
            if [ -d "$PROJECTMAR_PATH/conf" ]; then
                log "The ProjectMAR configuration path already exists in $PROJECTMAR_PATH"
                log "Skipping over configurations"
            else
                log "$appItem does not exist in $PROJECTMAR_PATH"
                cp -r "/tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver/$appItem" "$PROJECTMAR_PATH"
            fi
        else
            cp -r "/tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver/$appItem" "$PROJECTMAR_PATH"
        fi
    done

    # Set permissions on projectMAR
    adjust_user_permissions $PROJECTMAR_PATH
    
    # Setup python env
    python3 -m venv "$PROJECTMAR_PATH/env"
    
    # Get all Python dependencies
    "$PROJECTMAR_PATH/env/bin/python3" -m pip install -r "$PROJECTMAR_PATH/requirements.txt"

    if is_desktop; then
        echo -e "/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py" > /home/$SUDO_USER/Desktop/projectMAR.sh
        chmod +x "/home/$SUDO_USER/Desktop/projectMAR.sh"
    fi
}

configure_projectmar() {
    log "Configuring projectMAR"

  # Set the appropriate resolution in configuration
    if [ $VIDEO_OUTPUT = "composite" ]; then
        sed "$PROJECTMAR_PATH/conf/projectMAR.conf" -i -e "s/^#\\?resolution.*/resolution=720x480/"
    elif [ $VIDEO_OUTPUT = "hdmi" ]; then
        if [ $RPI_MODEL = "4" ]; then
            sed "$PROJECTMAR_PATH/conf/projectMAR.conf" -i -e "s/^#\\?resolution.*/resolution=720x576/"
        elif [ $RPI_MODEL = "5" ]; then
            sed "$PROJECTMAR_PATH/conf/projectMAR.conf" -i -e "s/^#\\?resolution.*/resolution=1280x720/"
        fi
    fi
}

configure_projectmar_autostart() {
    log "Configuring projectMAR autostart"

    if is_desktop; then
        if ! [ -f "/etc/xdg/autostart/projectm.desktop" ]; then
            cat > "/etc/xdg/autostart/projectm.desktop" << EOF
[Desktop Entry]
Name=ProjectMAR
Exec=$PROJECTMAR_PATH/env/bin/python3 $PROJECTMAR_PATH/projectMAR.py
Type=Application
EOF
        fi
    else
        if ! [ -f "/etc/systemd/user/projectm.service" ];then
            cat > "/etc/systemd/user/projectm.service" << EOF
[Unit]
Description=ProjectMAR

[Service]
Type=simple
ExecStart=$PROJECTMAR_PATH/env/bin/python3 $PROJECTMAR_PATH/projectMAR.py
Restart=on-failure

[Install]
WantedBy=default.target
EOF
        fi
    fi
}

install_uinput() {
    pythonPackages=$("$PROJECTMAR_PATH/env/bin/python3" -m pip list)
    if [[ "$pythonPackages" =~ "python-uinput $inputCurrent" ]]; then
        log "uinput is already installed"
    else
        log "Installing uinput"
        
        # Setup additional python dependencies
        wget "https://github.com/pyinput/python-uinput/archive/refs/tags/$UINPUT_VERSION.tar.gz" -P "$TMP_BUILDS"
        tar xf "$TMP_BUILDS/$UINPUT_VERSION.tar.gz" -C "$TMP_BUILDS"
        cd "$TMP_BUILDS/python-uinput-$UINPUT_VERSION"
        "$PROJECTMAR_PATH/env/bin/python3" "$TMP_BUILDS/python-uinput-$UINPUT_VERSION/setup.py" build
        "$PROJECTMAR_PATH/env/bin/python3" "$TMP_BUILDS/python-uinput-$UINPUT_VERSION/setup.py" install
    fi
    
    # Create a new udev user group
    if ! getent group uinput > /dev/null 2>&1; then
        addgroup uinput
        usermod -a -G uinput $SUDO_USER
        chown :uinput /dev/uinput
        chmod 660 /dev/uinput
    else
        log "uinput group already exists!"
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
}

add_audio_plugin_config() {
    if [ -f "$PROJECTMAR_PATH/conf/audio_plugins.conf" ]; then
        audioPlugins=$(grep "^audio_plugins=" "$PROJECTMAR_PATH/conf/audio_plugins.conf")
        if [[ "$audioPlugins" == "audio_plugins=" ]]; then
            sed "$PROJECTMAR_PATH/conf/audio_plugins.conf" -i -e "s/^audio_plugins=.*/&$1/"
        elif [[ ! "$audioPlugins" =~ $1 ]]; then
            sed "$PROJECTMAR_PATH/conf/audio_plugins.conf" -i -e "s/^audio_plugins=.*/&,$1/"
        fi

        pluginSection=$(grep "\[$1\]" "$PROJECTMAR_PATH/conf/audio_plugins.conf")
        if [[ ! "$pluginSection" =~ "$1" ]]; then
            cat >> "$PROJECTMAR_PATH/conf/audio_plugins.conf" << EOF

[$1]
name=$2
path=$3
arguments=$4
restore=$5
EOF
        fi
    fi
}

install_plugin_a2dp() {
    log "Installing a2dp plugin"

    # Install bluetooth dependencies
    apt install -y pulseaudio-module-bluetooth bluez-tools

    # Setup bt mode
    sed -i 's/.*#Class = 0x000100.*/Class = 0x41C/' /etc/bluetooth/main.conf
    sed -i 's/^#\(.*DiscoverableTimeout.*\)/\1/' /etc/bluetooth/main.conf

    # restart service
    systemctl restart bluetooth

    log "Waiting for bluetooth to reinitialize..."
    sleep 5

    # Enable bt adapter and turn on pairable
    bluetoothctl power on
    bluetoothctl discoverable on
    bluetoothctl pairable on
    bluetoothctl agent on

    if systemctl is-active --quiet bt-agent; then
        log "bt-agent is already installed"
    else
        log "Installing bt-agent"

        # Install bt agent service
        if ! [ -f "/etc/systemd/system/bt-agent.service" ];then
            cat > "/etc/systemd/system/bt-agent.service" << EOF
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
EOF
        fi

        # Enable and restart service
        systemctl enable bt-agent
        systemctl start bt-agent
    fi
}

install_plugin_shairport-sync() {
    log "Installing shairport-sync plugin"

    if ! [ -f "/usr/local/bin/spotifyd" ]; then
        log "Installing shairport-sync"

        # Install the shairport-sync dependencies
        apt install -y --no-install-recommends build-essential git autoconf automake libtool libpulse-dev libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev libssl-dev libsoxr-dev libplist-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev uuid-dev libgcrypt-dev xxd

        # Download and build Shairport-Sync
        mkdir -p /tmp/Builds
        wget https://github.com/mikebrady/shairport-sync/archive/refs/tags/4.3.5.tar.gz -P /tmp/Builds
        tar xf /tmp/Builds/4.3.5.tar.gz -C /tmp/Builds/
        autoreconf -fi /tmp/Builds/shairport-sync-4.3.5/
        cd /tmp/Builds/shairport-sync-4.3.5
        ./configure --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2 --with-pa
        make -C /tmp/Builds/shairport-sync-4.3.5/
        make -C /tmp/Builds/shairport-sync-4.3.5/ install
    else
        log "shairport-sync is already installed"
    fi

    if systemctl is-active --quiet nqptp; then
        log "nqptp is already installed"
    else
        log "Installing nqptp"

        # Download and build nqptp
        wget https://github.com/mikebrady/nqptp/archive/refs/tags/1.2.4.tar.gz -P /tmp/Builds
        tar xf /tmp/Builds/1.2.4.tar.gz -C /tmp/Builds/
        autoreconf -fi /tmp/Builds/nqptp-1.2.4/
        cd /tmp/Builds/nqptp-1.2.4
        ./configure --with-systemd-startup
        make -C /tmp/Builds/nqptp-1.2.4/
        make -C /tmp/Builds/nqptp-1.2.4/ install

        # Enable and start nqptp service
        systemctl enable nqptp
        systemctl start nqptp
    fi

    add_audio_plugin_config "shairport-sync" "Shairport-Sync" "/usr/local/bin/shairport-sync" "" "true"
}

install_plugin_spotifyd() {
    log "Installing spotifyd plugin"
    if ! [ -f "/usr/local/bin/spotifyd" ]; then
        log "Installing spotifyd"

        # Download and install spotifyd
        mkdir -p /tmp/Builds
        wget https://github.com/Spotifyd/spotifyd/releases/download/v0.4.0/spotifyd-linux-aarch64-default.tar.gz -P /tmp/Builds
        tar xzf /tmp/Builds/spotifyd-linux-aarch64-default.tar.gz -C /tmp/Builds/
        chmod +x /tmp/Builds/spotifyd
        chown root:root /tmp/Builds/spotifyd
        mv /tmp/Builds/spotifyd /usr/local/bin/spotifyd
    else
        log "spotifyd is already installed"
    fi

    if ! [ -f "/etc/spotifyd.conf" ]; then
        # Download spotifyd configuration file
        wget https://github.com/Spotifyd/spotifyd/archive/refs/tags/v0.4.0.tar.gz -P /tmp/Builds
        tar xf /tmp/Builds/v0.4.0.tar.gz -C /tmp/Builds/
        cp /tmp/Builds/spotifyd-0.4.0/contrib/spotifyd.conf /etc/spotifyd.conf

        # Set ProjectMAR config
        sed -i 's/.*#backend.*/backend = "pulseaudio"/' /etc/spotifyd.conf
        sed -i 's/.*#device_name.*/device_name = "ProjectMAR"/' /etc/spotifyd.conf
        sed -i 's/.*#device_type.*/device_type = "a_v_r"/' /etc/spotifyd.conf
    else
        log "spotifyd configuration file already exists"
    fi

    add_audio_plugin_config "spotifyd" "Spotify" "/usr/local/bin/spotifyd" "--no-daemon --backend pulseaudio" "true"
}

install_plugin_plexamp() {
    log "Installing PlexAmp plugin"

    # Setup NodeJS if not installed
    log "Checking for NodeJs"
    if which node > /dev/null; then
        log 'NodeJs is already installed'
    else
        log "Installing NodeJs..."
        apt-get install -y ca-certificates curl gnupg
        mkdir -p /etc/apt/keyrings
        curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
        echo deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main | tee /etc/apt/sources.list.d/nodesource.list
        apt-get update && apt-get install -y nodejs
    fi

    if ! [ -f "/opt/plexamp/js/index.js" ]; then
        log "Installing PlexAmp"

        # Download and install Plexamp
        mkdir -p /tmp/Builds
        wget https://plexamp.plex.tv/headless/Plexamp-Linux-headless-v4.12.2.tar.bz2 -P /tmp/Builds
        tar xvjf /tmp/Builds/Plexamp-Linux-headless-v4.12.2.tar.bz2 -C /tmp/Builds/
        rm -rf /opt/plexamp
        cp /tmp/Builds/plexamp/ /opt/ -r
    else
        log "PlexAmp is already installed"
    fi

    # Setup your Plexamp token
    log "Checking for PlexAmp registration"
    if ! [ -f "/home/$SUDO_USER/.local/share/Plexamp/Settings/%40Plexamp%3Auser%3AsubscriptionActive" ]; then
        # This does not work when run from bash script
        #sudo -u $SUDO_USER node /opt/plexamp/js/index.js key="$claimToken" name="$deviceName"
        echo "PlexAmp has not been registered!"
        echo "Please run 'node /opt/plexamp/js/index.js' in a seperate terminal to register with Plex"
        read -p "Press any key to continue once complete..." complete </dev/tty
    else
        log "PlexAmp registration is current"
    fi

    add_audio_plugin_config "plexamp" "PlexAmp" "/usr/bin/node" "/opt/plexamp/js/index.js" "true"
}

while getopts "m:ap:h" opt; do
    case $opt in
        m)
            INSTALLATION_MODE="$OPTARG"
        ;;
        a)
            INSTALLATION_AUTOSTART="true"
        ;;
        p)
            INSTALLATION_PLUGINS="$OPTARG"
        ;;
        h)
            usage
            exit 1
        ;;
    esac
done

# Make sure we are not running in the background
if pgrep -x python3 > /dev/null; then
    log "Identified python3 running.  Closing application to proceed with installation..."
    killall python3
fi
if pgrep -x projectMSDL > /dev/null; then
    log "Identified projectMSDL running.  Closing application to proceed with installation..."
    killall projectMSDL
fi

# Setup a temp build location
mkdir -p "$TMP_BUILDS"

# Determine the output video mode
videoDevices=$(find /sys/devices -name "edid")
if [[ "$videoDevices" =~ "Composite" ]]; then
    log "Composiite display mode has been identified"
    VIDEO_OUTPUT="composite"
elif [[ "$videoDevices" =~ "HDMI" ]]; then
    log "HDMI display mode has been identified"
    VIDEO_OUTPUT="hdmi"
else
    log "Unable to detect video output device!"
    exit 1
fi

if is_desktop; then
    log "The Raspberry Pi is running desktop OS"
else
    log "The Raspberry Pi is running lite OS"
fi

# Determine the Raspberry Pi model
cpuInfo=$(cat /proc/cpuinfo)
if [[ "$cpuInfo" =~ "Raspberry Pi 4" ]]; then
    log "Raspberry Pi model 4 has been detected"
    RPI_MODEL="4"
elif [[ "$cpuInfo" =~ "Raspberry Pi 5" ]]; then
    log "Raspberry Pi model 5 has been detected"
    RPI_MODEL="5"
else
    log "Unable to detect Raspberry Pi or model is not supported!"
    exit 1
fi

if [ -n "$INSTALLATION_MODE" ]; then
    uninstall=false
    configure=false

    case "$INSTALLATION_MODE" in
        minimal)
            log "Running 'minimal' installation..."
        ;;
        optimized)
            log "Running 'optimized' installation..."
            configure=true
        ;;
        uninstall)
            log "Running uninstallation (This does not currently uninstall plugins)..."
            uninstall=true
        ;;
    esac

    if $uninstall; then
        rm -rf "$_PROJECTM_SDL_PATH"
        rm -rf "$_PROJECTM_AR_PATH"

        if [ -f "/etc/systemd/user/projectm.service" ];then
            rm /etc/systemd/user/projectm.service
        elif [ -f "/etc/xdg/autostart/projectm.desktop" ];then
            rm /etc/xdg/autostart/projectm.desktop
        fi

        if [ -f "/home/$SUDO_USER/Desktop/projectMAR.sh" ];then
            rm "/home/$SUDO_USER/Desktop/projectMAR.sh"
        fi

        find /usr/local/lib -type f -name "libPoco*" -exec rm {} \;
        find /usr/lib -type f -name "libPoco*" -exec rm {} \;
        find /usr/local/lib -type f -name "libprojectM*" -exec rm {} \;
        
        reboot

    else
        # Update repositories
        apt update
        # Install package dependencies
        apt install -y pulseaudio

        # Install uinput
        install_uinput
        
        # Switch system to use pulseaudio (Pipewire is currently not supported)
        systemctl --global -q disable pipewire-pulse
        systemctl --global -q disable wireplumber
        systemctl --global -q enable pulseaudio
        if [ -e /etc/alsa/conf.d/99-pipewire-default.conf ] ; then
            rm /etc/alsa/conf.d/99-pipewire-default.conf
        fi

        # Setup projectM requirements
        install_libprojectm
        install_libpoco
        install_frontend_sdl

        # Setup projectM Audio Receiver
        install_projectmar

        # Configure projectM and Audio Receiver
        if $configure; then
            log "Configuring projectMSDL and projectMAR..."
            configure_frontend_sdl
            configure_projectmar
        fi

        if $INSTALLATION_AUTOSTART; then
            log "Configuring autostart for projectMAR..."
            configure_projectmar_autostart
        fi

        # Force the Open GL version
        if ! grep -q "MESA_GL_VERSION_OVERRIDE=4.5" "/etc/environment"; then
            echo -e "\nMESA_GL_VERSION_OVERRIDE=4.5" >> /etc/environment
        fi

    fi

else
    log "No mode was specified for projectMAR installation"
fi

log "The following audio plugins will be installed: $INSTALLATION_PLUGINS"
if [ -n "$INSTALLATION_PLUGINS" ]; then
    IFS=',' read -ra parts <<< "$INSTALLATION_PLUGINS"
        for part in "${parts[@]}"; do
            plugin_function="install_plugin_$part"
            $plugin_function
        done

    if [ -f "$PROJECTMAR_PATH/conf/projectMAR.conf" ]; then
        sed "$PROJECTMAR_PATH/conf/projectMAR.conf" -i -e "s/^#\\?audio_plugin.*/audio_plugin=True/"
    fi
  
else
    log "No plugins were specified for installation"
fi

reboot