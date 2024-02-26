import json
import logging
import logging.handlers
import os
import re
import signal
import sys
import time

from configparser import ConfigParser
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
        "Module": "projectm_wrapper",
        "message": f"{result}",
        }
        return json.dumps(json_result)

def log_init(name, level=logging.DEBUG, **kwargs):
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
    
class SignalMonitor:
  exit = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.set_exit)
    signal.signal(signal.SIGTERM, self.set_exit)

  def set_exit(self, signum, frame):
    self.exit = True

class ProjectmWrapper:
    def __init__(self):
        self.config = self._get_config()
        
        self.threads = list()
        self.thread_event = Event()
        
        self.projectm_process = None
        self.preset_start = 0
        self.preset_display_duration = int(self.config['projectm']['projectM.displayDuration'])
        
    def _get_config(self):
        config_path = os.path.join(APP_ROOT, 'projectMSDL.properties')
        
        config = ConfigParser()
        with open(config_path) as config_file:
            data = config_file.read()
            config.read_string('[projectm]\n' + data)
            
        return config
                    
    def _monitor_output(self):
        preset_regex = r'^INFO: Displaying preset: (.*)$'
        for stdout_line in iter(self.projectm_process.stderr.readline, ""):
            log.debug('ProjectM Output: {0}'.format(stdout_line.strip()))
            
            match = re.match(preset_regex, stdout_line, re.I)
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
                    xautomation_process = Popen(['xte'], stdin=PIPE)
                    xautomation_process.communicate(input=b'key n\n')
                
            time.sleep(1)
        
    def execute(self, beatSensitivity=2.0):        
        app_path = os.path.join(APP_ROOT, 'projectMSDL')
        self.projectm_process = Popen(
            [app_path, '--beatSensitivity=' + str(beatSensitivity)],
            stdin=PIPE, stderr=PIPE, stdout=PIPE, 
            universal_newlines=True
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
    logpath = os.path.join(APP_ROOT, 'projectmWrapper.log')
    log_init(logpath)
    log_init('console')
    
    sm = SignalMonitor()
    
    log.info('Initializing projectmWrapper...')
    pmw = ProjectmWrapper()
    
    log.info('Executing ProjectMSDL and monitorring the presets for hangs...')
    pmw.execute()
    
    while True:
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
    sys.exit(0)
        

if __name__ == "__main__":
    main()
