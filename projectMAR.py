import argparse
import logging
import json
import os
import signal
import sys
import time

from threading import Event

from lib.config import Config, APP_ROOT
from lib.log import log_init

from controllers.audio import AudioCtrl
from controllers.display import DisplayCtrl
from controllers.plugins import PluginCtrl
from controllers.projectm import ProjectMCtrl

log = logging.getLogger()
    
class SignalMonitor:
    """Monitor for system signals to gracefully exit the application"""
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True

"""Main function to initialize and run the projectMAR system control.
@param config: the application configuration object
"""
def main(config):
    sm              = SignalMonitor()
    thread_event    = Event()
    refresh_event   = Event()

    log.info('Initializing projectMAR System Control in {0} mode...'.format(
        config.audio_ctrl.get('audio_mode', 'automatic')
        ))

    controllers = list()

    audio_ctrl = AudioCtrl(thread_event, config)
    if config.general.get('audio_ctrl', True):
        controllers.append(audio_ctrl)

    plugin_ctrl = PluginCtrl(thread_event, config)
    if config.general.get('plugin_ctrl', False):
        controllers.append(plugin_ctrl)

    display_ctrl = DisplayCtrl(thread_event, refresh_event, config)
    if config.general.get('display_ctrl', True):
        controllers.append(display_ctrl)
    
    if config.general.get('projectm_ctrl', True):
        projectM_ctrl = ProjectMCtrl(thread_event, refresh_event, config, audio_ctrl, display_ctrl)
        controllers.append(projectM_ctrl)

    for controller in controllers:
        controller.start()
    
    while not sm.exit:
        try:      
            if thread_event.is_set():
                break

            time.sleep(1)
        except KeyboardInterrupt:
            log.warning('User initiated keyboard exit')
            break
        except:
            log.exception('projectMAR failed!')
            
    log.info('Closing down all threads/processes...')
    if not thread_event.is_set():
        thread_event.set()
        
    for controller in controllers:
        controller.join()
        controller.close()
            
    log.info('Exiting ProjectMAR!')
    sys.exit(0)

"""Parse command line arguments for the projectMAR system control"""
def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-d','--diagnostics',
        action='store_true',
        dest='diag',
        help='Output diagnostics report for issue debugging'
        )

    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    config_path = os.path.join(APP_ROOT, 'conf', 'projectMAR.conf')
    config = Config(config_path)
    
    logpath = os.path.join(APP_ROOT, 'projectMAR.log')
    log_level = config.general.get('log_level', logging.INFO)
    log_init(logpath, log_level)
    log_init('console', log_level)

    if args.diag:
        diag_path = os.path.join(APP_ROOT, 'diag')
        if not os.path.exists(diag_path):
            os.makedirs(diag_path)

        audio = AudioCtrl(None, config)
        audio_data = dict()
        for cat, data in audio.get_raw_diagnostics():
            if not audio_data.get(cat):
                audio_data[cat] = [data]
            else:
                audio_data[cat].append(data)

        audio_json = os.path.join(diag_path, 'raw_audio.json')
        with open(audio_json, 'w') as outfile:
            outfile.write(json.dumps(audio_data, indent=2, default=str))

        audio_devices = audio.get_device_diagnostics()
        audio_devices_json = os.path.join(diag_path, 'audio_devices.json')
        with open(audio_devices_json, 'w') as outfile:
            outfile.write(json.dumps(audio_data, indent=2, default=str))

        audio.close()

        display = DisplayCtrl(None, config)
        if display._environment == 'desktop':
            display_data = display.get_diagnostics()

            display_json = os.path.join(diag_path, 'display.json')
            with open(display_json, 'w') as outfile:
                outfile.write(json.dumps(display_data, indent=2, default=str))

        display.close()
        sys.exit(0)

    main(config)
