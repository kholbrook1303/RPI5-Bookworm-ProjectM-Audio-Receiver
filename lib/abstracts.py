import logging
import os
import signal
import time

from subprocess import PIPE, Popen

from lib.constants import ProcessAttributes

log = logging.getLogger()

class Controller:
    """Base class for all controllers in the projectMAR system.
    @param thread_event: an event to signal the thread to stop
    """
    def __init__(self, thread_event, config):
        self._config = config

        self._threads = dict()
        self._thread_event = thread_event
        self._processes = dict()
        self._running_processes = dict()
        self._environment = self._get_environment()

    """Determine the current running environment based on the contents of /boot/issue.txt"""
    def _get_environment(self):
        with open('/boot/issue.txt', 'r') as infile:
            data = infile.read()
            for line in data.splitlines():
                if 'stage2' in line:
                    return 'lite'
                elif 'stage4' in line:
                    return 'desktop'
                
        return None
        
    """Obtain all of the current running processes"""
    def _get_running_processes(self):
        process = Popen(['ps', '-ax'], stdout=PIPE)

        stdout = process.stdout.readlines()
        headers = [h for h in ' '.join(stdout[0].decode('UTF-8').strip().split()).split() if h]
        raw_data = map(lambda s: s.decode('UTF-8').strip().split(None, len(headers) - 1), stdout[1:])

        self._running_processes = {r[4]:dict(zip(headers, r)) for r in raw_data}
        
    """Kill a running process by PID
    @param pid: a process id (int)
    """
    def _kill_running_process(self, pid):
        os.kill(pid, signal.SIGKILL)
    
    """Process output stream of a process
    @param stream: the process output stream
    @yields lines of text from the stream"""
    def _read_stream(self, stream):
        for line in iter(stream.readline, ''):
            yield line.strip()

    """Execute a process.
    @param name: the name of the process
    @param path: the path to the executable
    @param args: an array of arguments including the executable
    @param shell: specifies whether or not to run the command as shell
    @returns a ProcessAttributes instance
    """
    def _execute(self, name, path, args, shell=False):
        process = Popen(args, stdin=PIPE, stderr=PIPE, stdout=PIPE, universal_newlines=True, shell=shell)
        process_attributes = ProcessAttributes(
            name, process, path, args
            )

        return process_attributes
    
    """Execute a monitored process.
    @returns a boolean indicating whether the process execution failed
    """
    def _monitor_processes(self):
        while not self._thread_event.is_set():
            for process_name, attr in self._processes.items():
                if attr.process.poll() != None:
                    log.warning(
                        '{} has exited with return code {}'.format(
                            process_name, attr.process.returncode
                            ))

                    if attr.halt_on_exit:
                        log.warning('Stopping ProjectMAR due to {} exit'.format(process_name))
                        self._thread_event.set()

                    elif attr.restore and attr.process.returncode != 0:
                        log.info('Starting {}...'.format(attr.args))
                        process = self._execute(attr.name, attr.path, attr.args)
                        attr.process = process

                elif attr.trigger:
                    if attr.trigger.is_set():
                        log.warning('Resetting {} due to resolution change'.format(attr.name))
                        attr.process.kill()

                        process = self._execute(attr.name, attr.path, attr.args)
                        attr.process = process
                        attr.trigger.clear()

            time.sleep(1)

    """Perform any controller exit operations"""
    def _close(self):
        for process_name, attr in self._processes.items():
            if attr.process.poll() == None:
                log.info('Terminating process {}'.format(process_name))
                attr.process.kill()

        for thread_name, thread in self._threads.items():
            log.info('Joining thread {}'.format(thread_name))
            thread.join()