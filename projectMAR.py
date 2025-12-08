import argparse
import logging
import json
import os
import sys
import threading

from lib.config import Config, APP_ROOT
from lib.common import get_environment
from lib.log import log_init

from core.controllers.Audio import AudioCtrl
from core.controllers.Display import DisplayCtrl
from core.RenderingLoop import RenderingLoop

log = logging.getLogger()

def get_diagnostics(config):
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

    audio.close()

    display = DisplayCtrl(None, config)
    if get_environment() == 'desktop':
        display_data = display.get_diagnostics()

        display_json = os.path.join(diag_path, 'display.json')
        with open(display_json, 'w') as outfile:
            outfile.write(json.dumps(display_data, indent=2, default=str))

    display.close()

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

    thread_event = threading.Event()

    if args.diag:
        get_diagnostics(config)

    else:
        app = RenderingLoop(config, thread_event)

        try:
            app.run()
        except:
            log.exception('Fatal error running projectMAR!')
        finally:
            app.close()

    sys.exit(0)
