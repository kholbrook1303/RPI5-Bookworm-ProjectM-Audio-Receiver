# 🎵 Raspberry Pi - ProjectM Audio Receiver
The ProjectM Audio Receiver is an application designed for the Raspberry Pi that makes use of the projectM music visualization library, to react from an audio source of the users choosing.

The core components of the application will:
- Handle SDL rendering window
- Initialize projectM using a custom wrapper
- Capture SDL audio and route PCM data to projectM
- Listen for SDL mouse/keyboard/gamepad/window events for user controlled actions and window focus mgmt (if using Raspberry Pi lite OS evdev is used to monitor keyboard/mouse events)

The core controllers of the application will:
- Enforce the display resolution if running the Raspberry Pi desktop OS (Otherwise fullscreen exclusive mode is used for Raspberry Pi lite OS)
- Manage audio routing to ensure the device used to direct PCM audio data to projectM library receives all audio, while also ensuring any device you add for both input and output are routed accordingly so you don't have to manage it yourself.
- Manage audio plugin applications as defined in config.  Currently projectM Audio Receiver has installation instructions for Bluetooth A2DP, AirPlay, Spotify Connect, and Plexamp.

## 🔉 Example Use Cases
The obvious purpose for this is to have visualizations react to sound.  That said there are various use cases for implementation.
- Music player:
  - Add DAC/ADC board for an analog input (e.g. HiFiBerry DAC+ ADC)
  - Add DAC/DSP board for a digital input (e.g. HiFiBerry DAC+ DSP)
  - Use Bluetooth A2DP, AirPlay, Spotify Connect, or Plexamp to "cast" to your device
  - Store music in a local directory or use a usb drive of media and enable the "audio listener" in the projectMAR config file
- Monitoring Ambient Sound:
  - Add a USB microphone to capture sound for visualizing

## 🖼️ Screenshots
![ProjectMAR Screenshot 1](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview1.png)
![ProjectMAR Screenshot 2](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview2.png)
![ProjectMAR Screenshot 3](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview3.png)
![ProjectMAR Screenshot 4](https://github.com/kholbrook1303/RPI5-Bookworm-ProjectM-Audio-Receiver/blob/main/resources/preview4.png)

## 🎞️ Video Preview
[![ProjectMAR Video 1](https://img.youtube.com/vi/8kj53j3EDec/0.jpg)](https://www.youtube.com/watch?v=8kj53j3EDec)

## 💻 Software Requirements:
- Raspberry Pi OS Bookworm:
  - Desktop OS (labwc, wayfire, and x11 are all supported)
  - Lite OS

## 🔩 Hardware Requirements:

- Raspberry Pi
  - Raspberry Pi 4  **This will only work with a reduced resolution and fps*
  - Raspberry Pi 5
- 5v/5A USB-C Power Supply
- SD Card (I recommend the SanDisk 32GB Extreme PRO microSD)
- Case with active cooling (The following are my recommendations)
    - Hifiberry Steel case for RP5 w/active cooling and w/DAC+ ADC card for analog input/output
    - Argon NEO 5 BRED Case for Raspberry Pi 5 with built-in fan
- HDMI Cable with Micro HDMI adapter or Micro HDMI to HDMI cable
- Input device of your choosing (You can always use built in Bluetooth; just know there is potential for interference with the built in card)
    - USB Microphone
    - USB Line in/Aux
    - DAC/ADC

# ⚙️ Installing instructions
For both manual and automated script installation see [SETUP.md](SETUP.md).

# 🖦 Input Event Handling Guide

This document describes how keyboard, controller, and window input events are handled in the application.

---

## ⌨️ Keyboard Input

Handles key presses, with support for modifier keys like **Ctrl**.

### Modifier Support
- `Ctrl` (either left or right) enables certain shortcut actions when combined with other keys.

### Key Bindings

| Key            | With Ctrl? | Action                                  |
|----------------|------------|-----------------------------------------|
| `F`            | ✅         | Toggle fullscreen mode                  |
| `N`            | ❌         | Load **next preset**                    |
| `P`            | ❌         | Load **previous preset**                |
| `Q`            | ✅         | **Exit** the application                |
| `Y`            | ✅         | Toggle **playlist shuffle** mode        |
| `Delete`       | ❌         | **Delete** current preset               |
| `Space`        | ❌         | Toggle **preset lock**                  |
| `Escape`       | ❌         | Toggle fullscreen mode                  |
| `Arrow Up`     | ❌         | Increase **beat sensitivity** (+0.1)    |
| `Arrow Down`   | ❌         | Decrease **beat sensitivity** (−0.1)    |

---

## 🎮 Controller Axis Input (Desktop OS only)

Handles analog stick and trigger inputs. Uses a **deadzone threshold** to avoid accidental movements.

### Axis Bindings

| Axis                          | Condition       | Action                          |
|-------------------------------|------------------|----------------------------------|
| Left Stick X / Trigger Left   | Left / Pressed   | Load **previous preset**         |
| Left Stick X / Trigger Right  | Right / Pressed  | Load **next preset**             |
| Left Stick Y                  | Up               | Increase **beat sensitivity** (+0.1) |
| Left Stick Y                  | Down             | Decrease **beat sensitivity** (−0.1) |

---

## 🎮 Controller Button Input (Desktop OS only)

Handles digital controller buttons such as D-Pad and stick clicks.

### Button Bindings

| Button                           | Action                        |
|----------------------------------|-------------------------------|
| Left Stick Click / Right Stick Click | Toggle **preset lock**      |
| D-Pad Up                         | Increase **beat sensitivity** (+0.1) |
| D-Pad Down                       | Decrease **beat sensitivity** (−0.1) |
| D-Pad Left                       | Load **previous preset**      |
| D-Pad Right                      | Load **next preset**          |

---

## 🗔 Window Events

Handles SDL window-related system events.

### Window Event Bindings

| Event Type                                | Action                                |
|-------------------------------------------|----------------------------------------|
| `SDL_WINDOWEVENT_CLOSE`                   | Exit the application                   |
| `SDL_WINDOWEVENT_RESIZED` / `SIZE_CHANGED`| Update internal rendering dimensions   |
| `SDL_WINDOWEVENT_HIDDEN` / `MINIMIZED`    | Restore and show the window           |
| `SDL_WINDOWEVENT_FOCUS_LOST`              | Log focus loss                         |
| `SDL_WINDOWEVENT_FOCUS_GAINED`            | Log focus gain                         |
