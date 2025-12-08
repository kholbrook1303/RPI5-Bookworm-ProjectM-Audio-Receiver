import ctypes.util
import logging
import platform

from subprocess import PIPE, Popen

from lib.abstracts import ProcessAttributes

log = logging.getLogger()

"""Determine the current running environment based on the contents of /boot/issue.txt"""
def get_environment():
    with open('/boot/issue.txt', 'r') as infile:
        data = infile.read()
        for line in data.splitlines():
            if any(stage in line for stage in ['stage2','stage-hyperbian']):
                return 'lite'
            elif 'stage4' in line:
                return 'desktop'
                
    return None

"""Get OS release information as a dictionary."""
def get_os_release():
    return platform.freedesktop_os_release()

"""Execute a process.
@param name: the name of the process
@param path: the path to the executable
@param args: an array of arguments including the executable
@param shell: specifies whether or not to run the command as shell
@returns a ProcessAttributes instance
"""
def execute(name, path, args, shell=False):
    process = Popen(args, stdin=PIPE, stderr=PIPE, stdout=PIPE, universal_newlines=True, shell=shell)
    process_attributes = ProcessAttributes(
        name, process, path, args
        )

    return process_attributes

"""Execute a managed process.
@param args: an array of arguments including the executable
@param shell: specifies whether or not to run the command as shell
@returns a boolean indicating whether the process execution failed
"""
def execute_managed(args, shell=False):
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

"""Load a shared library using ctypes.
@param name: the name of the library to load
@returns the loaded library
"""
def load_library(name: str):
    path = ctypes.util.find_library(name)
    if not path:
        raise Exception("Unable to load " + name)

    return ctypes.cdll.LoadLibrary(path)