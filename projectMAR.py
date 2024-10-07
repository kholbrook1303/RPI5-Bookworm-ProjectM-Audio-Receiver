import logging
import os
import signal
import sys
import time

from copy import deepcopy
from threading import Thread, Event

from lib.config import Config, APP_ROOT
from lib.log import log_init
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
        self.config                 = config
            
        self.audio                  = Audio(self.config)
        self.bluetooth              = Bluetooth()
        self.thread                 = None
        self.thread_event           = Event()
        
        self.environment            = self._get_environment()
        
        self.display = None
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
            
            self.display = display_method(
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
        
    def monitor(self):
        while not self.thread_event.is_set():
            try:
                if self.display and self.config.general['projectm_enabled']:
                    self.display.enforce_resolution()

                self.audio.handle_devices()
            except Exception as e:
                log.exception('Device processing failed!')
                
            time.sleep(5)
        
    def start(self):
        self.thread = Thread(
            target=self.monitor,
            args=(),
            daemon=True
            )
        self.thread.start()
    
    def stop(self):
        self.thread_event.set()
        self.thread.join()
        self.audio.close()
        

def main():
    config_path = os.path.join(APP_ROOT, 'projectMAR.conf')
    print (config_path)
    config = Config(config_path)
    
    logpath = os.path.join(APP_ROOT, 'projectMAR.log')
    log_init(logpath, config.general['log_level'])
    log_init('console', config.general['log_level'])
    
    sm = SignalMonitor()
    
    log.info('Initializing projectMAR System Control in {0} mode...'.format(
        config.audio_receiver.get('audio_mode', 'automatic')
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
