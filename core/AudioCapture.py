import logging

log = logging.getLogger()

from core.AudioCaptureImpl_SDL import AudioCaptureImpl

class AudioCapture:
    def __init__(self, config, projectm_wrapper):
        self.config = config
        self.projectm_wrapper = projectm_wrapper

        self.audio_capture_impl = AudioCaptureImpl(self.config , projectm_wrapper)
        deviceList = self.audio_capture_impl.audio_device_list()
        audioDeviceIndex = self.get_initial_audio_device_index(deviceList)

        self.output_device_list(deviceList)

        self.audio_capture_impl.start_recording(audioDeviceIndex)

    def __del__(self):
        if self.audio_capture_impl:
            self.audio_capture_impl.stop_recording()
            self.audio_capture_impl = None

    def output_device_list(self, deviceList):
        log.info(f'Available audio capturing devices:')

        for device in deviceList:
            log.info(f' - {device}: {deviceList[device]}')

    def get_initial_audio_device_index(self, deviceList):
        audioDeviceIndex = -1

        for idx, dev in deviceList.items():
            if 'ProjectMAR-NULL-Sink' in str(dev):
                audioDeviceIndex = idx

        try:
            if not deviceList.get(audioDeviceIndex):
                audioDeviceIndex = -1
        except Exception as ex:
            log.error(f'audioDeviceIndex "{audioDeviceIndex}" does not exist')

        return audioDeviceIndex

    def next_audio_device(self):
        self.audio_capture_impl.next_audio_device()