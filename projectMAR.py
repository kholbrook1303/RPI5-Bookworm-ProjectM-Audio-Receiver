import logging
import os
import signal
import subprocess
import sys
import time

from copy import deepcopy
from threading import Thread, Event

from lib.config import Config, APP_ROOT
from lib.log import log_init
from lib.controllers import AirPlayDevice, BluetoothDevice, PlexAmpDevice
from lib.controllers import Audio, Bluetooth, ProjectM, WaylandDisplay, XDisplay

log = logging.getLogger()
    
class SignalMonitor:
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True
            
class DeviceControl():
    def __init__(self, config):
            
        self.audio                  = Audio()
        self.bluetooth              = Bluetooth()
        self.thread                 = None
        self.thread_event           = Event()
        
        self.config                 = config
        self.audio_mode             = self.config.media_player['audio_mode']
        self.allow_multiple_sinks   = self.config.media_player['allow_multiple_sinks']
        self.devices                = deepcopy(self.audio.device_template)
        self.environment            = self._get_environment()
        self.processes              = self._get_processes()
        self.sink_device            = None
        self.source_device          = None
        
        self.display_ctrl = None
        if self.environment == 'desktop':
            display_method = None
            display_type = os.environ['XDG_SESSION_TYPE']
            log.info('Identified display type: {}'.format(display_type))
            
            if display_type == 'x11':
                display_method = XDisplay
            
            elif display_type == 'wayland':
                display_method = WaylandDisplay
                
            else:
                raise Exception('Display type {} is not currently supported!'.format(display_type))
            
            self.display_ctrl = display_method(
                self.config.general['resolution'],
                self.environment
                )

    def _get_environment(self):
        with open('/boot/issue.txt', 'r') as infile:
            data = infile.read()
            for line in data.splitlines():
                if 'stage2' in line:
                    return 'lite'
                elif 'stage4' in line:
                    return 'desktop'
                
        return None

    def _get_processes(self):
        process = subprocess.Popen(['ps', '-ax'], stdout=subprocess.PIPE)
        stdout = process.stdout.readlines()
        headers = [h for h in ' '.join(stdout[0].decode('UTF-8').strip().split()).split() if h]
        raw_data = map(lambda s: s.decode('UTF-8').strip().split(None, len(headers) - 1), stdout[1:])
        return {r[0]:dict(zip(headers, r)) for r in raw_data}
    
    def _control_sink_device(self, sink_name, sink_channels, sink_device, sink_volume=.75):
        log.info('Identified a new sink device: {}'.format(sink_name))
        self.audio.pulse.sink_default_set(sink_name)
        self.audio.set_sink_volume(sink_device, sink_name, sink_channels, sink_volume)
                
    def _control_source_device(self, source_name, source_device, source_volume):
        log.info('Identified a new {} {} source device: {} ({})'.format(
            source_device.device, source_device.type, source_name, source_device.description
            ))

        source_channels = None
        try:
            source_channels = len(source_device.volume.values)
            if source_channels:
                self.audio.set_source_volume(source_device, source_name, source_channels, source_volume)

        except:
            pass
        
        if source_device.type == 'aux' and source_device.device == 'pa':
            self.audio.unload_loopback_modules(source_name=source_name)

            log.info('Loading module-loopback for {}'.format(source_name))
            self.audio.pulse.module_load('module-loopback', [
                'source=' + source_name,
                'sink=' + self.sink_device,
                'latency_msec=20'
                ])
            
    def _control_devices(self):
        sinks               = list()
        total_sinks         = 0
        total_new_sinks     = 0
        total_active_sinks  = 0

        # Check for any disconnected sink devices
        current_devices = self.audio.get_active_devices(self.processes)
        for sink_name in list(self.devices['sinks']):
            if not current_devices['sinks'].get(sink_name):
                log.warning('Sink device {} has been disconnected'.format(sink_name))
                self.audio.unload_loopback_modules(sink_name=sink_name)
                if sink_name == self.sink_device:
                    self.sink_device = None
        
        # Check for new sink devices
        for sink_name, sink_device in current_devices['sinks'].items():
            total_sinks += 1

            # Check to see if the device is already being managed
            if self.devices['sinks'].get(sink_name, False):
                total_active_sinks += 1
                sinks.append(sink_name)
                continue
            
            control_sink = False
            sink_channels = len(sink_device.volume.values)
            if self.audio_mode == 'automatic':
                output_device = self.config.automatic['output_device']
                if output_device and sink_device.device != output_device:
                    log.warning('Skipping sink {} as it is not {}'.format(sink_name, output_device))
                    continue
                
                control_sink = True

            elif self.audio_mode == 'manual':
                if sink_name in self.config.manual['sink_devices']:
                    control_sink = True

            else:
                raise Exception('The specified mode \'{0}\' is invalid!'.format(self.audio_mode))

            if control_sink:
                total_new_sinks += 1
                sinks.append(sink_name)
                self.sink_device = sink_name
                self._control_sink_device(sink_name, sink_channels, sink_device)

                if not self.allow_multiple_sinks:
                    break

        # Exit function if no sinks are identified (Nothing to do)
        if total_sinks == 0:
            log.warning("No sink devices were found!")
            return
           
        # Handle multiple sinks if enabled
        if (total_active_sinks + total_new_sinks) >= 2 and total_new_sinks > 0:
            unloaded = True
            if current_devices['modules'].get('module-combine-sink'):
                log.info('Found an active module-combined-sink module loaded!')
                unloaded = self.audio.unload_combined_sink_modules()

            if unloaded:
                log.info('Loading combined sink for {}'.format(sinks))
                self.audio.pulse.module_load('module-combine-sink', [
                    'slaves=' + ','.join(sinks)
                    ])
                self.audio.pulse.sink_default_set('combined')
                self.sink_device = 'combined'
        elif (total_active_sinks + total_new_sinks) <= 1:
            if self.audio.unload_combined_sink_modules():
                current_devices['modules'].pop('module-combine-sink')

        # Check for any disconnected source devices
        for source_name in list(self.devices['sources']):
            if not current_devices['sources'].get(source_name):
                log.warning('Source device {} has been disconnected'.format(source_name))
                if isinstance(self.devices['sources'][source_name], BluetoothDevice):
                    continue
                elif self.devices['sources'][source_name].type == 'aux':
                    self.audio.unload_loopback_modules(source_name=source_name)
                if source_name == self.source_device:
                    self.source_device = None
                    
        devices_found = 0
        devices_connected = 0
        for source_name, source_device in current_devices['sources'].items():
            devices_found += 1
            if self.devices['sources'].get(source_name, False):
                continue
                
            source_volume = .75
            control_source = False
            if isinstance(source_device, BluetoothDevice):
                control_source = True

            elif isinstance(source_device, AirPlayDevice):
                control_source = True

            elif isinstance(source_device, PlexAmpDevice):
                control_source = True

            elif self.audio_mode == 'automatic':
                input_mode = self.config.automatic['input_mode']
                if input_mode and source_device.type != input_mode:
                    log.warning('Skipping source {} as it is not {}'.format(source_name, input_mode))
                    continue

                control_source = True

            elif self.audio_mode == 'manual':
                if source_device.type == 'mic' and source_name in self.config.manual['mic_devices']:
                    control_source = True

                elif source_device.type == 'aux' and source_name in self.config.manual['aux_devices']:
                    control_source = True

            else:
                raise Exception('The specified mode \'{0}\' is invalid!'.format(self.audio_mode))

            if control_source:
                devices_connected += 1
                self.source_device = source_name
                self._control_source_device(
                    source_name, 
                    source_device, 
                    source_volume
                    )

        if devices_found == 0:
            log.warning("No mic/aux devices detected")

        self.devices = current_devices
        
    def control(self):
        while not self.thread_event.is_set():
            try:
                if self.display_ctrl and self.config.general['projectm_enabled']:
                    self.display_ctrl.enforce_resolution()

                self._control_devices()
            except Exception as e:
                log.exception('Device control failed!')
                
            time.sleep(5)
        
    def start(self):
        # self.kill_prior_instances()

        self.thread = Thread(
            target=self.control,
            args=(),
            daemon=True
            )
        self.thread.start()
    
    def stop(self):
        # Unload any modules created by ProjectMAR
        self.audio.unload_combined_sink_modules()
        for name, device in self.devices['sources'].items():
            if device.type == 'aux':
                self.audio.unload_loopback_modules(source_name=name)

        self.audio.close()

        self.thread_event.set()
        self.thread.join()
        

def main():
    config_path = os.path.join(APP_ROOT, 'projectMAR.conf')
    print (config_path)
    config = Config(config_path)
    
    logpath = os.path.join(APP_ROOT, 'projectMAR.log')
    log_init(logpath, config.general['log_level'])
    log_init('console', config.general['log_level'])
    
    sm = SignalMonitor()
    
    log.info('Initializing projectMAR System Control in {0} mode...'.format(
        config.media_player['audio_mode']
        ))
    device_ctrl = DeviceControl(config)
    device_ctrl.start()
    
    if config.general['projectm_enabled']:
        log.info('Initializing projectMSDL Wrapper...')
        projectm_wrapper = ProjectM(config, device_ctrl)
    
        log.info('Executing ProjectMSDL and monitorring presets for hangs...')
        projectm_wrapper.execute()
    
    while not sm.exit:
        try:
            if config.general['projectm_enabled']:
                if projectm_wrapper.projectm_process.poll() != None:
                    log.warning(
                        'ProjectM has exited with return code {}'.format(
                            projectm_wrapper.projectm_process.returncode
                            ))
                    projectm_wrapper.thread_event.set()
                    projectm_wrapper.stop()

                    if not config.general['projectm_restore']:
                        log.warning('Stopping ProjectMAR due to ProjectMDSL exit')
                        break

                    else:
                        log.info('Executing ProjectMSDL and monitorring presets for hangs...')
                        projectm_wrapper.execute()
            
            time.sleep(1)
        except KeyboardInterrupt:
            log.warning('User initiated keyboard exit')
            break
        except:
            log.exception('projectMAR failed!')
            
    log.info('Closing down all threads/processes...')
    
    if config.general['projectm_enabled']:
        projectm_wrapper.thread_event.set()
        projectm_wrapper.stop()
        
    device_ctrl.stop()
            
    log.info('Exiting ProjectMAR!')
    sys.exit(0)

if __name__ == "__main__":
    main()
