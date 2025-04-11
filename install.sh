#!/usr/bin/env bash

# get user name for setting permissions later
if [ -n "$SUDO_USER" ]
then
	username=$SUDO_USER
	echo "Current user: $username"
else
	echo "Unable to identify SUDO_USER"
	exit 1
fi

# Create a builds directory in the home root to organize dependencies
mkdir /tmp/Builds
 
# Update repositories
apt update

# Install projectM package dependencies
apt install -y build-essential cmake libgl1-mesa-dev mesa-common-dev libglm-dev mesa-utils flex bison openssl libssl-dev git

# Download/extract/build libprojectM
wget https://github.com/projectM-visualizer/projectm/releases/download/v4.1.4/libprojectM-4.1.4.tar.gz -P /tmp/Builds
tar xf /tmp/Builds/libprojectM-4.1.4.tar.gz -C /tmp/Builds
mkdir /tmp/Builds/libprojectM-4.1.4/cmake-build
cmake DENABLE_GLES=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -S /tmp/Builds/libprojectM-4.1.4 -B /tmp/Builds/libprojectM-4.1.4/cmake-build
cmake --build /tmp/Builds/libprojectM-4.1.4/cmake-build --parallel && cmake --build /tmp/Builds/libprojectM-4.1.4/cmake-build --target install

# Download/extract/build libPoco-dev
wget https://github.com/pocoproject/poco/archive/refs/tags/poco-1.12.5p2-release.tar.gz -P /tmp/Builds
tar xf /tmp/Builds/poco-1.12.5p2-release.tar.gz -C /tmp/Builds
mkdir /tmp/Builds/poco-poco-1.12.5p2-release/cmake-build
cmake -S /tmp/Builds/poco-poco-1.12.5p2-release -B /tmp/Builds/poco-poco-1.12.5p2-release/cmake-build
cmake --build /tmp/Builds/poco-poco-1.12.5p2-release/cmake-build --config Release
cmake --build /tmp/Builds/poco-poco-1.12.5p2-release/cmake-build --target install

cp /usr/local/lib/libPoco* /usr/lib/

# Install frontend-sdl2 package dependencies
apt install -y libsdl2-dev libfreetype-dev

# Download/build frontend-sdl2
git clone https://github.com/kholbrook1303/frontend-sdl2.git /tmp/Builds/frontend-sdl2
git config --global --add safe.directory /tmp/Builds/frontend-sdl2
git -C /tmp/Builds/frontend-sdl2 submodule init
git -C /tmp/Builds/frontend-sdl2 submodule update
mkdir /tmp/Builds/frontend-sdl2/cmake-build
cmake -S /tmp/Builds/frontend-sdl2 -B /tmp/Builds/frontend-sdl2/cmake-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/Builds/frontend-sdl2/cmake-build --config Release

mkdir /opt/ProjectMSDL
cp -r /tmp/Builds/frontend-sdl2/cmake-build/src/projectMSDL /opt/ProjectMSDL/
cp -r /tmp/Builds/frontend-sdl2/cmake-build/src/projectMSDL.properties /opt/ProjectMSDL/

# Setup textures and presets
git clone https://github.com/kholbrook1303/RPI5-ProjectM-Presets-Textures.git /tmp/Builds/RPI5-ProjectM-Presets-Textures
cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/presets/ /opt/ProjectMSDL/ -R
cp /tmp/Builds/RPI5-ProjectM-Presets-Textures/textures/ /opt/ProjectMSDL/ -R

# Set permissions on projectMSDL
chown $username /opt/ProjectMSDL/ -R
chmod 777 -R /opt/ProjectMSDL

# Force the Open GL version
if ! grep -q "MESA_GL_VERSION_OVERRIDE=4.5" "/etc/environment"; then
	echo -e "MESA_GL_VERSION_OVERRIDE=4.5" >> /etc/environment
fi

# Install ProjectMAR package dependencies
apt install pulseaudio

# Download and configure ProjectMAR
git clone https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver.git /tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver
mkdir /opt/ProjectMAR
cp -r /tmp/Builds/RPI5-Bookworm-ProjectM-Audio-Receiver/* /opt/ProjectMAR/

# Set permissions on projectMAR
chown $username /opt/ProjectMAR/ -R
chmod 777 -R /opt/ProjectMAR

# Setup python env
python3 -m venv /opt/ProjectMAR/env

# Setup additional python dependencies
wget https://github.com/pyinput/python-uinput/archive/refs/tags/1.0.1.tar.gz -P /tmp/Builds
tar xf /tmp/Builds/1.0.1.tar.gz -C /tmp/Builds
cd /tmp/Builds/python-uinput-1.0.1
/opt/ProjectMAR/env/bin/python3 /tmp/Builds/python-uinput-1.0.1/setup.py build
/opt/ProjectMAR/env/bin/python3 /tmp/Builds/python-uinput-1.0.1/setup.py install

# Create a new udev user group
if ! getent group "groupname" > /dev/null 2>&1; then
	addgroup uinput
	usermod -a -G uinput $username
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

# Get all Python dependencies
/opt/ProjectMAR/env/bin/python3 -m pip install -r /opt/ProjectMAR/requirements.txt

if grep -q "stage2" "/boot/issue.txt"; then
  echo -e "[Unit]\nDescription=ProjectMAR\n\n[Service]\nType=simple\nExecStart=/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py\nRestart=on-failure\n\n[Install]\nWantedBy=default.target" > /etc/systemd/user/projectm.service
else
  echo -e "[Desktop Entry]\nName=ProjectMAR\nExec=/opt/ProjectMAR/env/bin/python3 /opt/ProjectMAR/projectMAR.py\nType=Application" > /etc/xdg/autostart/projectm.desktop
fi

rm -rf /tmp/Builds