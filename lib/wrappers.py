import logging
import os
import random
import re
from threading import Event, Thread
import time

from lib.abstracts import Wrapper
from lib.config import APP_ROOT, Config

log = logging.getLogger()

class ProjectM(Wrapper):
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
        preset_regex = r'^INFO: Displaying preset: (?P<name>.*)$'
        for line in self._read_stderr(self.projectm_process):
            log.debug('ProjectM Output: {0}'.format(line))
            
            try:
                match = re.match(preset_regex, line, re.I)
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

class Device(Wrapper):
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

class Bluetooth(Wrapper):
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
                
    def disconnect_device(self, source_device):
        log.info('Disconnecting bluetooth device: {}'.format(source_device['name']))
        self._execute_managed(['bluetoothctl', 'disconnect', source_device['mac']])

class XDisplay(Wrapper):
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


class WaylandDisplay(Wrapper):
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