import json
import logging
import logging.handlers
import os
import random
import re
import signal
import sys
import time

from configparser import ConfigParser, RawConfigParser
from datetime import datetime
from subprocess import Popen, PIPE
from threading import Thread, Event

loggers = {}
log = logging.getLogger()

APP_ROOT = os.path.dirname(
    os.path.abspath(__file__)
    )

class JsonFormatter(logging.Formatter):
    def formatException(self, exc_info):
        result = super(JsonFormatter, self).formatException(exc_info)
        json_result = {
        "timestamp": f"{datetime.now()}",
        "level": "ERROR",
        "Module": "projectMAR",
        "message": f"{result}",
        }
        return json.dumps(json_result)

def log_init(name, level=logging.INFO, **kwargs):
    json_formatter = JsonFormatter(
        '{"timestamp":"%(asctime)s", "level":"%(levelname)s", "Module":"%(module)s", "message":"%(message)s"}'
        )

    if name.endswith('.log'):
        hdlr = logging.handlers.TimedRotatingFileHandler(
            name,
            when=kwargs.get('frequency', 'midnight'),
            interval=kwargs.get('interval', 1),
            backupCount=kwargs.get('backups', 5)
            )
        hdlr.setFormatter(json_formatter)
        hdlr.setLevel(level)

    if name == "console":
        hdlr = logging.StreamHandler()
        hdlr.setFormatter(json_formatter)
        hdlr.setLevel(level)
       
    loggers[name] = hdlr
    log.addHandler(hdlr)
    log.setLevel(level)
    
class Config:
    def __init__(self, config_path, config_header=None):
        try:
            if config_header:
                config = RawConfigParser(allow_no_value=True)
                with open(config_path) as config_file:
                    data = config_file.read()
                    config.read_string(config_header + '\n' + data)
                    
            else:
                config = ConfigParser(allow_no_value=True)
                config.read(config_path)

            for section in config.sections():
                setattr(self, section, dict())

                for name, str_value in config.items(section):
                    if name.endswith("_devices"):
                        value = config.get(section, name).split(",")
                    elif self._is_str_bool(str_value):
                        value = config.getboolean(section, name)
                    elif self._is_str_int(str_value):
                        value = config.getint(section, name)
                    else:
                        value = config.get(section, name)

                    getattr(self, section)[name] = value

        except:
            log.error("Error loading configuration file")
            sys.exit()
        
    def _is_str_bool(self, value):
        """Check if string is an integer.
        @param value: object to be verified.
        """
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return True

        return False

    def _is_str_int(self, value):
        """Check if string is an integer.
        @param value: object to be verified.
        """
        try:
            int(value)
            return True
        except:
            return False
    
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
    
    def _execute(self, args, shell=False):
        process = Popen(args, stdin=PIPE, stderr=PIPE, stdout=PIPE, universal_newlines=True, shell=shell)
        return process
    
    def _read_stdout(self, process):
        for line in iter(process.stdout.readline, ""):
            yield line.strip()
    
    def _read_stderr(self, process):
        for line in iter(process.stderr.readline, ""):
            yield line.strip()
    
class Control(ProjectMAR):
    def __init__(self):
        super().__init__()
        
        config_path = os.path.join(APP_ROOT, 'projectMAR.conf')
        self.config = Config(config_path)
        
        self.thread = None
        self.thread_event = Event()
        
        self.source_device = None
        self.source_device_type = None
        self.sink_device = None
            
    def _get_devices(self, device_type, device_regex):
        devices = list()
        
        pactl = self._execute(['pactl', 'list', device_type, 'short'])
        for line in self._read_stdout(pactl):
            log.debug('pactl {} output: {}'.format(device_type, line))
            match = re.search(device_regex, line, re.I)
            if match:
                devices.append(match.group('name'))
                
        return devices
    
    def _get_display_config(self, resolution):
        display_config = {
            'device': None,
            'current_resolution': None,
            'resolutions': list()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\s'
        display_configs_regex = r'^(?P<resolution>' + resolution + ')\spx,\s(?P<refreshRate>\d+\.\d+)'
        current_resolution_regex = r'^(?P<resolution>\d+x\d+)\spx,\s(?P<refreshRate>\d+\.\d+).*?current'
        
        randr = self._execute(['wlr-randr'])
        for line in self._read_stdout(randr):
            log.debug('wlr-randr output: ' + line)
            
            match = re.search(display_device_regex, line, re.I)
            if match:
                display_config['device'] = match.group('device')
                
            match = re.search(display_configs_regex, line, re.I)
            if match:
                display_config['resolutions'].append(match.group('resolution') + '@' + match.group('refreshRate') + 'Hz')
            
            match = re.search(current_resolution_regex, line, re.I)
            if match:
                log.debug(str(match.groupdict()))
                display_config['current_resolution'] = match.group('resolution') + '@' + match.group('refreshRate') + 'Hz'
                
        return display_config
        
    def setup_display(self):
        resolution = self.config.general['resolution']
        display_config = self._get_display_config(resolution)
                
        if display_config['current_resolution'] == max(display_config['resolutions']):
            log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
        else:
            log.info('Setting resolution to {}'.format(max(display_config['resolutions'])))
            randr = self._execute([
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
                self._execute(['sudo', 'killall',  process])
                break
            
    def unload_loopback_modules(self):
        modules = self._get_devices('modules', r'^(?P<id>\d+)\s+module-loopback\s+source=(?P<source>.*?)\s')
        
        for module,moduleId in modules.items():
            if module[1:-1] in self.config.general['bluetooth_devices']:
                continue
                
            log.info('Unloading module {} ({})'.format(module, moduleId))
            self._execute(['pactl', 'unload-module', moduleId])         
            
    def setup_devices(self):
        sinks = self._get_devices('sinks', r'(?P<id>\d+)\s+(?P<name>.*?)\s+')
        sources = self._get_devices('sources', r'(?P<id>\d+)\s+(?P<name>.*?)\s+')
        
        for sink in sinks:
            if sink in self.config.general['sink_devices'] and self.sink_device != sink:
                log.info('Identified a new sink device: {}'.format(sink))
                self.sink_device = sink
                
        if not self.sink_device:
            raise Exception("No sink devices were found!")
        
        found_devices = 0
        connected_devices = 0
        for source in sources:
            if source in self.config.general['mic_devices']:
                found_devices += 1
                if self.source_device != source and connected_devices == 0:
                    connected_devices += 1
                    log.info('Identified a new mic source device: {}'.format(source))
                    
                    if self.source_device in self.config.general['bluetooth_devices']:
                        log.info('Disconnecting bluetooth device: {}'.format(self.source_device))
                        self._execute(['bluetoothctl', 'disconnect'])
                        
                    self.source_device_type = 'mic'
                    self.source_device = source
                    self.unload_loopback_modules()
                
                    self._execute(['pactl', 'set-default-source', source])
                    self._execute(['amixer', 'sset', 'Capture', '100%'])

            elif source in self.config.general['aux_devices']:
                found_devices += 1
                if self.source_device != source and connected_devices == 0:
                    connected_devices += 1
                    log.info('Identified a new aux source device: {}'.format(source))
                    
                    if self.source_device in self.config.general['bluetooth_devices']:
                        log.info('Disconnecting bluetooth device: {}'.format(self.source_device))
                        self._execute(['bluetoothctl', 'disconnect'])

                    self.source_device_type = 'aux'
                    self.source_device = source
                
                    self._execute(['pactl', 'set-default-source', source])
                    self._execute(['amixer', 'sset', 'Capture', '75%'])
                    proc = self._execute([
                        'pactl', 'load-module', 'module-loopback',
                        'source=' + source, 'sink=' + self.sink_device,
                        'latency_msec=20'
                        ])
                    
            elif source in self.config.general['bluetooth_devices']:
                found_devices += 1
                if self.source_device != source and connected_devices == 0:
                    connected_devices += 1
                    log.info('Identified a new bluetooth source:{}'.format(source))
                    self.source_device_type = 'bluetooth'
                    self.source_device = source
                    self.unload_loopback_modules()
                
                    self._execute(['amixer', 'sset', 'Capture', '100%'])
                
        if found_devices == 0:
            log.debug("No mic/aux/bluetooth devices detected")
            self.source_device = None
            self.source_device_type = None
        
    def control(self):
        while not self.thread_event.is_set():
            self.setup_display()
            self.setup_devices()
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

class Wrapper(ProjectMAR):
    def __init__(self):
        super().__init__()
        
        config_path = os.path.join(APP_ROOT, 'projectMSDL.properties')
        self.config = Config(config_path, config_header='[projectm]')
        
        self.threads = list()
        self.thread_event = Event()
        
        self.projectm_process = None
        self.preset_start = 0
        self.preset_shuffle = self.config.projectm['projectm.shuffleenabled']
        self.preset_display_duration = int(self.config.projectm['projectm.displayduration'])
        self.preset_path = self.config.projectm['projectm.presetpath'].replace(
            '${application.dir}', APP_ROOT
            )
                    
    def _monitor_output(self):
        preset_regex = r'^INFO: Displaying preset: (.*)$'
        for line in self._read_stderr(self.projectm_process):
            log.debug('ProjectM Output: {0}'.format(line))
            
            match = re.match(preset_regex, line, re.I)
            if match:
                log.debug('Currently displaying preset: {0}'.format(match.groups()[0]))
                self.preset_start = time.time()
            
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
        if self.preset_shuffle == 'false':
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
    logpath = os.path.join(APP_ROOT, 'projectMAR.log')
    log_init(logpath)
    log_init('console')
    
    sm = SignalMonitor()
    
    log.info('Initializing projectMAR System Control...')
    pmc = Control()
    pmc.start()
    
    log.info('Initializing projectMAR Wrapper...')
    pmw = Wrapper()
    
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
        except:
            log.exception('projectmWrapper failed!')
            
    log.info('Closing down all threads/processes...')
    pmw.thread_event.set()
    pmw.stop()
    pmc.stop()
    
    sys.exit(0)

if __name__ == "__main__":
    main()
