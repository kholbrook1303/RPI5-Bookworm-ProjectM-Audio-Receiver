import glob
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

    """Execute a plugin process, expanding wildcards before launching.
    Captures stdout/stderr for monitoring.
    @param name: the name of the process
    @param path: the path to the executable
    @param args: an array of arguments including the executable
    @param shell: specifies whether or not to run the command as shell
    @returns a ProcessAttributes instance
    """
    def _execute(self, name, path, args, shell=False):
        expanded_args = []
        for arg in args:
            # Only expand wildcards for local filesystem paths
            if "*" in arg or "?" in arg or "[" in arg:  
                files = glob.glob(arg, recursive=True)
                if files:
                    expanded_args.extend(files)
                else:
                    # If no files matched, keep the literal arg
                    expanded_args.append(arg)
            else:
                expanded_args.append(arg)

        # Launch the process
        process = Popen(
            [path] + expanded_args[1:],  # path + expanded arguments
            stdin=None,                  # important: do NOT pipe stdin
            stdout=PIPE,
            stderr=PIPE,
            universal_newlines=True,
            shell=False
        )

        return ProcessAttributes(name, process, path, expanded_args)
    
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