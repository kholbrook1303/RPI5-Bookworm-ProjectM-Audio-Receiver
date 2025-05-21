import logging
import os
import signal
import time

from subprocess import PIPE, Popen

log = logging.getLogger()

class Controller:
    def __init__(self, thread_event):
        self._threads = dict()
        self._thread_event = thread_event
        self._processes = dict()
        self._running_processes = dict()
        self._environment = self._get_environment()

    def _get_environment(self):
        with open('/boot/issue.txt', 'r') as infile:
            data = infile.read()
            for line in data.splitlines():
                if 'stage2' in line:
                    return 'lite'
                elif 'stage4' in line:
                    return 'desktop'
                
        return None
        
    """Obtain all of the current running processes
    """
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
        log.debug('Running command {}'.format(args))
        process = Popen(args, universal_newlines=True, shell=shell)
        stdout,stderr = process.communicate()
        
        if stdout:
            log.debug('stdout: {}'.format(stdout))
        if stderr:
            log.error(stderr)
            return False
        if process.returncode != 0:
            log.error('command {} return code: {}'.format(args, process.returncode))
            return False
        
        return True

    def _monitor_processes(self, halt_on_exit=False):
        while not self._thread_event.is_set():
            for process_name, attr in self._processes.items():
                if attr['process'].poll() != None:
                    log.warning(
                        '{} has exited with return code {}'.format(
                            process_name, attr['process'].returncode
                            ))

                    if halt_on_exit or (attr['process'].returncode == 0 and attr['name'] == 'projectMSDL'):
                        log.warning('Stopping ProjectMAR due to {} exit'.format(process_name))
                        self._thread_event.set()

                    elif attr['meta']['restore'] and attr['process'].returncode != 0:
                        log.info('Starting {}...'.format(attr['meta']['args']))
                        process = self._execute(attr['meta']['args'])
                        attr['process'] = process

                elif attr['meta'].get('reset', None):
                    if attr['meta']['reset'].is_set():
                        log.warning('Resetting {} due to resolution change'.format(attr['name']))
                        attr['process'].kill()

                        process = self._execute(attr['meta']['args'])
                        attr['process'] = process
                        attr['meta']['reset'].clear()

            time.sleep(1)

    """Perform any controller exit operations
    """
    def _close(self):
        for process_name, attr in self._processes.items():
            if attr['process'].poll() == None:
                log.info('Terminating process {}'.format(process_name))
                attr['process'].kill()

        for thread_name, thread in self._threads.items():
            log.info('Joining thread {}'.format(thread_name))
            thread.join()