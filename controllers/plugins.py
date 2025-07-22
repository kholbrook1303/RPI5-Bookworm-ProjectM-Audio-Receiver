import logging
import os
import threading

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config

log = logging.getLogger()

class PluginCtrl(Controller, threading.Thread):
    """Controller for managing audio plugins"""
    def __init__(self, thread_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event)

        self.config         = config
        self.thread_event   = thread_event
        
        self.audio_plugins_config = Config(os.path.join(APP_ROOT, 'conf', 'audio_plugins.conf'))
                  
    """Monitor the output of a plugin process"""
    def monitor_output(self, plugin_name, plugin_output_stream, log_level):
        while not self._thread_event.is_set():
            line = next(self._read_stream(plugin_output_stream), None)
            if line is None:
                break

            log.log(log_level, '{} Plugin Output: {}'.format(plugin_name, line))

    """Run the plugins controller thread"""
    def run(self):
        self._get_running_processes()
        plugins = self.audio_plugins_config.general.get('audio_plugins', list())
        for plugin in plugins:
            try:
                plugin_config     = getattr(self.audio_plugins_config, plugin)
                plugin_name     = plugin_config.get('name', '')
                plugin_path     = plugin_config.get('path', '')
                plugin_restore  = plugin_config.get('restore', True)

                if plugin_name == '' or plugin_path == '':
                    log.error('Plugin {} has not been configured'.format(plugin))
                    continue

                plugin_args = list()
                plugin_args.append(plugin_path)

                config_args = plugin_config.get('arguments', '').split(' ')
                for config_arg in config_args:
                    if config_arg == '':
                        continue

                    plugin_args.append(config_arg)

                process_cl = ' '.join(plugin_args)
                if self._running_processes.get(process_cl):
                    log.warning('{} is already running!  Attempting to kill the process...'.format(plugin_name))
                    pid = int(self._running_processes[process_cl]['PID'])
                    self._kill_running_process(pid)

                log.info('Loading plugin {} with {}'.format(plugin_name, ' '.join(plugin_args)))
                plugin_process_attributes = self._execute(
                    plugin_name, plugin_path, plugin_args
                    )

                plugin_process_attributes.restore = plugin_restore

                self._processes[plugin_name] = plugin_process_attributes
        
                output_monitors = [
                    {
                        'name': plugin_name + '_Output',
                        'target': self.monitor_output, 
                        'args': (plugin_name, plugin_process_attributes.process.stdout, logging.INFO)
                    },
                    {
                        'name': plugin_name + '_Error',
                        'target': self.monitor_output, 
                        'args': (plugin_name, plugin_process_attributes.process.stderr, logging.ERROR)
                    }
                ]

                for monitor in output_monitors:
                    output_thread = threading.Thread(
                        target=monitor['target'],
                        args=monitor['args']
                        )

                    output_thread.start()
                    self._threads[monitor['name']] = output_thread

            except AttributeError as ae:
                log.warning('Unable to load plugin {}: {}'.format(plugin, ae))

            except Exception as e:
                log.exception('Failed to load plugin {} with error {}'.format(plugin, e))

        self._monitor_processes()

    """Close the plugin controller and all associated threads"""
    def close(self):
        self._close()