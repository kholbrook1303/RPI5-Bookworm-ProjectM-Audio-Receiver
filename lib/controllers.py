import logging
import os
import random
import re
import threading
import time

from pulsectl import Pulse, PulseVolumeInfo
from pulsectl.pulsectl import PulseOperationFailed
from threading import Thread

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config

log = logging.getLogger()

class PluginDevice:
    def __init__(self, device_name, device_index, device_meta=None):
        self.name           = device_name
        self.description    = None
        self.index          = device_index
        self.active         = False
        self.device         = None
        self.type           = 'aux'
        self.meta           = device_meta

class DeviceCatalog:
    def __init__(self):
        self.modules                = dict()
        self.sink_cards             = dict()
        self.sink_devices           = dict()
        self.source_devices         = dict()
        self.bluetooth_devices      = dict()
        self.plugin_devices         = dict()
        self.unsupported_sinks      = dict()
        self.unsupported_sources    = dict()

class AudioCtrl(Controller, threading.Thread):
    def __init__(self, thread_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event)
        
        self.config = config
        self.thread_event = thread_event
        
        self.audio_mode             = self.config.audio_receiver.get('audio_mode', 'automatic')
        self.io_device_mode         = self.config.audio_receiver.get('io_device_mode', 'aux')
        self.allow_multiple_sinks   = self.config.audio_receiver.get('allow_multiple_sinks', True)
        self.allow_multiple_sources = self.config.audio_receiver.get('allow_multiple_sources', True)
        self.sink_device            = None
        self.source_device          = None
        
        self.devices                = DeviceCatalog()
        self.bluetoothCtrl          = BluetoothCtrl(self.thread_event)

        self.pulse = Pulse()

        # Load null sink
        self.ar_sink = 'platform-project_mar.stereo'
        self.pulse.module_load('module-null-sink', [
            'sink_name=' + self.ar_sink,
            'sink_properties=device.description=ProjectMAR-Sink-Monitor'
            ])

        # Set null sink monitor as default
        self.pulse.source_default_set('platform-project_mar.stereo.monitor')

    def get_raw_diagnostics(self):
        log.info('Getting sinks: sink_list()')
        for sinkInfo in self.pulse.sink_list():
            log.info('Identified sink {}'.format(sinkInfo.name))
            yield 'sinks', sinkInfo.__dict__
            
        log.info('Getting sources: source_list()')
        for sourceInfo in self.pulse.source_list():
            log.info('Identified sink {}'.format(sourceInfo.name))
            yield 'sources', sourceInfo.__dict__
            
        log.info('Getting sink inputs: sink_input_list()')
        for sinkInputInfo in self.pulse.sink_input_list():
            log.info('Identified sink input {}'.format(sinkInputInfo.name))
            yield 'sink_inputs', sinkInputInfo.__dict__
    
        log.info('Getting source outputs: source_output_list()')
        for sourceOutputInfo in self.pulse.source_output_list():
            log.info('Identified sink input {}'.format(sourceOutputInfo.name))
            yield 'source_outputs', sourceOutputInfo.__dict__
            
        log.info('Getting modules: module_list()')
        for moduleInfo in self.pulse.module_list():
            log.info('Identified module {}'.format(moduleInfo.name))
            yield 'modules', moduleInfo.__dict__
            
        log.info('Getting cards: card_list()')
        for cardInfo in self.pulse.card_list():
            log.info('Identified card {}'.format(cardInfo.name))
            yield 'cards', cardInfo.__dict__
            
        log.info('Getting clients: client_list()')
        for clientInfo in self.pulse.client_list():
            log.info('Identified client {}'.format(clientInfo.name))
            yield 'clients', clientInfo.__dict__

    def get_device_diagnostics(self):
        self.update_sink_devices()
        self.update_source_devices()
        self.update_bluetooth_devices()
        self.update_plugin_devices()

        return self.devices.__dict__

    def get_module_arguments(self, module):
        module.args = dict()
        if hasattr(module, 'argument'):
            if module.argument:
                args = module.argument.split(' ')
                for arg in args:
                    key,val = arg.split('=', 1)
                    module.args[key] = val

    def get_modules(self, module_name):
        modules = list()
        
        for module in self.pulse.module_list():
            try:
                self.get_module_arguments(module)
                if module.name == module_name:
                    modules.append(module)
            except:
                log.exception('Failed to process argument {}'.format(module.argument))
                pass

        return modules

    def module_loaded(self, module_name):
        modules = self.get_modules(module_name)
        if len(modules) > 0:
            return True

        return False
            
    def unload_loopback_modules(self, sink_name=None, source_name=None):
        for module in self.get_modules('module-loopback'):            
            unload = False
            if not source_name and not sink_name:
                unload = True
            elif sink_name and module.args.get('sink', None) == sink_name:
                unload = True
            elif source_name and module.args.get('source', None) == source_name:
                unload = True

            if unload:
                log.info('Unloading loopback module {}'.format(module.name))
                self.pulse.module_unload(module.index)

    def load_loopback_module(self, source_name, sink_name):
        log.info('Loading module-loopback for source {} sink {}'.format(source_name, sink_name))
        self.pulse.module_load('module-loopback', [
            'source=' + source_name,
            'sink=' + sink_name,
            'latency_msec=20',
            'source_dont_move=true',
            'sink_dont_move=true'
            ])

    def unload_null_sink_modules(self):
        for module in self.get_modules('module-null-sink'):
            log.info('Unloading null sink {}'.format(module.name))
            self.pulse.module_unload(module.index)

    def unload_combined_sink_modules(self):
        for module in self.get_modules('module-combine-sink'):
            log.info('Unloading combined sink {}'.format(module.name))
            self.pulse.module_unload(module.index)

    def load_combined_sinks(self, combined_sinks):
        log.info('Loading combined sink for {}'.format(combined_sinks))
        self.pulse.module_load('module-combine-sink', [
            'slaves=' + ','.join(combined_sinks)
            ])

    def set_sink_input_volume(self, sink_input_device, sink_input_channels, sink_input_volume):
        sink_input_volume_info = PulseVolumeInfo(sink_input_volume, sink_input_channels)
        log.info('Setting sink input {} volume to {}'.format(sink_input_device.name, sink_input_volume_info))
        self.pulse.sink_input_volume_set(sink_input_device.meta.index, sink_input_volume_info)
    
    def control_plugin_device(self, plugin_device, plugin_volume):
        log.info('Identified a new plugin device: {}'.format(plugin_device.name))
        
        plugin_channels = len(plugin_device.meta.volume.values)
        self.set_sink_input_volume(plugin_device, plugin_channels, plugin_volume)

    def update_plugin_devices(self):
        plugins = self.pulse.sink_input_list()

        # Check for any disconnected plugin devices
        for plugin_name in list(self.devices.plugin_devices):
            disconnected = True
            for plugin in plugins:
                if plugin.proplist.get('application.process.binary'):
                    app = plugin.proplist['application.process.binary']
                    if plugin_name == app:
                        disconnected = False
            if disconnected:
                log.warning('Plugin device {} has been disconnected'.format(plugin_name))
                self.devices.plugin_devices.pop(plugin_name)

        for plugin in plugins:
            if plugin.proplist.get('application.process.binary'):
                app = plugin.proplist['application.process.binary']
                if not self.devices.plugin_devices.get(app):
                    plugin_device = None
                    if app == 'node':
                        plugin_device = PluginDevice(app, plugin.index, plugin)
                        plugin_device.device = 'plexamp'
                    elif app == 'shairport-sync':
                        plugin_device = PluginDevice(app, plugin.index, plugin)
                        plugin_device.device = 'airplay'
                    elif app == 'spotifyd':
                        plugin_device = PluginDevice(app, plugin.index, plugin)
                        plugin_device.device = 'spotify'

                    if not plugin_device:
                        log.warning('Unable to identify plugin device: {}'.format(plugin.__dict__))
                        continue

                    log.info('Found plugin device: {} {}'.format(plugin_device.name, plugin_device.device))
                    self.devices.plugin_devices[app] = plugin_device

    def update_bluetooth_devices(self):
        bluetooth_devices = list()

        for mac_address, device_name in self.bluetoothCtrl.get_connected_devices():
            bluetooth_device = PluginDevice(device_name, mac_address)
            bluetooth_device.device = 'bluetooth'
            bluetooth_devices.append(bluetooth_device)
            
        # Check for any disconnected bluetooth devices
        for bluetooth_name in list(self.devices.bluetooth_devices):
            if not any(bth_device.name == bluetooth_name for bth_device in bluetooth_devices):
                log.warning('Plugin device {} has been disconnected'.format(bluetooth_name))
                self.devices.bluetooth_devices.pop(bluetooth_name)

        for bluetooth_device in bluetooth_devices:
            if self.devices.bluetooth_devices.get(bluetooth_device.name):
                continue

            log.info('Found bluetooth device: {} {}'.format(bluetooth_device.name, bluetooth_device))
            self.devices.bluetooth_devices[bluetooth_device.name] = bluetooth_device

    def set_sink_volume(self, sink_device, sink_volume):
        try:
            sink_channels = len(sink_device.volume.values)
            sink_volume = PulseVolumeInfo(sink_volume, sink_channels)
            
            log.info('Setting sink {} volume to {}'.format(sink_device.name, sink_volume))
            self.pulse.sink_volume_set(sink_device.index, sink_volume)

        except:
            log.error('Failed to set sink {} volume'.format)

    def update_sink_devices(self):
        sinks = self.pulse.sink_list()

        # Check for any disconnected sink devices
        for sink_name in list(self.devices.sink_devices):
            if not any (sink_name == sink.name for sink in sinks):
                log.warning('Sink device {} has been disconnected'.format(sink_name))
                self.unload_loopback_modules(sink_name=sink_name)

                sink_device = self.devices.sink_devices[sink_name]
                if sink_device.proplist.get('alsa.card') and sink_device.proplist.get('alsa.long_card_name'):
                    alsa_card = sink_device.proplist['alsa.card']
                    alsa_name = sink_device.proplist['alsa.long_card_name']

                    if self.devices.sink_cards.get(alsa_card):
                        self.devices.sink_cards.pop(alsa_card)
                    
                self.devices.sink_devices.pop(sink_name)
                if sink_name == self.sink_device:
                    self.sink_device = None

        for sink in sinks:
            if self.devices.sink_devices.get(sink.name):
                continue
            elif self.devices.unsupported_sinks.get(sink.name):
                continue

            log.debug('Found sink device: {} {}'.format(sink.name, sink))
            if sink.name == 'combined':
                log.debug('Sink device: {} is not supported'.format(sink.name))
                self.devices.unsupported_sinks[sink.name] = sink
                
                sink_volume = None
                if self.audio_mode == 'automatic':
                    sink_volume = self.config.automatic.get('sink_device_volume', 1.0)
                elif self.audio_mode == 'manual':
                    sink_volume = self.config.manual.get('combined_sink_volume', 1.0)

                if not isinstance(sink_volume, float):
                    log.warning('Combined sink requires a float object')
                    sink_volume = 1.0

                self.set_sink_volume(sink, sink_volume)
                continue

            sink_type = None
            if 'Built-in Audio' in sink.description:
                sink_type = 'internal'
            else:
                sink_type = 'external'

            if sink.proplist.get('alsa.card') and sink.proplist.get('alsa.long_card_name'):
                alsa_card = sink.proplist['alsa.card']
                alsa_name = sink.proplist['alsa.long_card_name']
                log.debug('Identified sink ALSA card {} {}'.format(alsa_name, alsa_card))

                if not self.devices.sink_cards.get(alsa_card):
                    self.devices.sink_cards[alsa_card] = alsa_name

            sink.active = False
            sink.type = sink_type
            sink.device = 'pa'
            self.devices.sink_devices[sink.name] = sink
    
    def control_sink_device(self, sink_device, sink_volume):
        log.info('Identified a new sink device: {}'.format(sink_device.name))
        self.pulse.sink_default_set(sink_device.name)
        self.set_sink_volume(sink_device, sink_volume)

    def get_supported_sink_devices(self):
        if self.audio_mode == 'automatic':
            for sink_name, sink_device in self.devices.sink_devices.items():
                if sink_device.active:
                    continue

                sink_device_type = self.config.automatic.get('sink_device_type', None)
                if sink_device_type and sink_device.type != sink_device_type:
                    log.debug('Skipping sink {} as it is not {}'.format(sink_name, sink_device_type))
                    continue

                sink_volume = self.config.automatic.get('sink_device_volume', 1.0)
                if not isinstance(sink_volume, float):
                    log.warning('Sink {} does not have a float value for volume'.format(sink_name))
                    sink_volume = 1.0
                    
                supported_sink = {
                    'device': sink_device,
                    'volume': sink_volume
                    }

                yield supported_sink

        elif self.audio_mode == 'manual':
            for sink_id in self.config.manual.get('sink_devices', list()):
                sink_meta = getattr(self.config, sink_id)
                sink_name = sink_meta['name']
                if not sink_name:
                    log.warning('Sink {} is missing a name'.format(sink_id))
                    continue

                if self.devices.sink_devices.get(sink_name):
                    sink_device = self.devices.sink_devices[sink_name]
                    if sink_device.active:
                        continue

                    sink_device_type = sink_meta['type']
                    if sink_device_type and sink_device.type != sink_device_type:
                        log.debug('Skipping sink {} as it is not {}'.format(sink_device, sink_device_type))
                        continue
                    
                    sink_volume = sink_meta.get('volume', 1.0)
                    if not isinstance(sink_volume, float):
                        log.warning('Sink {} does not have a float value for volume'.format(sink_name))
                        sink_volume = 1.0
                    
                    supported_sink = {
                        'device': sink_device,
                        'volume': sink_volume
                        }

                    yield supported_sink

    def update_source_devices(self):
        sources = self.pulse.source_list()

        # Check for any disconnected source devices
        for source_name in list(self.devices.source_devices):
            if not any (source_name == source.name for source in sources):
                log.warning('Source device {} {} has been disconnected'.format(source_name, self.devices.source_devices[source_name].type))
                if not source_name.startswith('bluez_source'):
                    self.unload_loopback_modules(source_name=source_name)

                if source_name == self.source_device:
                    self.source_device = None

                self.devices.source_devices.pop(source_name)

        for source in sources:
            if self.devices.source_devices.get(source.name):
                continue
            elif self.devices.unsupported_sources.get(source.name):
                continue

            log.debug('Found source device: {} {}'.format(source.name, source))
            if source.name.startswith('alsa_output'):
                loopback_modules = self.get_modules('module-loopback')
                if not any(lm.args['source'] == source.name and lm.args['sink'] == self.ar_sink for lm in loopback_modules):
                    self.load_loopback_module(source.name, self.ar_sink)

                log.debug('Source device: {} is not supported'.format(source.name))
                self.devices.unsupported_sources[source.name] = source
                continue

            if source.name.endswith('.monitor'):
                log.debug('Source device: {} is not supported'.format(source.name))
                self.devices.unsupported_sources[source.name] = source
                continue

            source_type = None
            if any('mic' in port.name or 'Microphone' in port.description for port in source.port_list):
                source_type = 'mic'
            else:
                source_type = 'aux'

            if source.proplist.get('alsa.card') and source.proplist.get('alsa.long_card_name'):
                alsa_card = source.proplist['alsa.card']
                alsa_name = source.proplist['alsa.long_card_name']
                log.debug('Found Source ALSA card {} {}'.format(alsa_name, alsa_card))

                if self.devices.sink_cards.get(alsa_card):
                    if self.devices.sink_cards[alsa_card] == alsa_name:
                        if self.io_device_mode:
                            source_type = self.io_device_mode

            source.active = False
            source.type = source_type
            source.device = 'pa'
            self.devices.source_devices[source.name] = source

    def set_source_volume(self, source_device, volume):
        try:
            source_channels = len(source_device.volume.values)
            source_volume = PulseVolumeInfo(volume, source_channels)

            log.info('Setting source {} volume to {}'.format(source_device.name, source_volume))
            self.pulse.source_volume_set(source_device.index, source_volume)

        except:
            log.error('Failed to set source {} volume'.format(source_device.name))
                
    def control_source_device(self, source_device, source_volume):
        log.info('Identified a new {} {} source device: {} ({})'.format(
            source_device.device, source_device.type, source_device.name, source_device.description
            ))

        self.set_source_volume(source_device, source_volume)
        if not source_device.name.startswith('bluez_source'):
            self.unload_loopback_modules(source_name=source_device.name)

            if self.sink_device and source_device.type == 'aux':

                for sink in self.devices.sink_devices.values():
                    if not sink.active:
                        continue
                
                    self.load_loopback_module(source_device.name, sink.name)

            elif self.sink_device and source_device.type == 'mic':
                self.load_loopback_module(source_device.name, self.ar_sink)


    def get_supported_source_devices(self):
        if self.audio_mode == 'automatic':
            for source_name, source_device in self.devices.source_devices.items():
                if source_device.active:
                    continue

                source_device_type = self.config.automatic.get('source_device_type', None)
                if source_device_type and source_device.type != source_device_type:
                    log.debug('Skipping source {} as it is not {}'.format(source_name, source_device_type))
                    continue

                source_volume = self.config.automatic.get('source_device_volume', .85)
                if not isinstance(source_volume, float):
                    log.warning('Source {} does not have a float value for volume'.format(source_name))
                    source_volume = .85
                    
                supported_source = {
                    'device': source_device,
                    'volume': source_volume
                    }

                yield supported_source

        elif self.audio_mode == 'manual':
            for source_id in self.config.manual.get('source_devices', list()):
                source_meta = getattr(self.config, source_id)
                source_name = source_meta['name']
                if not source_name:
                    continue

                if self.devices.source_devices.get(source_name):
                    source_device = self.devices.source_devices[source_name]
                    if source_device.active:
                        continue

                    source_device_type = source_meta['type']
                    if source_device_type and source_device.type != source_device_type:
                        log.debug('Skipping source {} as it is not {}'.format(source_name, source_device_type))
                        continue

                    source_volume = source_meta.get('volume', .85)
                    if not isinstance(source_volume, float):
                        log.warning('Source {} does not have a float value for volume'.format(source_name))
                        source_volume = .85
                    
                    supported_source = {
                        'device': source_device,
                        'volume': source_volume
                        }

                    yield supported_source

    def handle_devices(self):
        self.update_sink_devices()

        active_sinks = list()
        for sink_device in self.devices.sink_devices.values():
            if sink_device.active:
                active_sinks.append(sink_device)
        
        inactive_sinks = list()
        for supported_sink in self.get_supported_sink_devices():
            inactive_sinks.append(supported_sink)

        total_sinks = len(active_sinks) + len(inactive_sinks)
        if self.allow_multiple_sinks and total_sinks > 1 and len(inactive_sinks) > 0:
            if self.module_loaded('module-combine-sink'):
                log.info('Found an active module-combined-sink module loaded!')
                self.unload_combined_sink_modules()

            combined_sinks = list()
            for sink_device in active_sinks:
                combined_sinks.append(sink_device.name)
            for supported_sink in inactive_sinks:
                supported_sink['device'].active = True
                combined_sinks.append(supported_sink['device'].name)

            self.load_combined_sinks(combined_sinks)
            self.pulse.sink_default_set('combined')
            self.sink_device = 'combined'

        elif not self.allow_multiple_sinks and len(active_sinks) > 0:
            pass
        else:
            if self.allow_multiple_sinks and total_sinks <= 1 and self.module_loaded('module-combine-sink'):
                self.unload_combined_sink_modules()

            for supported_sink in inactive_sinks:
                sink_device = supported_sink['device']
                sink_volume = supported_sink['volume']

                self.sink_device = sink_device.name
                self.control_sink_device(sink_device, sink_volume)
                self.devices.sink_devices[sink_device.name].active = True

                if not self.allow_multiple_sinks:
                    break

        if total_sinks == 0:
            log.debug("No sink devices were found!")

        self.update_source_devices()
        self.update_bluetooth_devices()
        self.update_plugin_devices()

        active_sources = list()
        for source_device in self.devices.source_devices.values():
            if source_device.active:
                active_sources.append(source_device)
        
        inactive_sources = list()
        for supported_source in self.get_supported_source_devices():
            inactive_sources.append(supported_source)

        total_sources = len(active_sources) + len(inactive_sources)

        if total_sources == 0:
            log.debug("No mic/aux devices detected")
            pass
        elif not self.allow_multiple_sources and len(active_sources) > 0:
            pass
        else:
            for supported_source in inactive_sources:
                source_device = supported_source['device']
                source_volume = supported_source['volume']

                self.source_device = source_device.name
                self.control_source_device(
                    source_device, 
                    source_volume
                    )
                self.devices.source_devices[source_device.name].active = True

                if not self.allow_multiple_sources:
                    break

        for plugin_device in self.devices.plugin_devices.values():
            if plugin_device.active:
                continue

            self.control_plugin_device(plugin_device, 1.0)
            plugin_device.active = True

    def run(self):
        while not self.thread_event.is_set():
            try:
                self.handle_devices()

            except PulseOperationFailed:
                log.exception('Failed to handle Pulseaudio devices... Restarting Pulseaudio')
                self.pulse = Pulse()

            except Exception as e:
                log.exception('Failed to handle Pulseaudio devices!')

            finally:
                time.sleep(2)

    def close(self):
        for source_name, source_device in self.devices.source_devices.items():
            if not source_device.active:
                continue

            if not source_name.startswith('bluez_source'):
                self.unload_loopback_modules(source_name=source_name)

        self.unload_null_sink_modules()
                
        self.unload_combined_sink_modules()

        self.pulse.close()

class PluginCtrl(Controller, threading.Thread):
    def __init__(self, thread_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event)

        self.config = config
        self.thread_event = thread_event
                    
    def monitor_output(self, plugin_name, plugin_process):
        for line in self._read_stdout(plugin_process):
            log.info('{} Plugin Output: {}'.format(plugin_name, line))
                    
    def monitor_error(self, plugin_name, plugin_process):
        for line in self._read_stderr(plugin_process):
            log.info('{} Plugin Error: {}'.format(plugin_name, line))

    def run(self):
        self._get_running_processes()
        plugins = self.config.audio_receiver.get('plugins', list())
        for plugin in plugins:
            try:
                plugin_meta     = getattr(self.config, plugin)
                plugin_name     = plugin_meta.get('name', '')
                plugin_path     = plugin_meta.get('path', '')
                plugin_restore  = plugin_meta.get('restore', True)

                if plugin_name == '' or plugin_path == '':
                    log.error('Plugin {} has not been configured'.format(plugin))
                    continue

                plugin_meta['args'] = list()
                plugin_meta['args'].append(plugin_path)

                plugin_args = plugin_meta.get('arguments', '').split(' ')
                for plugin_arg in plugin_args:
                    if plugin_arg == '':
                        continue

                    plugin_meta['args'].append(plugin_arg)

                process_cl = ' '.join(plugin_meta['args'])
                if self._running_processes.get(process_cl):
                    log.warning('{} is already running!  Attempting to kill the process...'.format(plugin_name))
                    pid = int(self._running_processes[process_cl]['PID'])
                    self._kill_running_process(pid)

                log.info('Loading plugin {} with ''{}'''.format(plugin_name, ' '.join(plugin_meta['args'])))
                plugin_process = self._execute(plugin_meta['args'])
                self._processes[plugin_name] = {
                    'process': plugin_process,
                    'meta': plugin_meta
                    }
        
                output_thread = Thread(
                    target=self.monitor_output,
                    args=(plugin_name, plugin_process)
                    )
                output_thread.daemon = True
                output_thread.start()
                self._threads[plugin_name + '_Output'] = output_thread
        
                error_thread = Thread(
                    target=self.monitor_error,
                    args=(plugin_name, plugin_process)
                    )
                error_thread.daemon = True
                error_thread.start()
                self._threads[plugin_name + '_Error'] = error_thread

            except Exception as e:
                log.exception('Failed to load plugin {} with error {}'.format(plugin, e))

        self._monitor_processes()

    def close(self):
        self._close()

class DisplayCtrl(Controller, threading.Thread):
    def __init__(self, thread_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event)

        self.config = config
        self.display_type = os.environ.get('XDG_SESSION_TYPE', None)
        self.thread_event = thread_event

        self.ctrl = None
        if self._environment == 'desktop':
            display_method = None
            log.info('Identified display type: {}'.format(self.display_type))
            
            if self.display_type == 'x11':
                display_method = XDisplay
            
            elif self.display_type == 'wayland':
                display_method = WaylandDisplay
                
            else:
                raise Exception('Display type {} is not currently supported!'.format(self.display_type))
            
            self.ctrl = display_method(self.thread_event, self.config.general.get('resolution', '1280x720'))

    def get_diagnostics(self):
        return self.ctrl.get_display_config()

    def run(self):
        while not self.thread_event.is_set():
            if self._environment == 'desktop':
                try:
                    self.ctrl.enforce_resolution()
                except:
                    log.error('Failed to enforce resolution!')

            time.sleep(5)

    def close(self):
        pass

class XDisplay(Controller):
    def __init__(self, thread_event, resolution):
        super().__init__(thread_event)
        self.resolution = resolution
        
    def get_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': dict()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\sconnected'
        display_configs_regex = r'^(?P<resolution>\d+x\d+)\s+(?P<refreshRates>.*?)$'
        
        log.debug('Running xrandr...')
        randr = self._execute(['xrandr'])
        for line in self._read_stdout(randr):
            log.debug('xrandr output: {}'.format(line))
            
            match = re.search(display_device_regex, line, re.I)
            if match:
                display_config['device'] = match.group('device')
                
            match = re.search(display_configs_regex, line, re.I)
            if match:
                resolution = match.group('resolution')
                refresh_rates = match.group('refreshRates').replace('+', '')
                if '*' in refresh_rates:
                    display_config['current_resolution'] = resolution
                for refresh_rate in refresh_rates.split():
                    refresh_rate = refresh_rate.replace('*', '')
                    if not display_config['resolutions'].get(resolution):
                        display_config['resolutions'][resolution] = [refresh_rate]
                    else:
                        display_config['resolutions'][resolution].append(refresh_rate)
            
        return display_config
        
    def enforce_resolution(self):
        display_config = self.get_display_config()
          
        if not display_config['current_resolution']:
            log.warning('There is currently no display connected: {}'.format(display_config))  
        elif display_config['current_resolution'] == self.resolution:
            log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
        else:
            res_profile = display_config['resolutions'].get(self.resolution)
            log.info('Setting resolution to {} refresh rate to {}'.format(self.resolution, max(res_profile)))

            xrandr = self._execute_managed([
                'xrandr', '--output', display_config['device'], 
                '--mode', self.resolution, '--rate', max(res_profile)
                ])

class WaylandDisplay(Controller):
    def __init__(self, thread_event, resolution):
        super().__init__(thread_event)
        self.resolution = resolution
        
    def get_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': list()
            }
        
        display_device_regex = r'^(?P<device>HDMI.*?)\s\"(?P<description>.*?)\"'
        display_configs_regex = r'^(?P<resolution>' + self.resolution + ')\spx,\s(?P<refreshRate>\d+\.\d+)'
        current_resolution_regex = r'^(?P<resolution>\d+x\d+)\spx,\s(?P<refreshRate>\d+\.\d+).*?current'
        
        randr = self._execute(['wlr-randr'])
        for line in self._read_stdout(randr):
            log.debug('wlr-randr output: {}'.format(line))
            
            match = re.search(display_device_regex, line, re.I)
            if match:
                display_config['device'] = match.group('device')
                display_config['description'] = match.group('description')
                
            match = re.search(display_configs_regex, line, re.I)
            if match:
                display_config['resolutions'].append(match.group('resolution') + '@' + match.group('refreshRate') + 'Hz')
            
            match = re.search(current_resolution_regex, line, re.I)
            if match:
                display_config['current_resolution'] = match.group('resolution') + '@' + match.group('refreshRate') + 'Hz'
                
        return display_config
        
    def enforce_resolution(self):
        display_config = self.get_display_config()
          
        if len(display_config['resolutions']) == 0:
            log.warning('There is currently no display connected: {}'.format(display_config))  
        elif display_config['current_resolution'] == max(display_config['resolutions']):
            log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
        else:
            log.info('Setting resolution to {}'.format(max(display_config['resolutions'])))
            randr = self._execute_managed([
                'wlr-randr', '--output', display_config['device'], 
                '--mode', max(display_config['resolutions'])
                ])

class ProjectMCtrl(Controller, threading.Thread):
    def __init__(self, thread_event, config, audio_ctrl, display_ctrl):
        threading.Thread.__init__(self)
        super().__init__(thread_event)
        
        self.config = config
        self.audio_ctrl = audio_ctrl
        self.display_ctrl = display_ctrl
        self.thread_event = thread_event
        
        self.projectm_path = self.config.projectm.get('path', '/opt/ProjectMSDL')
        self.projectm_restore = self.config.general.get('projectm_restore', False)        

        self.screenshot_index = 0
        self.screenshot_path = os.path.join(self.projectm_path, 'preset_screenshots')
        if not os.path.exists(self.screenshot_path):
            os.makedirs(self.screenshot_path)
        self.screenshots_enabled = self.config.projectm.get('screenshots_enabled', False)
        
        self.preset_start = 0
        self.preset_monitor = self.config.projectm.get('preset_monitor', False)
        self.preset_advanced_shuffle = self.config.projectm.get('advanced_shuffle', False)

        # ProjectM Configurations
        config_path = os.path.join(self.projectm_path, 'projectMSDL.properties')
        self.projectm_config = Config(config_path, config_header='[projectm]')

        self.preset_shuffle = self.projectm_config.projectm['projectm.shuffleenabled']
        self.preset_display_duration = self.projectm_config.projectm['projectm.displayduration']
        self.preset_path = self.projectm_config.projectm['projectm.presetpath'].replace('${application.dir}', self.projectm_path)
            
    def take_screenshot(self, preset):
        preset_name = os.path.splitext(preset)[0]
        preset_name_filtered = preset_name.split(' ', 1)[1]
        preset_screenshot_name = preset_name_filtered + '.png'
        if not preset_screenshot_name in os.listdir(self.screenshot_path):
            if self.screenshot_index > 0:
                time.sleep(self.preset_display_duration - 7)
                log.info('Taking a screenshot of {0}'.format(preset))
                screenshot_path = os.path.join(self.screenshot_path, preset_screenshot_name)
                self._execute_managed(['grim', screenshot_path])
                            
            self.screenshot_index += 1
                    
    def monitor_output(self, projectm_process):
        preset_regex = r'Displaying preset: (?P<name>.*)$'
        for line in self._read_stderr(projectm_process):
            log.debug('ProjectM Output: {0}'.format(line))
            
            try:
                match = re.search(preset_regex, line, re.I)
                if match:
                    preset = match.group('name').rsplit('/', 1)[1]
                
                    log.info('Currently displaying preset: {0}'.format(preset))
                    self.preset_start = time.time()
                
                    # Take a preview screenshot
                    if self.display_ctrl._environment == 'desktop':
                        if self.screenshots_enabled and self.audio_ctrl.source_device:
                            self.take_screenshot(preset)
            except:
                log.exception('Failed to process output: {}'.format(line))
            
    def monitor_hang(self):
        while not self.thread_event.is_set():
            if self.preset_start == 0:
                continue
            else:
                duration = time.time() - self.preset_start
                if duration >= (self.preset_display_duration + 5):
                    log.warning('The visualization has not changed in the alloted timeout!')

                    log.info('Manually transitioning to the next visualization...')
                    xautomation_process = self._execute(['xte'])
                    xautomation_process.communicate(input='key n\n')
                
            time.sleep(1)

    def index_presets(self, presets):
        index = 0
        for preset in presets:
            index += 1
            idx_pad = format(index, '06')
            preset_root, preset_name = preset.rsplit('/', 1)
            if not re.match(r'^\d{6}\s.*?\.milk', preset_name, re.I):
                preset_name_stripped = preset_name
            else:
                preset_name_stripped = preset_name.split(' ', 1)[1]
                
            dst = os.path.join(preset_root, idx_pad + ' ' + preset_name_stripped)
            try:
                os.rename(preset, dst)
            except Exception as e:
                log.error('Failed to rename preset {0}: {1}'.format(preset, e))

            
    def manage_playlist(self):
        presets = list()
        for root, dirs, files in os.walk(self.preset_path):
            for name in files:
                preset_path = os.path.join(root, name)
                if not preset_path in presets:
                    presets.append(preset_path)

        if self.preset_advanced_shuffle == True:
            random.shuffle(presets)

        self.index_presets(presets)
                
        
    def run(self, beatSensitivity=2.0):   
        self.manage_playlist()
    
        app_path = os.path.join(APP_ROOT, 'projectMSDL')
        
        projectm_meta = {
            'path': app_path,
            'args': [app_path, '--beatSensitivity=' + str(beatSensitivity)],
            'restore': self.projectm_restore
        }

        projectm_process = self._execute(projectm_meta['args'])
        self._processes['ProjectMDSL'] = {
            'process': projectm_process,
            'meta': projectm_meta
            }

        # Start thread to monitor preset output to ensure
        # there are no hangs
        output_thread = Thread(
            target=self.monitor_output,
            args=(projectm_process,)
            )
        output_thread.daemon = True
        output_thread.start()
        self._threads['ProjectMDSL_Output'] = output_thread
        
        if self.preset_monitor:
            # Start thread to trigger the next preset 
            # in the event of a hang
            hang_thread = Thread(
                target=self.monitor_hang,
                )
            hang_thread.daemon = True
            hang_thread.start()
            self._threads['ProjectMDSL_Hang'] = hang_thread

        halt_on_exit = False
        if not self.projectm_restore:
            halt_on_exit = True

        self._monitor_processes(halt_on_exit=halt_on_exit)

    def close(self):
        self._close()

class BluetoothCtrl(Controller):
    def __init__(self, thread_event):
        super().__init__(thread_event)
        
    def get_connected_devices(self):
        bluetoothctl =  self._execute(['bluetoothctl', 'devices', 'Connected'])
        for line in self._read_stdout(bluetoothctl):
            log.debug('bluetoothctl output: {}'.format(line))
            match = re.match(r'^Device\s(?P<mac_address>.*?)\s(?P<device>.*?)$', line)
            if match:
                mac_address = match.group('mac_address')
                device = match.group('device')
                    
                yield mac_address, device

    def player(self, action):
        log.info('Attempting to {} bluetooth audio'.format(action))
        self._execute_managed(['bluetoothctl', 'player.{}'.format(action)])

    def connect_device(self, source_device):
        log.info('Connecting bluetooth device: {}'.format(source_device.name))
        self._execute_managed(['bluetoothctl', 'connect', source_device.mac_address])
                
    def disconnect_device(self, source_device):
        log.info('Disconnecting bluetooth device: {}'.format(source_device.name))
        self._execute_managed(['bluetoothctl', 'disconnect', source_device.mac_address])