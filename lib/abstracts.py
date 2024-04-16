import logging

from subprocess import PIPE, Popen

log = logging.getLogger()

class Wrapper:
    def __init__(self):
        pass
    
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