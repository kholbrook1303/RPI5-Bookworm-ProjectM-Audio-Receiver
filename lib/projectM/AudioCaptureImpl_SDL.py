import sdl2
import ctypes
import logging
import numpy as np

log = logging.getLogger()

class SDLAudioCapture:
    def __init__(self, config, projectm_wrapper, sample_rate=44100, channels=2, samples=1024):
        self.projectm_wrapper = projectm_wrapper

        self._currentAudioDeviceIndex = -1
        self._currentAudioDeviceID = 0
        self._channels = channels
        
        self._requestedSampleFrequency = sample_rate
        self._requestedSampleCount = sample_rate / config.projectm.get('projectm.fps', 60)

        sdl2.SDL_SetHint(sdl2.SDL_HINT_AUDIO_INCLUDE_MONITORS, b"1")
        sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO)

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

    def start_recording(self, index):
        self._currentAudioDeviceIndex = index

        try:
            if self.open_audio_device():
                sdl2.SDL_PauseAudioDevice(self._currentAudioDeviceID, False)
        except:
            log.exception('Failed to start recording!')

    def stop_recording(self):
        if self._currentAudioDeviceID:
            sdl2.SDL_PauseAudioDevice(self._currentAudioDeviceID, True)
            sdl2.SDL_CloseAudioDevice(self._currentAudioDeviceID)
            self._currentAudioDeviceID = 0

    def set_audio_device_index(self, index):
        if index > 1 and index < sdl2.SDL_GetNumAudioDevices(True):
            self._currentAudioDeviceID = index
            self.start_recording()

    def get_audio_device_index(self):
        return self._currentAudioDeviceID

    def open_audio_device(self):
        self.user_data = ctypes.py_object(self)
        user_data_ptr = ctypes.cast(ctypes.pointer(self.user_data), ctypes.c_void_p)

        requestedSpecs = sdl2.SDL_AudioSpec(
            self._requestedSampleFrequency, 
            sdl2.AUDIO_F32SYS, 
            self._channels, 
            int(self._requestedSampleCount),
            audio_callback,
            user_data_ptr
            )

        actualSpecs = sdl2.SDL_AudioSpec(
            freq=0,
            aformat=0,
            channels=0,
            samples=0            
            )

        deviceName = sdl2.SDL_GetAudioDeviceName(self._currentAudioDeviceIndex, True)
        self._currentAudioDeviceID  = sdl2.SDL_OpenAudioDevice(
            deviceName, True, 
            requestedSpecs, 
            actualSpecs, 
            sdl2.SDL_AUDIO_ALLOW_CHANNELS_CHANGE
            )

        if self._currentAudioDeviceID == 0:
            log.error(f'Failed to open audio device "{deviceName}" (ID {self._currentAudioDeviceIndex}): {sdl2.SDL_GetError()}')
            return False

        self._channels = actualSpecs.channels

        log.info(f'Opened audio recording device "{deviceName}" (ID {self._currentAudioDeviceIndex}) with {actualSpecs.channels} channels at {actualSpecs.freq} Hz')

        return True

    def uninitialize(self):
        self.stop_recording()
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_AUDIO)

@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int)
def audio_callback(userdata, stream, length_bytes):
    instance = ctypes.cast(userdata, ctypes.POINTER(ctypes.py_object)).contents.value

    length  = length_bytes // ctypes.sizeof(ctypes.c_float)
    float_ptr = ctypes.cast(stream, ctypes.POINTER(ctypes.c_float))
    samples = np.ctypeslib.as_array(float_ptr, shape=(length,)).copy()

    instance.projectm_wrapper.add_pcm(samples, channels=2)