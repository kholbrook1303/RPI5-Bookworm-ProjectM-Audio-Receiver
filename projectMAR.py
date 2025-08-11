import argparse
import logging
import json
import os
import sys

from threading import Event

from lib.config import Config, APP_ROOT
from lib.common import get_environment
from lib.log import log_init

from lib.projectM.RenderingLoop import RenderingLoop

from controllers.audio import AudioCtrl
from controllers.display import DisplayCtrl
from controllers.plugins import PluginCtrl

log = logging.getLogger()

class ProjectMAR:
    def __init__(self, config):
        self.config         = config
        self.thread_event   = Event()
        self.ctrl_threads   = list()

    def run(self):
        try:
            log.info('Starting projectM rendering loop...')
            rendering_loop = RenderingLoop(self.config, self.thread_event)
            
            log.info('Initializing projectMAR System Control in {0} mode...'.format(
                self.config.audio_ctrl.get('audio_mode', 'automatic')
                ))

            controllers = {
                'audio_ctrl': AudioCtrl,
                'plugin_ctrl': PluginCtrl,
                'display_ctrl': DisplayCtrl
                }

            for name, controller in controllers.items():
                if self.config.general.get(name, False):
                    handler = controller(self.thread_event, self.config)
                    handler.start()
                    self.ctrl_threads.append(handler)

            rendering_loop.run()
        except:
            log.exception('Failed to run rendering loop')
            self.thread_event.set()

    def close(self):
        log.info('Closing down all threads/processes...')
        if not self.thread_event.is_set():
            self.thread_event.set()
        
        for controller in self.ctrl_threads:
            controller.join()
            controller.close()
            
        log.info('Exiting ProjectMAR!')

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

    pm = ProjectMAR(config)
    pm.run()
    pm.close()
