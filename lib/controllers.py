import logging
import os
import random
import re
import time
from tkinter import CURRENT

from pulsectl import Pulse, PulseVolumeInfo
from pulsectl.pulsectl import PulseOperationFailed
from threading import Event, Thread

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config

log = logging.getLogger()

class BluetoothDevice:
    def __init__(self, device_name, mac_address):
        self.name           = device_name
        self.description    = None
        self.mac_address    = mac_address
        self.index          = None
        self.active         = False
        self.device         = 'bluetooth'
        self.type           = 'aux'
        self.meta           = None

class PlexAmpDevice:
    def __init__(self, device_name, index, meta):
        self.name           = device_name
        self.description    = None
        self.index          = index
        self.active         = False
        self.device         = 'plexamp'
        self.type           = 'aux'
        self.meta           = meta
     
class AirPlayDevice:
    def __init__(self, device_name, index, meta):
        self.name           = device_name
        self.description    = None
        self.index          = index
        self.active         = False
        self.device         = 'airplay'
        self.type           = 'aux'
        self.meta           = meta

class DeviceCatalog:
    def __init__(self):
        self.modules                = dict()
        self.sink_cards             = dict()
        self.sink_devices           = dict()
        self.source_devices         = dict()
        self.bluetooth_devices      = dict()
        self.plugin_devices         = dict()
        self.unsupported_sinks      = dict()
        self.unsupported_sources    = dict()

class Audio(Controller):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        self.audio_mode             = self.config.audio_receiver['audio_mode']
        self.io_device_mode         = self.config.audio_receiver['io_device_mode']
        self.allow_multiple_sinks   = self.config.audio_receiver['allow_multiple_sinks']
        self.allow_multiple_sources = self.config.audio_receiver['allow_multiple_sources']
        self.sink_device            = None
        self.source_device          = None
        
        self.devices                = DeviceCatalog()

        self.pulse = Pulse()

    def get_module_arguments(self, module):
        module_args = dict()
        try:
            for key,val in re.findall(r'([^\s=]*)=(.*?)(?:\s|$)', module.argument):
                module_args[key] = val
                    
        except TypeError:
            pass

        return module_args

    def get_modules(self, module_name):
        modules = list()

        try:
            for module in self.pulse.module_list():
                if module.name == module_name:
                    modules.append(module)
        except:
            pass

        return modules

    def module_loaded(self, module_name):
        modules = self.get_modules(module_name)
        if len(modules) > 0:
            return True

        return False
            
    def unload_loopback_modules(self, sink_name=None, source_name=None):
        for module in self.get_modules('module-loopback'):
            module_args = self.get_module_arguments(module)
            
            unload = False
            if not source_name and not sink_name:
                unload = True
            elif sink_name and module_args.get('sink', None) == sink_name:
                unload = True
            elif source_name and module_args.get('source', None) == source_name:
                unload = True
            else:
                log.warning('unable to unload loopback module {}'.format(module.__dict__))

            if unload:
                log.info('Unloading loopback module {}'.format(module.name))
                self.pulse.module_unload(module.index)

    def load_loopback_module(self, source_name, sink_name):
        log.info('Loading module-loopback for source {} sink {}'.format(source_name, sink_name))
        self.pulse.module_load('module-loopback', [
            'source=' + source_name,
            'sink=' + sink_name,
            'latency_msec=20',
            'source_dont_move=true',
            'sink_dont_move=true'
            ])

    def unload_combined_sink_modules(self):
        for module in self.get_modules('module-combine-sink'):
            log.info('Unloading combined sink {}'.format(module.name))
            self.pulse.module_unload(module.index)

    def load_combined_sinks(self, combined_sinks):
        log.info('Loading combined sink for {}'.format(combined_sinks))
        self.pulse.module_load('module-combine-sink', [
            'slaves=' + ','.join(combined_sinks)
            ])

    def update_plugin_devices(self):
        plugins = self.pulse.sink_input_list()

        # Check for any disconnected plugin devices
        for plugin_name in list(self.devices.plugin_devices):
            disconnected = True
            for plugin in plugins:
                if plugin.proplist.get('application.process.binary'):
                    app = plugin.proplist['application.process.binary']
                    if plugin_name == app:
                        disconnected = False
            if disconnected:
                log.warning('Plugin device {} has been disconnected'.format(plugin_name))
                self.devices.plugin_devices.pop(plugin_name)

        for plugin in plugins:
            if plugin.proplist.get('application.process.binary'):
                app = plugin.proplist['application.process.binary']
                if not self.devices.plugin_devices.get(app):
                    plugin_device = None
                    if app == 'node':
                        plugin_device = PlexAmpDevice(app, plugin.index, plugin)
                    elif app == 'shairport-sync':
                        plugin_device = AirPlayDevice(app, plugin.index, plugin)

                    if not plugin_device:
                        log.warning('Unable to identify plugin device: {}'.format(plugin.__dict__))
                        continue

                    log.info('Found plugin device: {} {}'.format(plugin_device.name, plugin_device.device))
                    self.devices.plugin_devices[app] = plugin_device

    def update_bluetooth_devices(self):
        bluetooth_devices = list()

        bth = Bluetooth()
        for mac_address, device_name in bth.get_connected_devices():
            bluetooth_device = BluetoothDevice(device_name, mac_address)
            bluetooth_devices.append(bluetooth_device)
            
        # Check for any disconnected bluetooth devices
        for bluetooth_name in list(self.devices.bluetooth_devices):
            if not any(bth_device.name == bluetooth_name for bth_device in bluetooth_devices):
                log.warning('Plugin device {} has been disconnected'.format(bluetooth_name))
                self.devices.bluetooth_devices.pop(bluetooth_name)

        for bluetooth_device in bluetooth_devices:
            if self.devices.bluetooth_devices.get(bluetooth_device.name):
                continue

            log.info('Found bluetooth device: {} {}'.format(bluetooth_device.name, bluetooth_device))
            self.devices.bluetooth_devices[bluetooth_device.name] = bluetooth_device

    def set_sink_volume(self, sink_device, sink_channels, sink_volume):
        sink_volume = PulseVolumeInfo(sink_volume, sink_channels)
        log.info('Setting sink {} volume to {}'.format(sink_device.name, sink_volume))
        self.pulse.sink_volume_set(sink_device.index, sink_volume)

    def update_sink_devices(self):
        sinks = self.pulse.sink_list()

        # Check for any disconnected sink devices
        for sink_name in list(self.devices.sink_devices):
            if not any (sink_name == sink.name for sink in sinks):
                log.warning('Sink device {} has been disconnected'.format(sink_name))
                self.unload_loopback_modules(sink_name=sink_name)

                sink_device = self.devices.sink_devices[sink_name]
                if sink_device.proplist.get('alsa.card') and sink_device.proplist.get('alsa.long_card_name'):
                    alsa_card = sink_device.proplist['alsa.card']
                    alsa_name = sink_device.proplist['alsa.long_card_name']

                    if self.devices.sink_cards.get(alsa_card):
                        self.devices.sink_cards.pop(alsa_card)
                    
                self.devices.sink_devices.pop(sink_name)
                if sink_name == self.sink_device:
                    self.sink_device = None

        for sink in sinks:
            if self.devices.sink_devices.get(sink.name):
                continue
            elif self.devices.unsupported_sinks.get(sink.name):
                continue

            log.debug('Found sink device: {} {}'.format(sink.name, sink))
            if sink.name == 'combined':
                log.debug('Sink device: {} is not supported'.format(sink.name))
                self.devices.unsupported_sinks[sink.name] = sink
                
                sink_volume = None
                if self.audio_mode == 'automatic':
                    sink_volume = self.config.automatic.get('sink_device_volume', 1.0)
                elif self.audio == 'manual':
                    sink_volume = self.config.manual.get('combined_sink_volume', 1.0)

                if not isinstance(sink_volume, float):
                    log.warning('Combined sink requires a float object')
                    sink_volume = 1.0

                sink_channels = len(sink.volume.values)
                self.set_sink_volume(sink, sink_channels, sink_volume)
                continue

            sink_type = None
            if 'Built-in Audio' in sink.description:
                sink_type = 'internal'
            else:
                sink_type = 'external'

            if sink.proplist.get('alsa.card') and sink.proplist.get('alsa.long_card_name'):
                alsa_card = sink.proplist['alsa.card']
                alsa_name = sink.proplist['alsa.long_card_name']
                log.debug('Identified sink ALSA card {} {}'.format(alsa_name, alsa_card))

                if not self.devices.sink_cards.get(alsa_card):
                    self.devices.sink_cards[alsa_card] = alsa_name

            sink.active = False
            sink.type = sink_type
            sink.device = 'pa'
            self.devices.sink_devices[sink.name] = sink
    
    def control_sink_device(self, sink_channels, sink_device, sink_volume):
        log.info('Identified a new sink device: {}'.format(sink_device.name))
        self.pulse.sink_default_set(sink_device.name)
        self.set_sink_volume(sink_device, sink_channels, sink_volume)

    def get_supported_sink_devices(self):
        if self.audio_mode == 'automatic':
            for sink_name, sink_device in self.devices.sink_devices.items():
                if sink_device.active:
                    continue

                sink_device_type = self.config.automatic['sink_device_type']
                if sink_device_type and sink_device.type != sink_device_type:
                    log.debug('Skipping sink {} as it is not {}'.format(sink_name, sink_device_type))
                    continue

                sink_volume = self.config.automatic.get('sink_device_volume', 1.0)
                if not isinstance(sink_volume, float):
                    log.warning('Sink {} does not have a float value for volume'.format(sink_name))
                    sink_volume = 1.0
                    
                supported_sink = {
                    'device': sink_device,
                    'volume': sink_volume
                    }

                yield supported_sink

        elif self.audio_mode == 'manual':
            for sink_id in self.config.manual['sink_devices']:
                sink_meta = getattr(self.config, sink_id)
                sink_name = sink_meta['name']
                if not sink_name:
                    log.warning('Sink {} is missing a name'.format(sink_id))
                    continue

                if self.devices.sink_devices.get(sink_name):
                    sink_device = self.devices.sink_devices[sink_name]
                    if sink_device.active:
                        continue

                    sink_device_type = sink_meta['type']
                    if sink_device_type and sink_device.type != sink_device_type:
                        log.debug('Skipping sink {} as it is not {}'.format(sink_device, sink_device_type))
                        continue
                    
                sink_volume = sink_meta.get('volume', 1.0)
                if not isinstance(sink_volume, float):
                    log.warning('Sink {} does not have a float value for volume'.format(sink_name))
                    sink_volume = 1.0
                    
                supported_sink = {
                    'device': sink_device,
                    'volume': sink_volume
                    }

                yield supported_sink

    def update_source_devices(self):
        sources = self.pulse.source_list()

        # Check for any disconnected source devices
        for source_name in list(self.devices.source_devices):
            if not any (source_name == source.name for source in sources):
                log.warning('Source device {} {} has been disconnected'.format(source_name, self.devices.source_devices[source_name].type))
                if self.devices.source_devices[source_name].type == 'aux' and not source_name.startswith('bluez_source'):
                    self.unload_loopback_modules(source_name=source_name)
                if source_name == self.source_device:
                    self.source_device = None
                self.devices.source_devices.pop(source_name)

        for source in sources:
            if self.devices.source_devices.get(source.name):
                continue
            elif self.devices.unsupported_sources.get(source.name):
                continue

            log.debug('Found source device: {} {}'.format(source.name, source))
            if source.name.startswith('alsa_output'):
                log.debug('Source device: {} is not supported'.format(source.name))
                self.devices.unsupported_sources[source.name] = source
                continue

            if source.name == 'combined.monitor':
                log.debug('Source device: {} is not supported'.format(source.name))
                self.devices.unsupported_sources[source.name] = source
                continue

            source_type = None
            if any('mic' in port.name or 'Microphone' in port.description for port in source.port_list):
                source_type = 'mic'
            else:
                source_type = 'aux'

            if source.proplist.get('alsa.card') and source.proplist.get('alsa.long_card_name'):
                alsa_card = source.proplist['alsa.card']
                alsa_name = source.proplist['alsa.long_card_name']
                log.debug('Found Source ALSA card {} {}'.format(alsa_name, alsa_card))

                if self.devices.sink_cards.get(alsa_card):
                    if self.devices.sink_cards[alsa_card] == alsa_name:
                        if self.io_device_mode:
                            source_type = self.io_device_mode

            source.active = False
            source.type = source_type
            source.device = 'pa'
            self.devices.source_devices[source.name] = source

    def set_source_volume(self, source_device, source_channels, volume):
        source_volume = PulseVolumeInfo(volume, source_channels)
        log.info('Setting source {} volume to {}'.format(source_device.name, source_volume))
        self.pulse.source_volume_set(source_device.index, source_volume)
                
    def control_source_device(self, source_device, source_volume):
        log.info('Identified a new {} {} source device: {} ({})'.format(
            source_device.device, source_device.type, source_device.name, source_device.description
            ))

        source_channels = 0
        try:
            source_channels = len(source_device.volume.values)
        except:
            pass

        if source_channels > 0:
            self.set_source_volume(source_device, source_channels, source_volume)
        
        loopback_modules = self.get_modules('module-loopback')
        if self.sink_device and source_device.type == 'aux' and not source_device.name.startswith('bluez_source'):
            if len(loopback_modules) > 0:
                self.unload_loopback_modules(source_name=source_device.name)

            for sink in self.devices.sink_devices.values():
                if not sink.active:
                    continue
                
                self.load_loopback_module(source_device.name, sink.name)

    def get_supported_source_devices(self):
        if self.audio_mode == 'automatic':
            for source_name, source_device in self.devices.source_devices.items():
                if source_device.active:
                    continue

                source_device_type = self.config.automatic['source_device_type']
                if source_device_type and source_device.type != source_device_type:
                    log.debug('Skipping source {} as it is not {}'.format(source_name, source_device_type))
                    continue

                source_volume = self.config.automatic.get('source_device_volume', .85)
                if not isinstance(source_volume, float):
                    log.warning('Source {} does not have a float value for volume'.format(source_name))
                    source_volume = .85
                    
                supported_source = {
                    'device': source_device,
                    'volume': source_volume
                    }

                yield supported_source

        elif self.audio_mode == 'manual':
            for source_id in self.config.manual['source_devices']:
                source_meta = getattr(self.config, source_id)
                source_name = source_meta['name']
                if not source_name:
                    continue

                if self.devices.source_devices.get(source_name):
                    source_device = self.devices.source_devices[source_name]
                    if source_device.active:
                        continue

                    source_device_type = source_meta['type']
                    if source_device_type and source_device.type != source_device_type:
                        log.debug('Skipping source {} as it is not {}'.format(source_name, source_device_type))
                        continue

                    source_volume = source_meta.get('volume', .85)
                    if not isinstance(source_volume, float):
                        log.warning('Source {} does not have a float value for volume'.format(source_name))
                        source_volume = .85
                    
                    supported_source = {
                        'device': source_device,
                        'volume': source_volume
                        }

                    yield supported_source

    def handle_devices(self):
        try:
            self.update_sink_devices()
            self.update_source_devices()
            self.update_bluetooth_devices()
            self.update_plugin_devices()

            active_sinks = list()
            for sink_device in self.devices.sink_devices.values():
                if sink_device.active:
                    active_sinks.append(sink_device)
        
            inactive_sinks = list()
            for supported_sink in self.get_supported_sink_devices():
                inactive_sinks.append(supported_sink)

            total_sinks = len(active_sinks) + len(inactive_sinks)
            if self.allow_multiple_sinks and total_sinks > 1 and len(inactive_sinks) > 0:
                if self.module_loaded('module-combine-sink'):
                    log.info('Found an active module-combined-sink module loaded!')
                    self.unload_combined_sink_modules()

                combined_sinks = list()
                for sink_device in active_sinks:
                    combined_sinks.append(sink_device.name)
                for supported_sink in inactive_sinks:
                    supported_sink['device'].active = True
                    combined_sinks.append(supported_sink['device'].name)

                self.load_combined_sinks(combined_sinks)
                self.pulse.sink_default_set('combined')
                self.sink_device = 'combined'

            elif not self.allow_multiple_sinks and len(active_sinks) > 0:
                pass
            else:
                if self.allow_multiple_sinks and total_sinks <= 1 and self.module_loaded('module-combine-sink'):
                    self.unload_combined_sink_modules()

                for supported_sink in inactive_sinks:
                    sink_device = supported_sink['device']
                    sink_volume = supported_sink['volume']

                    sink_channels = len(sink_device.volume.values)
                    self.sink_device = sink_device.name
                    self.control_sink_device(sink_channels, sink_device, sink_volume)
                    self.devices.sink_devices[sink_device.name].active = True

                    if not self.allow_multiple_sinks:
                        break

            if total_sinks == 0:
                log.debug("No sink devices were found!")

            active_sources = list()
            for source_device in self.devices.source_devices.values():
                if source_device.active:
                    active_sources.append(source_device)
        
            inactive_sources = list()
            for supported_source in self.get_supported_source_devices():
                inactive_sources.append(supported_source)

            total_sources = len(active_sources) + len(inactive_sources)

            if total_sources == 0:
                log.debug("No mic/aux devices detected")
                pass
            elif not self.allow_multiple_sources and len(active_sources) > 0:
                pass
            else:
                for supported_source in inactive_sources:
                    source_device = supported_source['device']
                    source_volume = supported_source['volume']

                    self.source_device = source_device.name
                    self.control_source_device(
                        source_device, 
                        source_volume
                        )
                    self.devices.source_devices[source_device.name].active = True

                    if not self.allow_multiple_sources:
                        break

        except PulseOperationFailed:
            log.error('Failed to handle Pulseaudio devices... Restarting Pulseaudio')
            self.pulse = Pulse()

        except Exception as e:
            log.exception('Failed to handle Pulseaudio devices!')

    def close(self):
        self.unload_combined_sink_modules()

        for source_name, source_device in self.devices.source_devices.items():
            if not source_device.active:
                continue

            if source_device.type == 'aux' and not source_name.startswith('bluez_source'):
                self.unload_loopback_modules(source_name=source_name)

        self.pulse.close()

class ProjectM(Controller):
    def __init__(self, config, control, thread_event):
        super().__init__()
        
        self.config = config
        self.control = control
        
        self.projectm_path = self.config.projectm['path']
        self.projectm_process = None
        
        config_path = os.path.join(self.projectm_path, 'projectMSDL.properties')
        self.projectm_config = Config(config_path, config_header='[projectm]')
        
        self.threads = list()
        self.thread_event = thread_event
        
        self.preset_start = 0
        self.preset_shuffle = self.projectm_config.projectm['projectm.shuffleenabled']
        self.preset_display_duration = self.projectm_config.projectm['projectm.displayduration']
        self.preset_path = self.projectm_config.projectm['projectm.presetpath'].replace(
            '${application.dir}', self.projectm_path
            )
        self.preset_screenshot_index = 0
        self.preset_screenshot_path = os.path.join(self.projectm_path, 'preset_screenshots')
        if not os.path.exists(self.preset_screenshot_path):
            os.makedirs(self.preset_screenshot_path)
            
    def _take_screenshot(self, preset):
        preset_name = os.path.splitext(preset)[0]
        preset_name_filtered = preset_name.split(' ', 1)[1]
        preset_screenshot_name = preset_name_filtered + '.png'
        if not preset_screenshot_name in os.listdir(self.preset_screenshot_path):
            if self.preset_screenshot_index > 0:
                time.sleep(self.projectm_config.projectm['projectm.transitionduration'])
                log.info('Taking a screenshot of {0}'.format(preset))
                screenshot_path = os.path.join(self.preset_screenshot_path, preset_screenshot_name)
                self._execute_managed(['grim', screenshot_path])
                            
            self.preset_screenshot_index += 1
                    
    def _monitor_output(self):
        preset_regex = r'Displaying preset: (?P<name>.*)$'
        for line in self._read_stderr(self.projectm_process):
            log.debug('ProjectM Output: {0}'.format(line))
            
            try:
                match = re.search(preset_regex, line, re.I)
                if match:
                    preset = match.group('name').rsplit('/', 1)[1]
                
                    log.info('Currently displaying preset: {0}'.format(preset))
                    self.preset_start = time.time()
                
                    # Take a preview screenshot
                    if self.control.environment == 'desktop':
                        if self.config.projectm['screenshots_enabled'] and self.control.audio.source_device:
                            self._take_screenshot(preset)
            except:
                log.exception('Failed to process output')
            
    def _monitor_hang(self):
        while not self.thread_event.is_set():
            if self.preset_start == 0:
                continue
            else:
                duration = time.time() - self.preset_start
                if duration >= (self.preset_display_duration + 5):
                    log.warning('The visualization has not changed in the alloted timeout!')
                    log.info('Manually transitioning to the next visualization...')
                    xautomation_process = self._execute(['xte'])
                    xautomation_process.communicate(input=b'key n\n')
                
            time.sleep(1)
            
    def _manage_playlist(self):
        if self.config.projectm['advanced_shuffle'] == True:
            log.info('Performing smart randomization on presets...')
            presets = list()
            for root, dirs, files in os.walk(self.preset_path):
                for name in files:
                    preset_path = os.path.join(root, name)
                    if not preset_path in presets:
                        presets.append(preset_path)
                        
            random.shuffle(presets)
            index = 0
            for preset in presets:
                index += 1
                idx_pad = format(index, '06')
                preset_root, preset_name = preset.rsplit('/', 1)
                if not re.match(r'^\d{6}\s.*?\.milk', preset_name, re.I):
                    preset_name_stripped = preset_name
                else:
                    preset_name_stripped = preset_name.split(' ', 1)[1]
                
                dst = os.path.join(preset_root, idx_pad + ' ' + preset_name_stripped)
                log.debug('Renaming {0} to {1}'.format(preset, dst))
                try:
                    os.rename(preset, dst)
                except Exception as e:
                    log.error('Failed to rename preset {0}: {1}'.format(preset, e))
                
        
    def execute(self, beatSensitivity=2.0):   
        self._manage_playlist()
    
        app_path = os.path.join(APP_ROOT, 'projectMSDL')
        self.projectm_process = self._execute(
            [app_path, '--beatSensitivity=' + str(beatSensitivity)]
            )
        
        # Start thread to monitor preset output to ensure
        # there are no hangs (TODO: Report to ProjectM)
        monitor_thread = Thread(
            target=self._monitor_output,
            )
        monitor_thread.daemon = True
        monitor_thread.start()
        self.threads.append(monitor_thread)
        
        # Start thread to trigger the next preset 
        # in the event of a hang
        hang_thread = Thread(
            target=self._monitor_hang,
            )
        hang_thread.daemon = True
        hang_thread.start()
        self.threads.append(hang_thread)
        
    def stop(self):
        for thread in self.threads:
            thread.join()
            
        self.projectm_process.kill()

class Device(Controller):
    def __init__(self):
        super().__init__()
        
    def get_display_type(self):
        session_type = self._execute(['echo %XDG_SESSION_TYPE'], shell=True)
        for line in self._read_stdout(session_type):
            return line
        
        raise Exception("Failed to get the XDG_SESSION_TYPE variable!")
    
    def kill_process_by_name(self, process_name):
        pgrep = self._execute(['pgrep', '-f', process_name])
        for line in self._read_stdout(pgrep):
            self.kill_process_by_name(process_name)
    
    def kill_process_pid(self, pid):
        log.info('Killing process {}...'.format(pid))
        self._execute_managed(['sudo', 'kill', pid])
    
    def kill_process_name(self, process_name):
        log.info('Killing process {}...'.format(process_name))
        self._execute_managed(['sudo', 'killall',  process_name])

class Bluetooth(Controller):
    def __init__(self):
        super().__init__()
        
    def get_connected_devices(self):
        bluetoothctl =  self._execute(['bluetoothctl', 'devices', 'Connected'])
        for line in self._read_stdout(bluetoothctl):
            log.debug('bluetoothctl output: {}'.format(line))
            match = re.match(r'^Device\s(?P<mac_address>.*?)\s(?P<device>.*?)$', line)
            if match:
                mac_address = match.group('mac_address')
                device = match.group('device')
                    
                yield mac_address, device

    def player(self, action):
        log.info('Attempting to {} bluetooth audio'.format(action))
        self._execute_managed(['bluetoothctl', 'player.{}'.format(action)])

    def connect_device(self, source_device):
        log.info('Connecting bluetooth device: {}'.format(source_device.name))
        self._execute_managed(['bluetoothctl', 'connect', source_device.mac_address])
                
    def disconnect_device(self, source_device):
        log.info('Disconnecting bluetooth device: {}'.format(source_device.name))
        self._execute_managed(['bluetoothctl', 'disconnect', source_device.mac_address])

class XDisplay(Controller):
    def __init__(self, resolution, environment):
        super().__init__()
        
        self.resolution = resolution
        self.environment = environment
        
    def get_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': dict()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\sconnected'
        display_configs_regex = r'^(?P<resolution>\d+x\d+)\s+(?P<refreshRates>.*?)$'
        
        log.debug('Running xrandr...')
        randr = self._execute(['xrandr'])
        for line in self._read_stdout(randr):
            log.debug('xrandr output: {}'.format(line))
            
            match = re.search(display_device_regex, line, re.I)
            if match:
                display_config['device'] = match.group('device')
                
            match = re.search(display_configs_regex, line, re.I)
            if match:
                resolution = match.group('resolution')
                refresh_rates = match.group('refreshRates').replace('+', '')
                if '*' in refresh_rates:
                    display_config['current_resolution'] = resolution
                for refresh_rate in refresh_rates.split():
                    refresh_rate = refresh_rate.replace('*', '')
                    if not display_config['resolutions'].get(resolution):
                        display_config['resolutions'][resolution] = [refresh_rate]
                    else:
                        display_config['resolutions'][resolution].append(refresh_rate)
            
        return display_config
        
    def enforce_resolution(self):
        if self.environment == 'desktop':
            display_config = self.get_display_config()
          
            if not display_config['current_resolution']:
                log.warning('There is currently no display connected: {}'.format(display_config))  
            elif display_config['current_resolution'] == self.resolution:
                log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
            else:
                res_profile = display_config['resolutions'].get(self.resolution)
                log.info('Setting resolution to {} refresh rate to {}'.format(self.resolution, max(res_profile)))

                xrandr = self._execute_managed([
                    'xrandr', '--output', display_config['device'], 
                    '--mode', self.resolution, '--rate', max(res_profile)
                    ])


class WaylandDisplay(Controller):
    def __init__(self, resolution, environment):
        super().__init__()
        
        self.resolution = resolution
        self.environment = environment
        
    def get_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': list()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\s\"(?P<description>.*?)\"'
        display_configs_regex = r'^(?P<resolution>' + self.resolution + ')\spx,\s(?P<refreshRate>\d+\.\d+)'
        current_resolution_regex = r'^(?P<resolution>\d+x\d+)\spx,\s(?P<refreshRate>\d+\.\d+).*?current'
        
        randr = self._execute(['wlr-randr'])
        for line in self._read_stdout(randr):
            log.debug('wlr-randr output: {}'.format(line))
            
            match = re.search(display_device_regex, line, re.I)
            if match:
                display_config['device'] = match.group('device')
                display_config['description'] = match.group('description')
                
            match = re.search(display_configs_regex, line, re.I)
            if match:
                display_config['resolutions'].append(match.group('resolution') + '@' + match.group('refreshRate') + 'Hz')
            
            match = re.search(current_resolution_regex, line, re.I)
            if match:
                display_config['current_resolution'] = match.group('resolution') + '@' + match.group('refreshRate') + 'Hz'
                
        return display_config
        
    def enforce_resolution(self):
        if self.environment == 'desktop':
            display_config = self.get_display_config()
          
            if len(display_config['resolutions']) == 0:
                log.warning('There is currently no display connected: {}'.format(display_config))  
            elif display_config['current_resolution'] == max(display_config['resolutions']):
                log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
            else:
                log.info('Setting resolution to {}'.format(max(display_config['resolutions'])))
                randr = self._execute_managed([
                    'wlr-randr', '--output', display_config['device'], 
                    '--mode', max(display_config['resolutions'])
                    ])