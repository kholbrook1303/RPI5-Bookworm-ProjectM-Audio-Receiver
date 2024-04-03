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

log = logging.getLogger()
    
class SignalMonitor:
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True
    
class ProjectMAR(object):
    def __init__(self):        
        pass
    
    """Execute a process.
    @param args: an array of arguments including the executable
    @param shell: specifies wether or not to run the command as shell
    @returns a process instance
    """
    def _execute(self, args, shell=False):
        process = Popen(args, stdin=PIPE, stderr=PIPE, stdout=PIPE, universal_newlines=True, shell=shell)
        return process
    
    """Execute a managed process.
    @param args: an array of arguments including the executable
    @param shell: specifies wether or not to run the command as shell
    @returns a boolean indicating whether the process execution failed
    """
    def _execute_managed(self, args, shell=False):
        log.debug('Running command: {}'.format(args))
        process = Popen(args, universal_newlines=True, shell=shell)
        stdout,stderr = process.communicate()
        
        if stdout:
            log.debug('stdout: {}'.format(stdout))
        if stderr:
            log.error(stderr)
            return False
        if process.returncode != 0:
            log.error('command return code: {}'.format(process.returncode))
            return False
        
        return True
    
    """Process stdout of a process instance.
    @param process: a process instance 
    @yields each line of the stdout
    """
    def _read_stdout(self, process):
        for line in iter(process.stdout.readline, ""):
            yield line.strip()
    
    """Process stderr of a process instance.
    @param process: a process instance 
    @yields each line of the stderr
    """
    def _read_stderr(self, process):
        for line in iter(process.stderr.readline, ""):
            yield line.strip()
            
    
class Control(ProjectMAR):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        self.thread = None
        self.thread_event = Event()
        
        self.sinks = dict()
        self.sources = dict()
        self.modules = dict()
        
        self.source_device = None
        self.source_device_type = None
        self.sink_device = None
        
        self.pa = Pulse('ProjectMAR')
        self.ar_mode = self.config.general['ar_mode']
        
        self.supported_sources = [
            'alsa_input',
            'bluez_source'
            ]
        self.supported_sinks = [
            'alsa_output'
            ]
    
    def _get_display_config(self, resolution):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': list()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\s\"(?P<description>.*?)\"'
        display_configs_regex = r'^(?P<resolution>' + resolution + ')\spx,\s(?P<refreshRate>\d+\.\d+)'
        current_resolution_regex = r'^(?P<resolution>\d+x\d+)\spx,\s(?P<refreshRate>\d+\.\d+).*?current'
        
        randr = self._execute(['wlr-randr'])
        for line in self._read_stdout(randr):
            log.debug('wlr-randr output: ' + line)
            
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
    
    def _control_sink_device(self, sink_name, sink_channels, device, volume=1):
        log.info('Identified a new sink device: {}'.format(sink_name))
        self.sink_device = sink_name
                    
        sink_volume = PulseVolumeInfo(volume, sink_channels)
        self.pa.sink_volume_set(device.index, sink_volume)
                
    def _control_source_device(self, source_name, source_channels, device, device_type, volume=1):
        log.info('Identified a new source device: {0} ({1})'.format(
            source_name,device.description
            ))
                    
        if self.source_device and self.source_device.startswith('bluez_source'):
            log.info('Disconnecting bluetooth device: {}'.format(self.source_device))
            device_mac = self.source_device.split('.')[1].replace('_', ':')
            self._execute_managed(['bluetoothctl', 'disconnect', device_mac])

        self.source_device_type = device_type
        self.source_device = source_name
                
        self.pa.default_set(device)
        source_volume = PulseVolumeInfo(volume, source_channels)
        self.pa.source_volume_set(device.index, source_volume)
        
        if device_type == 'aux' and not source_name.startswith('bluez_source'):
            self.unload_loopback_modules()
            self.pa.module_load('module-loopback', [
                'source=' + source_name, 
                'sink=' + self.sink_device,
                'latency_msec=20'
                ])
    
    """Updates the current source/sink/modules"""
    def update_devices(self):
        try:
            self.sinks.clear()
            for sink in self.pa.sink_list():
                self.sinks[sink.name] = sink
            
            self.sources.clear()
            for source in self.pa.source_list():
                self.sources[source.name] = source
            
            self.modules.clear()
            for module in self.pa.module_list():
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
            log.error('Failed to update PulseAudio devices')
        
    def enforce_resolution(self):
        resolution = self.config.general['resolution']
        display_config = self._get_display_config(resolution)
          
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
            
    def kill_prior_instances(self):
        processes = [
            'projectMSDL'
            ]
        
        for process in processes:
            pgrep = self._execute(['pgrep', '-f', process])
            for line in self._read_stdout(pgrep):
                log.info('Killing process {} ({})'.format(process, line))
                self._execute_managed(['sudo', 'killall',  process])
                break
            
    def unload_loopback_modules(self):
        for module in self.pa.module_list():
            if module.name == 'module-loopback':
                try:
                    m_args = dict()
                    for key,val in re.findall(r'([^\s=]*)=(?:\"|)(.*?)(?:\"|\s)', module.argument):
                        m_args[key] = val
                        
                    if m_args['source'].startswith('bluez_source'):
                        continue
                    
                    log.info('Unloading module {} ({})'.format(m_args['source'], module.index))
                    self.pa.module_unload(module.index)
                except TypeError:
                    pass
            
    def control_devices(self):
        # Check for any disconnected sink devices
        if self.sink_device and self.sink_device not in self.sinks:
            log.warning('Sink device {} has been disconnected'.format(self.sink_device))
            self.sink_device = None
            
        # Check for any disconnected source devices
        if self.source_device and self.source_device not in self.sources:
            log.warning('Source device {} has been disconnected'.format(self.source_device))
            self.source_device = None
            if self.source_device_type == 'aux':
                self.unload_loopback_modules()
                self.source_device_type = None
        
        # Check for new sink devices
        for sink_name, device in self.sinks.items():
            sink_channels = len(device.volume.values)
            if self.ar_mode == 'automatic':
                if any(sink_name.startswith(dev) for dev in self.supported_sinks) and self.sink_device != sink_name:
                    self._control_sink_device(sink_name, sink_channels, device)
                    break
                    
            elif self.ar_mode == 'manual':
                if sink_name in self.config.manual['sink_devices'] and self.sink_device != sink_name:
                    self._control_sink_device(sink_name, sink_channels, device)
                    
            else:
                raise Exception('The specified mode \'{0}\' is invalid!'.format(self.ar_mode))
            
                
        if not self.sink_device:
            log.warning("No sink devices were found!")
        
        devices_found = 0
        devices_connected = 0
        for source_name, device in self.sources.items():
            source_channels = len(device.volume.values)
            source_volume = device.volume.values
            
            if self.ar_mode == 'automatic':
                if not any(src in source_name for src in self.supported_sources):
                    continue
            
                devices_found += 1
            
                source_channels = len(device.volume.values)
                source_volume = device.volume.values
            
                if self.source_device != source_name and devices_connected == 0:
                    self._control_source_device(source_name, source_channels, device, self.config.automatic['audio_mode'])
                    devices_connected += 1
                    break
                
            elif self.ar_mode == 'manual':
                if source_name in self.config.manual['mic_devices']:
                    devices_found += 1
                    if self.source_device != source_name and devices_connected == 0:
                        self._control_source_device(source_name, source_channels, device, 'mic', volume=.75)
                        devices_connected += 1
                        
                elif source_name.startswith('bluez_source'):
                    devices_found += 1
                    if self.source_device != source_name and devices_connected == 0:
                        self._control_source_device(source_name, source_channels, device, 'aux')
                        devices_connected += 1
                        
                elif source_name in self.config.manual['aux_devices']:
                    devices_found += 1
                    if self.source_device != source_name and devices_connected == 0:
                        self._control_source_device(source_name, source_channels, device, 'aux', volume=.75)
                        devices_connected += 1
                        
            else:
                raise Exception('The specified mode \'{0}\' is invalid!'.format(self.ar_mode))
            
        
        if devices_found == 0:
            log.debug("No mic/aux devices detected")
            self.source_device = None
            self.source_device_type = None
        
    def control(self):
        while not self.thread_event.is_set():
            try:
                self.enforce_resolution()
                self.update_devices()
                self.control_devices()
            except Exception as e:
                log.exception('Device control failed!')
                
            time.sleep(5)
        
    def start(self):
        self.kill_prior_instances()

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

class Wrapper(ProjectMAR):
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
            log.info('Performing smart randomization on presets!')
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
        
        # Start hang thread to trigger the next preset 
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
        

def main():
    config_path = os.path.join(APP_ROOT, 'projectMAR.conf')
    print (config_path)
    config = Config(config_path)
    
    logpath = os.path.join(APP_ROOT, 'projectMAR.log')
    log_init(logpath, config.general['log_level'])
    log_init('console', config.general['log_level'])
    
    sm = SignalMonitor()
    
    log.info('Initializing projectMAR System Control in {0} mode...'.format(
        config.general['ar_mode']
        ))
    pmc = Control(config)
    pmc.start()
    
    log.info('Initializing projectMSDL Wrapper...')
    pmw = Wrapper(config, pmc)
    
    log.info('Executing ProjectMSDL and monitorring presets for hangs...')
    pmw.execute()
    
    while not sm.exit:
        try:
            if pmw.projectm_process.poll() != None:
                log.warning('ProjectM has terminated!')
                break
            
            time.sleep(1)
        except KeyboardInterrupt:
            log.warning('User initiated keyboard exit')
            break
        except:
            log.exception('projectMAR failed!')
            
    log.info('Closing down all threads/processes...')
    pmw.thread_event.set()
    
    pmw.stop()
    pmc.stop()
            
    log.info('Exiting ProjectMAR!')
    sys.exit(0)

if __name__ == "__main__":
    main()
