import logging
import os
import random
import re
import time

from copy import deepcopy
from pulsectl import Pulse, PulseVolumeInfo
from threading import Event, Thread

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config

log = logging.getLogger()

class BluetoothDevice:
    def __init__(self, device_name, mac_address):
        self.name = device_name
        self.description = None
        self.mac_address = mac_address
        self.index = None
        self.active = False
        self.device = 'bluetooth'
        self.type = 'aux'
        self.meta = None

class PlexAmpDevice:
    def __init__(self, device_name, index, meta):
        self.name = device_name
        self.description = None
        self.index = index
        self.active = False
        self.device = 'plexamp'
        self.type = 'aux'
        self.meta = meta
     
# TODO: Get method to control shairport-sync
class AirPlayDevice:
    def __init__(self, device_name, index, meta):
        self.name = device_name
        self.description = None
        self.index = index
        self.active = False
        self.device = 'airplay'
        self.type = 'aux'
        self.meta = meta

class Audio(Controller):
    def __init__(self):
        super().__init__()

        self.pulse = Pulse()

        self.device_template = {
            'cards':    dict(),
            'modules':  dict(),
            'sinks':    dict(),
            'sources':  dict()
            }

    def get_module_arguments(self, module):
        module_args = dict()
        try:
            for key,val in re.findall(r'([^\s=]*)=(.*?)(?:\s|$)', module.argument):
                module_args[key] = val
                    
        except TypeError:
            pass

        return module_args

    """Updates the current source/sink/modules"""
    def get_active_devices(self, processes):
        device_meta = deepcopy(self.device_template)

        try:
            bth = Bluetooth()
            for mac_address, device_name in bth.get_connected_devices():
                log.debug('Found bluetooth device: {} ({})'.format(mac_address, device_name))

                source = BluetoothDevice(device_name, mac_address)
                source.active = True
                device_meta['sources'][device_name] = source
            
            alsa_cards = dict()
            for sink in self.pulse.sink_list():
                log.debug('Found sink device: {} {}'.format(sink.name, sink))
                if sink.name == 'combined':
                    log.debug('Sink device: {} is not supported'.format(sink.name))
                    continue

                sink_device = None
                if 'Built-in Audio' in sink.description:
                    sink_device = 'hdmi'
                else:
                    sink_device = 'external'

                try:
                    alsa_card = sink.proplist['alsa.card']
                    alsa_name = sink.proplist['alsa.name']
                    alsa_cards[alsa_card] = alsa_name
                except:
                    pass

                sink.active = False
                sink.device = sink_device
                device_meta['sinks'][sink.name] = sink
            
            for source in self.pulse.source_list():
                log.debug('Found source device: {} {}'.format(source.name, source))
                if source.name.startswith('alsa_output'):
                    log.debug('Source device: {} is not supported'.format(source.name))
                    continue

                if source.name == 'combined.monitor':
                    log.debug('Source device: {} is not supported'.format(source.name))
                    continue

                source_type = None
                if any('mic' in port.name or 'Microphone' in port.description for port in source.port_list):
                    source_type = 'mic'
                else:
                    source_type = 'aux'

                try:
                    alsa_card = source.proplist['alsa.card']
                    alsa_name = source.proplist['alsa.name']
                    if alsa_cards.get(alsa_card):
                        if alsa_cards[alsa_card] == alsa_name:
                            # When using a input/output card the input will often be labeled as a mic.
                            # Handle this as though it is an aux.  TODO: Make configurable
                            if source_type == 'mic':
                                source_type = 'aux'
                except:
                    pass

                source.active = False
                source.type = source_type
                source.device = 'pa'
                device_meta['sources'][source.name] = source

            for sink_input in self.pulse.sink_input_list():
                if not sink_input.proplist.get('application.process.id', False):
                    continue

                pid = sink_input.proplist['application.process.id']
                if not processes.get(pid):
                    print ('Unable to find pid {}'.format(pid))
                    continue

                sink_input_device = None
                app_name = sink_input.proplist['application.name']
                if '/usr/bin/node' in processes[pid]['COMMAND']:
                    sink_input_device = PlexAmpDevice(app_name, sink_input.index, sink_input)
                elif '/usr/local/bin/shairport-sync' in processes[pid]['COMMAND']:
                    sink_input_device = AirPlayDevice(app_name, sink_input.index, sink_input)

                if not sink_input_device:
                    print ('Unable to identify a process for {}'.format(processes[pid]))
                    continue

                log.debug('Found source device: {} {}'.format(sink_input_device.type, sink_input))

                sink_input_device.active = True
                device_meta['sources'][app_name] = sink_input_device
            
            for module in self.pulse.module_list():
                log.debug('Found module device: {} {}'.format(module.name, module))
                device_meta['modules'][module.name] = module
                
        except Exception as e:
            log.exception('Failed to update PulseAudio devices:')

        return device_meta

    def set_sink_volume(self, device, sink_name, sink_channels, sink_volume):
        sink_volume = PulseVolumeInfo(sink_volume, sink_channels)
        log.info('Setting sink {} volume to {}'.format(sink_name, sink_volume))
        self.pulse.sink_volume_set(device.index, sink_volume)

    def set_source_volume(self, device, source_name, source_channels, volume):
        source_volume = PulseVolumeInfo(volume, source_channels)
        log.info('Setting source {} volume to {}'.format(source_name, source_volume))
        self.pulse.source_volume_set(device.index, source_volume)
            
    def unload_loopback_modules(self, sink_name=None, source_name=None):
        for module in self.pulse.module_list():
            if module.name == 'module-loopback':
                try:
                    module_args = self.get_module_arguments(module)
                    if sink_name and module_args['sink'] == sink_name:
                        self.pulse.module_unload(module.index)
                    elif source_name and module_args['source'] == source_name:
                        self.pulse.module_unload(module.index)

                except TypeError:
                    pass
                except Exception:
                    log.exception('Failed to unload module {} {}'.format(module.name, module.index))

    def unload_combined_sink_modules(self):
        for module in self.pulse.module_list():
            log.debug(module.name)
            if module.name == 'module-combine-sink':
                try:
                    log.info('Unloading combined sink {}'.format(module.name))
                    self.pulse.module_unload(module.index)
                    return True

                except TypeError:
                    pass
                except Exception:
                    log.exception('Failed to unload module {} {}'.format(module.name, module.index))

        return False

    def close(self):
        self.pulse.close()

class ProjectM(Controller):
    def __init__(self, config, control):
        super().__init__()
        
        self.config = config
        self.control = control
        
        self.projectm_path = self.config.projectm['path']
        self.projectm_process = None
        
        config_path = os.path.join(self.projectm_path, 'projectMSDL.properties')
        self.projectm_config = Config(config_path, config_header='[projectm]')
        
        self.threads = list()
        self.thread_event = Event()
        
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
                        if self.config.projectm['screenshots_enabled'] and self.control.source_device:
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