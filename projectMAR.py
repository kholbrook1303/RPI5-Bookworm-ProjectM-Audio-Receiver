import logging
import os
import random
import re
import signal
import sys
import time

from pulsectl import Pulse, PulseVolumeInfo
from subprocess import Popen, PIPE
from threading import Thread, Event

from lib.config import Config, APP_ROOT
from lib.log import log_init
from lib.wrappers import Device, ProjectM, WaylandDisplay, XDisplay, Bluetooth

log = logging.getLogger()
    
class SignalMonitor:
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True
        
class BluetoothDevice:
    def __init__(self, device_name, mac_address):
        self.name = device_name
        self.description = None
        self.mac_address = mac_address
        self.index = None
     
# TODO: Get method to control shairport-sync
class AirPlayDevice:
    def __init__(self, device_name):
        self.name = device_name
        self.description = None
        self.index = None
            
class DeviceControl():
    def __init__(self, config):
        
        self.config = config
        
        self.thread = None
        self.thread_event = Event()
        
        self.sinks = dict()
        self.sources = dict()
        self.modules = dict()
        self.bluetooth_devices = dict()
        self.airplay_devices = dict()
        
        self.environment = self._get_environment()
        
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

        self.bth = Bluetooth()

        self.source_device = {
            'name': None,
            'type': None,
            'id': None,
            'mac': None
            }
        
        self.sink_device = None
        
        self.pa = Pulse('ProjectMAR')
        self.audio_mode = self.config.media_player['audio_mode']
        
        self.priority_sinks = [
            'hdmi'
            ]
        self.supported_sinks = [
            'alsa_output'
            ]
        self.supported_sources = [
            'alsa_input',
            'bluez_source'
            ]

    def _get_environment(self):
        with open('/boot/issue.txt', 'r') as infile:
            data = infile.read()
            for line in data.splitlines():
                if 'stage2' in line:
                    return 'lite'
                elif 'stage4' in line:
                    return 'desktop'
                
        return None
        
    def _clear_source_device(self):
        for key in self.source_device.keys():
            self.source_device[key] = None
    
    def _control_sink_device(self, sink_name, sink_channels, device, volume=1):
        log.info('Identified a new sink device: {}'.format(sink_name))
        self.sink_device = sink_name
                    
        sink_volume = PulseVolumeInfo(volume, sink_channels)
        log.debug('Setting sink {} volume to {}'.format(sink_name, sink_volume))
        self.pa.sink_volume_set(device.index, sink_volume)
                
    def _control_source_device(self, source_name, source_channels, device, device_type, volume=1):
        log.info('Identified a new source {0} device: {1} ({2})'.format(
            device_type,source_name,device.description
            ))
        
        if device_type == 'bluetooth' and self.source_device['type'] == 'bluetooth':
            log.debug('{} {} {}'.format(device_type, source_name, self.source_device))
            if self.source_device['name'] and source_name != self.source_device['name']:
                self.bth.disconnect_device(self.source_device)
        
        if not isinstance(device, BluetoothDevice):
            log.debug('Setting the source device: {}'.format(source_name))
            self.pa.default_set(device)
        
        if source_channels:
            source_volume = PulseVolumeInfo(volume, source_channels)
            log.debug('Setting source {} volume to {}'.format(source_name, source_volume))
            self.pa.source_volume_set(device.index, source_volume)
        
        if device_type == 'aux' and not source_name.startswith('bluez_source'):
            self.unload_loopback_modules()
            self.pa.module_load('module-loopback', [
                'source=' + source_name, 
                'sink=' + self.sink_device,
                'latency_msec=20'
                ])
        elif device_type == 'mic':
            self.unload_loopback_modules()

        self.source_device['name'] = source_name
        self.source_device['type'] = device_type
        if device_type == 'bluetooth':
            self.source_device['mac'] = device.mac_address
    
    """Updates the current source/sink/modules"""
    def update_devices(self):
        try:
            self.bluetooth_devices.clear()
            bth = Bluetooth()
            for mac_address, device in bth.get_connected_devices():
                log.debug('Found bluetooth device: {} ({})'.format(mac_address, device))
                self.bluetooth_devices[mac_address] = device
            
            self.sinks.clear()
            for sink in self.pa.sink_list():
                log.debug('Found sink device: {} {}'.format(sink.name, sink))
                self.sinks[sink.name] = sink
            
            self.sources.clear()
            for source in self.pa.source_list():
                log.debug('Found source device: {} {}'.format(source.name, source))
                self.sources[source.name] = source
            
            self.modules.clear()
            for module in self.pa.module_list():
                log.debug('Found module device: {} {}'.format(module.name, module))
                self.modules[module.name] = {
                    'module': module
                    }
            
                m_args = dict()
                try:
                    for key,val in re.findall(r'([^\s=]*)=(.*?)(?:\s|$)', module.argument):
                        m_args[key] = val
                    
                except TypeError:
                    pass
            
                self.modules[module.name]['argument'] = m_args
                
        except Exception as e:
            log.exception('Failed to update PulseAudio devices:')
            
    def unload_loopback_modules(self):
        for module in self.pa.module_list():
            if module.name == 'module-loopback':
                try:
                    m_args = dict()
                    for key,val in re.findall(r'([^\s=]*)=(?:\"|)(.*?)(?:\"|\s)', module.argument):
                        m_args[key] = val
                        
                    if m_args['source'].startswith('bluez_source'):
                        continue
                    
                    log.warning('Unloading module {} ({})'.format(m_args['source'], module.index))
                    self.pa.module_unload(module.index)
                except TypeError:
                    pass
            
    def control_devices(self):
        # Check for any disconnected sink devices
        if self.sink_device and self.sink_device not in self.sinks:
            log.warning('Sink device {} has been disconnected'.format(self.sink_device))
            self.unload_loopback_modules()
            self.sink_device = None
            self._clear_source_device()
        
        # Check for new sink devices
        if not self.sink_device:    
            if self.audio_mode == 'automatic':
                for sink_name in list(self.sinks.keys()):
                    if not any(sink_part in sink_name for sink_part in self.priority_sinks):
                        log.warning('Dropping sink {} as it is not in the priority list'.format(sink_name))
                        self.sinks.pop(sink_name)
                    
            for sink_name, device in self.sinks.items():
                sink_channels = len(device.volume.values)
                if self.audio_mode == 'automatic':
                    if self.sink_device == sink_name:
                        break
                    elif any(sink_name.startswith(dev) for dev in self.supported_sinks) and self.sink_device != sink_name:
                        self._control_sink_device(sink_name, sink_channels, device)
                        break
                    
                elif self.audio_mode == 'manual':
                    if self.sink_device == sink_name:
                        break
                    elif sink_name in self.config.manual['sink_devices'] and self.sink_device != sink_name:
                        self._control_sink_device(sink_name, sink_channels, device)
                        break
                else:
                    raise Exception('The specified mode \'{0}\' is invalid!'.format(self.audio_mode))
            
                
        if not self.sink_device:
            log.warning("No sink devices were found!")
            return
            
        # Check for any disconnected source devices
        if self.source_device['type'] == 'bluetooth':
            if not self.bluetooth_devices.get(self.source_device['mac']):
                log.warning('Source device {} has been disconnected'.format(self.source_device['name']))
                
                self._clear_source_device()
            
        elif self.source_device['name'] and self.source_device['name'] not in self.sources:
            log.warning('Source device {} has been disconnected'.format(self.source_device['name']))
            if self.source_device['type'] == 'aux':
                self.unload_loopback_modules()
                
            self._clear_source_device()
        
        devices_found = 0
        devices_connected = 0
        for mac_address, device_name in self.bluetooth_devices.items():
            devices_found += 1
            
            if self.source_device['name'] != device_name and devices_connected == 0:
                device = BluetoothDevice(device_name, mac_address)
                self._control_source_device(device_name, None, device, 'bluetooth')
                devices_connected += 1
                
        for source_name, device in self.sources.items():
            source_channels = len(device.volume.values)
            source_volume = device.volume.values
            
            if self.audio_mode == 'automatic':
                if not any(src in source_name for src in self.supported_sources):
                    continue
            
                devices_found += 1
            
                source_channels = len(device.volume.values)
                source_volume = device.volume.values
            
                if self.source_device['name'] != source_name and devices_connected == 0:
                    if self.config.automatic['audio_mode'] == 'bluetooth':
                        continue

                    self._control_source_device(source_name, source_channels, device, self.config.automatic['audio_mode'])
                    devices_connected += 1
                    break
                
            elif self.audio_mode == 'manual':                        
                if source_name in self.config.manual['mic_devices']:
                    devices_found += 1
                    if self.source_device['name'] != source_name and devices_connected == 0:
                        self._control_source_device(source_name, source_channels, device, 'mic', volume=.75)
                        devices_connected += 1
                        
                elif source_name in self.config.manual['aux_devices']:
                    devices_found += 1
                    if self.source_device['name'] != source_name and devices_connected == 0:
                        self._control_source_device(source_name, source_channels, device, 'aux', volume=.75)
                        devices_connected += 1
                        
            else:
                raise Exception('The specified mode \'{0}\' is invalid!'.format(self.audio_mode))
        
        if devices_found == 0:
            log.debug("No mic/aux devices detected")
            self._clear_source_device()
        
    def control(self):
        while not self.thread_event.is_set():
            try:
                if self.display_ctrl and self.config.general['projectm_enabled']:
                    self.display_ctrl.enforce_resolution()
                    
                self.update_devices()
                self.control_devices()
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
        self.thread_event.set()
        self.thread.join()
        self.pa.close()
        

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
                    log.warning('ProjectM has terminated!')
                    projectm_wrapper.thread_event.set()
                    projectm_wrapper.stop()
                    
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
