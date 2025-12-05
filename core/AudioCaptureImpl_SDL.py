import time
import sdl2
import ctypes
import logging
import numpy as np
import threading

log = logging.getLogger()

class AudioCaptureImpl:
    def __init__(self, config, projectm_wrapper):
        self.projectm_wrapper = projectm_wrapper
        
        self.currentAudioDeviceIndex    = -1
        self.currentAudioDeviceID       = 0
        self.channels                   = 2

        self.requestedSampleFrequency   = 44100
        self.requestedSampleCount       = 44100 / 60

        self.audio_callback_event       = threading.Event()

        targetFps = config.projectm.get('projectm.fps', 60)
        if targetFps > 0:
            self.requestedSampleCount = min(self.requestedSampleFrequency // targetFps, self.requestedSampleCount)
            # Don't let the buffer get too small to prevent excessive update calls.
            # 300 samples is enough for 144 FPS.
            self.requestedSampleCount = max(self.requestedSampleCount, 300)

        log.info(f'AudioCaptureImpl: sample_frequency={self.requestedSampleFrequency}, sample_count={self.requestedSampleCount}, channels={self.channels}, targetFps={targetFps}')

        sdl2.SDL_SetHint(sdl2.SDL_HINT_AUDIO_INCLUDE_MONITORS, b"1")
        sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO)

    def __del__(self):
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_AUDIO)

    def set_capture_started(self):
        self.audio_callback_event.set()

    def audio_device_list(self):
        deviceList = {
            -1: "Default capturing device"
            }

        recordingDeviceCount = sdl2.SDL_GetNumAudioDevices(True)

        for i in range(recordingDeviceCount):
            deviceName = sdl2.SDL_GetAudioDeviceName(i, True)
            if deviceName:
                deviceList[i] = deviceName
            else:
                log.error(f'Could not get device name for device ID {i}: {sdl2.SDL_GetError()}')
                
        return deviceList

    def monitor_callback_start(self):
        if self.audio_callback_event.wait(timeout=0.1):
            log.info("Audio capture callback started successfully")
        else:
            self.restart_audio_device()
        self.audio_callback_event.clear()

    def start_recording(self, index):
        self.currentAudioDeviceIndex = index

        try:
            if self.open_audio_device():
                sdl2.SDL_PauseAudioDevice(self.currentAudioDeviceID, False)
                
            threading.Thread(target=self.monitor_callback_start, daemon=True).start()

        except:
            log.exception('Failed to start recording!')

    def restart_audio_device(self):
        log.debug("Restarting audio device...")
        self.stop_recording()

        self.start_recording(self.currentAudioDeviceIndex)

    def stop_recording(self):
        if self.currentAudioDeviceID:
            sdl2.SDL_PauseAudioDevice(self.currentAudioDeviceID, True)
            sdl2.SDL_CloseAudioDevice(self.currentAudioDeviceID)
            self.currentAudioDeviceID = 0
            time.sleep(0.1)

    def next_audio_device(self):
        self.stop_recording()
        device_id = ((self.currentAudioDeviceIndex + 2) % (sdl2.SDL_GetNumAudioDevices(True) + 1)) - 1
        self.start_recording(device_id)

    def fill_buffer(self):
        pass

    def set_audio_device_index(self, index):
        if index > 1 and index < sdl2.SDL_GetNumAudioDevices(True):
            self.currentAudioDeviceID = index
            self.start_recording()

    def get_audio_device_index(self):
        return self.currentAudioDeviceID

    def open_audio_device(self):
        self.user_data = ctypes.py_object(self)
        user_data_ptr = ctypes.cast(ctypes.pointer(self.user_data), ctypes.c_void_p)

        requestedSpecs = sdl2.SDL_AudioSpec(
            self.requestedSampleFrequency, 
            sdl2.AUDIO_F32SYS, 
            self.channels, 
            int(self.requestedSampleCount),
            audio_callback,
            user_data_ptr
            )

        actualSpecs = sdl2.SDL_AudioSpec(
            freq=0,
            aformat=0,
            channels=0,
            samples=0
            )

        deviceName = sdl2.SDL_GetAudioDeviceName(self.currentAudioDeviceIndex, True)

        self.currentAudioDeviceID = sdl2.SDL_OpenAudioDevice(
            deviceName, True, 
            requestedSpecs, 
            actualSpecs, 
            sdl2.SDL_AUDIO_ALLOW_CHANNELS_CHANGE
            )

        if self.currentAudioDeviceID == 0:
            err = sdl2.SDL_GetError()
            raise Exception(
                f"Failed to open audio device {deviceName!r} "
                f"(index {self.currentAudioDeviceIndex}): {err}"
            )

        log.debug(
            f"Opened audio capture device "
            f"name={deviceName!r} index={self.currentAudioDeviceIndex} -> deviceID={self.currentAudioDeviceID}"
            )
        log.debug(
            f"Actual specs: freq={actualSpecs.freq}, "
            f"format={actualSpecs.format}, "
            f"channels={actualSpecs.channels}, "
            f"samples={actualSpecs.samples}"
            )

        status = sdl2.SDL_GetAudioDeviceStatus(self.currentAudioDeviceID)
        log.debug(f"Initial SDL device status: {status}")

        self.channels = actualSpecs.channels

        return True

@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int)
def audio_callback(userdata, stream, length_bytes):
    instance = ctypes.cast(userdata, ctypes.POINTER(ctypes.py_object)).contents.value
    instance.set_capture_started()

    total_samples = length_bytes // ctypes.sizeof(ctypes.c_float)
    frame_count = total_samples // instance.channels

    float_ptr = ctypes.cast(stream, ctypes.POINTER(ctypes.c_float))
    samples = np.ctypeslib.as_array(float_ptr, shape=(total_samples,)).copy()

    instance.projectm_wrapper.add_pcm(samples, frame_count, channels=instance.channels)