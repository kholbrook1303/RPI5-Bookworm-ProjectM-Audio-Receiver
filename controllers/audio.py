import logging
import os
import re
import time
import threading

from pulsectl import Pulse, PulseVolumeInfo
from pulsectl.pulsectl import PulseOperationFailed

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config
from lib.constants import DeviceCatalog, PluginDevice
from lib.common import execute, execute_managed

log = logging.getLogger()

PROJECTM_MONO = 1
PROJECTM_STEREO = 2


class AudioCtrl(Controller, threading.Thread):
    """Controller for managing PulseAudio devices and profiles.
    @param thread_event: Event to signal when the thread should stop.
    @param config: Configuration object containing audio settings.
    """
    def __init__(self, thread_event, config):
        super().__init__(thread_event, config)
        threading.Thread.__init__(self)
        
        self.audio_mode             = self._config.audio_ctrl.get('audio_mode', 'automatic')
        self.io_device_mode         = self._config.audio_ctrl.get('io_device_mode', 'aux')
        self.allow_multiple_sinks   = self._config.audio_ctrl.get('allow_multiple_sinks', True)
        self.allow_multiple_sources = self._config.audio_ctrl.get('allow_multiple_sources', True)

        self.audio_listener_thread  = None
        self.audio_listener_enabled = self._config.audio_ctrl.get('audio_listener_enabled', True)

        config_path = os.path.join(APP_ROOT, 'conf')

        self.audio_cards_config     = Config(os.path.join(config_path, 'audio_cards.conf'))
        self.audio_plugins_config   = Config(os.path.join(config_path, 'audio_plugins.conf'))
        self.audio_sinks_config     = Config(os.path.join(config_path, 'audio_sinks.conf'))
        self.audio_sources_config   = Config(os.path.join(config_path, 'audio_sources.conf'))

        self.sink_device            = None
        self.source_device          = None
        self.combined_sink_devices  = list()
        
        self.devices                = DeviceCatalog()
        self.bluetoothCtrl          = BluetoothManager()

        self.pulse = Pulse()

        # Load null sink
        self.ar_sink = 'platform-project_mar.stereo'
        self.pulse.module_load('module-null-sink', [
            'sink_name=' + self.ar_sink,
            'sink_properties=device.description=ProjectMAR-Sink-Monitor'
            ])

        # Set null sink monitor as default
        self.pulse.source_default_set('platform-project_mar.stereo.monitor')
        
    """Get raw diagnostic information from PulseAudio"""
    def get_raw_diagnostics(self):
        """Yield diagnostic information for sinks, sources, modules, etc"""

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

    """Get diagnostic information for PulseAudio devices"""
    def get_device_diagnostics(self):
        self.update_sink_devices()
        self.update_source_devices()
        self.update_bluetooth_devices()
        self.update_plugin_devices()

        return self.devices.__dict__

    """Get module arguments from PulseAudio modules.
    @param module: The PulseAudio module object to extract arguments from.
    """
    def get_module_arguments(self, module):
        module.args = dict()
        if hasattr(module, 'argument'):
            if module.argument:
                args = module.argument.split(' ')
                for arg in args:
                    if '=' in arg:
                        key, val = arg.split('=', 1)
                        module.args[key] = val

    """Get modules by name from PulseAudio.
    @param module_name: The name of the module to search for.
    """
    def get_modules(self, module_name=None):
        modules = list()
        
        for module in self.pulse.module_list():
            try:
                self.get_module_arguments(module)
                if module.name == module_name:
                    modules.append(module)
            except Exception as e:
                log.exception('Failed to process argument %s: %s', getattr(module, 'argument', None), e)

        return modules

    """Check if a module is loaded by name.
    @param module_name: The name of the module to check.
    """
    def module_loaded(self, module_name):
        modules = self.get_modules(module_name)
        if len(modules) > 0:
            return True

        return False
           
    """Unload loopback modules based on sink and source names.
    @param sink_name: The name of the sink to unload loopback modules for.
    @param source_name: The name of the source to unload loopback modules for.
    """
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

    def sink_busy(self, sink_name):
        try:
            sink = self.pulse.get_sink_by_name(sink_name)
            sink_inputs = self.pulse.sink_input_list()
            for inp in sink_inputs:
                if inp.sink == sink.index:
                    log.warning(f'Something is actively using {sink_name}')
                    return True  # Something is actively using this sink
        except:
            pass

        return False

    def route_input_to_output_via_null_sink(self, source_name, sink_name):
        null_sink_name = sink_name.split('.', 1)[0] + '_null_sink'
        null_sink_monitor = f"{null_sink_name}.monitor"

        # Step 1: Ensure null sink is loaded
        # if not self.module_loaded("module-null-sink"):
        self.pulse.module_load('module-null-sink', [
            f'sink_name={null_sink_name}',
            'sink_properties=device.description=ProjectMAR-Sink-Monitor'
        ])
        log.info(f"Loaded null sink: {null_sink_name}")
        # else:
        #     log.debug("Null sink already loaded")

        # Step 2: Route input → null sink
        if not self.loopback_exists(source_name, null_sink_name):
            self.load_loopback_module(source_name, null_sink_name)
            log.info(f"Routed {source_name} → {null_sink_name}")

        # Step 3: Route null sink → hardware output sink
        if not self.loopback_exists(null_sink_monitor, sink_name):
            self.load_loopback_module(null_sink_monitor, sink_name)
            log.info(f"Routed {null_sink_monitor} → {sink_name}")


    def same_card(self, source_name, sink_name):
        try:
            source = self.pulse.get_source_by_name(source_name)
            sink = self.pulse.get_sink_by_name(sink_name)

            src_card = source.proplist.get('alsa.card')
            sink_card = sink.proplist.get('alsa.card')

            return src_card and sink_card and src_card == sink_card
        except Exception:
            return False

    def loopback_exists(self, source_name, sink_name):
        for module in self.get_modules('module-loopback'):
            if module.args.get('source') == source_name and module.args.get('sink') == sink_name:
                return True

        return False

    def loopback_params_are_valid(self, source_name, sink_name):
        sources = [s.name for s in self.pulse.source_list()]
        sinks = [s.name for s in self.pulse.sink_list()]
        return source_name in sources and sink_name in sinks

    """Load a loopback module for a specific source and sink.
    @param source_name: The name of the source to load the loopback module for.
    @param sink_name: The name of the sink to load the loopback module for.
    """
    def load_loopback_module(self, source_name, sink_name):
        # if self.same_card(source_name, sink_name):
        #     log.warning(f'Unable to route {source_name} to {sink_name} as they belong to the same card');
        #     return

        #self.stop_audio_stream()

        # log.info('Loading module-loopback for source {} sink {}'.format(source_name, sink_name))
        # if self.loopback_params_are_valid(source_name, sink_name):
        #     self.pulse.module_load('module-loopback', [
        #         'source=' + source_name,
        #         'sink=' + sink_name,
        #         'latency_msec=20',
        #         'source_dont_move=true',
        #         'sink_dont_move=true'
        #         ])
        # else:
        #     log.warning(f"Invalid loopback parameters: source={source_name}, sink={sink_name} — skipping")
        #self.create_audio_stream()

        log.info('Loading module-loopback for source {} sink {}'.format(source_name, sink_name))
        self.pulse.module_load('module-loopback', [
            'source=' + source_name,
            'sink=' + sink_name,
            'latency_msec=20',
            'source_dont_move=true',
            'sink_dont_move=true'
            ])

    """Unload null sink modules"""
    def unload_null_sink_modules(self):
        for module in self.get_modules('module-null-sink'):
            log.info('Unloading null sink {}'.format(module.name))
            self.pulse.module_unload(module.index)

    """Unload combined sink modules"""
    def unload_combined_sink_modules(self):
        for module in self.get_modules('module-combine-sink'):
            log.info('Unloading combined sink {}'.format(module.name))
            self.pulse.module_unload(module.index)

    """Load a combined sink module with specified sinks.
    @param combined_sinks: A list of sink names to combine.
    """
    def load_combined_sinks(self, combined_sinks):
        log.info('Loading combined sink for {}'.format(combined_sinks))
        self.pulse.module_load('module-combine-sink', [
            'slaves=' + ','.join(combined_sinks)
            ])

    """Set the volume for a sink input device.
    @param sink_input_device: The PulseAudio sink input device to set the volume for.
    @param sink_input_channels: The number of channels for the sink input device.
    @param sink_input_volume: The volume level to set for the sink input device.
    """
    def set_sink_input_volume(self, sink_input_device, sink_input_channels, sink_input_volume):
        sink_input_volume_info = PulseVolumeInfo(sink_input_volume, sink_input_channels)
        log.info('Setting sink input {} volume to {}'.format(sink_input_device.name, sink_input_volume_info))
        self.pulse.sink_input_volume_set(sink_input_device.meta.index, sink_input_volume_info)
    
    """Control a plugin device.
    @param plugin_device: The PluginDevice object representing the plugin device.
    @param plugin_volume: The volume level to set for the plugin device.
    """
    def control_plugin_device(self, plugin_device, plugin_volume):
        log.info('Identified a new plugin device: {}'.format(plugin_device.name))
        
        plugin_channels = len(plugin_device.meta.volume.values)
        self.set_sink_input_volume(plugin_device, plugin_channels, plugin_volume)

    """Update plugin devices by checking PulseAudio sink inputs"""
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
                    elif app == 'vlc':
                        plugin_device = PluginDevice(app, plugin.index, plugin)
                        plugin_device.device = 'vlc'
                    else:
                        plugin_device = PluginDevice(app, plugin.index, plugin)
                        plugin_device.device = 'generic'
                        log.warning('Unable to identify plugin app: {} device: {}'.format(app, plugin.__dict__))

                    log.info('Found plugin device: {} {}'.format(plugin_device.name, plugin_device.device))
                    self.devices.plugin_devices[app] = plugin_device

    """Update connected Bluetooth devices"""
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

    """Set the volume for a sink device.
    @param sink_device: The PulseAudio sink device to set the volume for.
    @param sink_volume: The volume level to set for the sink device.
    """
    def set_sink_volume(self, sink_device, sink_volume):
        try:
            sink_channels = len(sink_device.volume.values)
            sink_volume = PulseVolumeInfo(sink_volume, sink_channels)
            
            log.info('Setting sink {} volume to {}'.format(sink_device.name, sink_volume))
            self.pulse.sink_volume_set(sink_device.index, sink_volume)

        except:
            log.error('Failed to set sink {} volume'.format)

    """Update sink devices by checking PulseAudio sinks"""
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
                    sink_volume = self._config.automatic.get('sink_device_volume', 1.0)
                elif self.audio_mode == 'manual':
                    sink_volume = self._config.manual.get('combined_sink_volume', 1.0)

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
    
    """Control a sink device.
    @param sink_device: The PulseAudio sink device to control.
    @param sink_volume: The volume level to set for the sink device.
    """
    def control_sink_device(self, sink_device, sink_volume):
        log.info('Identified a new sink device: {}'.format(sink_device.name))
        self.pulse.sink_default_set(sink_device.name)
        self.set_sink_volume(sink_device, sink_volume)

    """Get supported sink devices based on the audio mode"""
    def get_supported_sink_devices(self):
        if self.audio_mode == 'automatic':
            for sink_name, sink_device in self.devices.sink_devices.items():
                if sink_device.active:
                    continue

                sink_device_type = self._config.automatic.get('sink_device_type', None)
                if sink_device_type and sink_device.type != sink_device_type:
                    log.debug('Skipping sink {} as it is not {}'.format(sink_name, sink_device_type))
                    continue

                sink_volume = self._config.automatic.get('sink_device_volume', 1.0)
                if not isinstance(sink_volume, float):
                    log.warning('Sink {} does not have a float value for volume'.format(sink_name))
                    sink_volume = 1.0
                    
                supported_sink = {
                    'device': sink_device,
                    'volume': sink_volume
                    }

                yield supported_sink

        elif self.audio_mode == 'manual':
            for sink_id in self.audio_sinks_config.general.get('audio_sinks', list()):
                sink_meta = getattr(self.audio_sinks_config, sink_id)
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

    """Update source devices by checking PulseAudio sources"""
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
                    # if self.same_card(source.name, self.ar_sink):
                    #     log.info(f"Routing {source.name} -> {self.ar_sink} via null sink (same card)")
                    #     self.route_input_to_output_via_null_sink(source.name, self.ar_sink)
                    # else:
                    #     self.load_loopback_module(source.name, self.ar_sink)

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

    """Set the volume for a source device.
    @param source_device: The PulseAudio source device to set the volume for.
    @param volume: The volume level to set for the source device.
    """
    def set_source_volume(self, source_device, volume):
        try:
            source_channels = len(source_device.volume.values)
            source_volume = PulseVolumeInfo(volume, source_channels)

            log.info('Setting source {} volume to {}'.format(source_device.name, source_volume))
            self.pulse.source_volume_set(source_device.index, source_volume)

        except:
            log.error('Failed to set source {} volume'.format(source_device.name))
            
    """Control a source device.
    @param source_device: The PulseAudio source device to control.
    @param source_volume: The volume level to set for the source device.
    """
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
                       
                    # if self.same_card(source_device.name, sink.name):
                    #     log.info(f"Routing {source_device.name} -> {sink.name} via null sink (same card)")
                    #     self.route_input_to_output_via_null_sink(source_device.name, sink.name)
                    # else:
                    #     self.load_loopback_module(source_device.name, sink.name)
                    self.load_loopback_module(source_device.name, sink.name)

            elif self.sink_device and source_device.type == 'mic':
                # if self.same_card(source_device.name, self.ar_sink):
                #     log.info(f"Routing {source_device.name} -> {self.ar_sink} via null sink (same card)")
                #     self.route_input_to_output_via_null_sink(source_device.name, self.ar_sink)
                # else:
                #     self.load_loopback_module(source_device.name, self.ar_sink)
                self.load_loopback_module(source_device.name, self.ar_sink)

    """Get supported source devices based on the audio mode"""
    def get_supported_source_devices(self):
        if self.audio_mode == 'automatic':
            for source_name, source_device in self.devices.source_devices.items():
                if source_device.active:
                    continue

                source_device_type = self._config.automatic.get('source_device_type', None)
                if source_device_type and source_device.type != source_device_type:
                    log.debug('Skipping source {} as it is not {}'.format(source_name, source_device_type))
                    continue

                source_volume = self._config.automatic.get('source_device_volume', .85)
                if not isinstance(source_volume, float):
                    log.warning('Source {} does not have a float value for volume'.format(source_name))
                    source_volume = .85
                    
                supported_source = {
                    'device': source_device,
                    'volume': source_volume
                    }

                yield supported_source

        elif self.audio_mode == 'manual':
            for source_id in self.audio_sources_config.general.get('audio_sources', list()):
                source_meta = getattr(self.audio_sources_config, source_id)
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

    """Update card devices by checking PulseAudio cards"""
    def update_card_devices(self):
        cards = self.pulse.card_list()

        # Check for any disconnected cards
        for card_name in list(self.devices.cards):
            if not any (card_name == card.name for card in cards):
                log.warning('Card {} has been disconnected'.format(card_name))
                self.devices.cards.pop(card_name)

        for card in cards:
            if self.devices.cards.get(card.name):
                continue
            
            card.active = False
            card.device = 'pa'
            self.devices.cards[card.name] = card

    """Control a card device.
    @param card: The PulseAudio card device to control.
    @param card_profile: The profile name to set for the card device.
    """
    def control_card_device(self, card, card_profile):
        if card.profile_active.name == card_profile:
            log.info('Profile {} is already set for card {} '.format(card_profile, card.name))
        else:
            log.info('Setting {} profile for card {} '.format(card_profile, card.name))
            self.pulse.card_profile_set(card, card_profile)

    """Get supported cards based on the audio mode"""
    def get_supported_cards(self):
        if self.audio_mode == 'automatic':      # Need to evaluate additonal options for automatic card profile configuration
            card_profile_types = self._config.automatic.get('card_profile_types', list())
            card_profile_modes = self._config.automatic.get('card_profile_modes', list())

            if len(card_profile_types) == 0 or len(card_profile_modes) == 0:
                log.warning('Skipping card control as there are missing configurations in projectMAR.conf')
                return

            for card_name, card in self.devices.cards.items():
                if card.active:
                    continue
                
                supported_card = None
                for card_profile_type in card_profile_types:
                    for card_profile in card.profile_list:
                        if card_profile.name == 'off':
                            continue

                        profile_type = None
                        profile_mode = None
                        for mode in card_profile.name.split('+'):

                            try:

                                if ':' in mode:
                                    profile_mode = mode.split(':')[1]

                                if card_profile.n_sources == 1 and card_profile.n_sinks == 1:
                                    profile_type = 'input-output'

                                elif card_profile.n_sources == 0 and card_profile.n_sinks == 1:
                                    profile_type = 'input'

                                elif card_profile.n_sources == 1 and card_profile.n_sinks == 0:
                                    profile_type = 'output'

                            except:
                                log.exception('No logic to handle mode {}'.format(mode))

                        if not profile_type or not profile_mode:
                            continue
                        elif profile_type != card_profile_type:
                            continue
                        elif profile_mode not in card_profile_modes:
                            continue
                        else:
                            supported_card = {
                                'card'      : card,
                                'profile'   : card_profile.name
                                }

                            break

                    if supported_card:
                        break

                if supported_card:
                    yield supported_card

        elif self.audio_mode == 'manual':
            for card_id in self.audio_cards_config.general.get('audio_cards', list()):
                card_meta = getattr(self.audio_cards_config, card_id)
                card_name = card_meta['name']
                if not card_name:
                    continue

                if self.devices.cards.get(card_name):
                    card = self.devices.cards[card_name]
                    if card.active:
                        continue

                    for card_profile in card.profile_list:
                        if card_profile.name == card_meta['profile']:
                            supported_card = {
                                'card'      : card,
                                'profile'   : card_meta['profile']
                                }

                            yield supported_card

    """Handle PulseAudio devices by updating active/inactive devices and controlling them"""
    def handle_devices(self):
        self.update_card_devices()

        for supported_card in self.get_supported_cards():
            card = supported_card['card']
            card_profile = supported_card['profile']

            self.control_card_device(card, card_profile)
            card.active = True

        self.update_sink_devices()

        active_sinks = list()
        for sink_device in self.devices.sink_devices.values():
            if sink_device.active:
                active_sinks.append(sink_device)
        
        inactive_sinks = list()
        for supported_sink in self.get_supported_sink_devices():
            inactive_sinks.append(supported_sink)

        total_sinks = len(active_sinks) + len(inactive_sinks)
        if self.allow_multiple_sinks and total_sinks > 1 and (len(inactive_sinks) > 0 or len(self.combined_sink_devices) != total_sinks):
            if self.module_loaded('module-combine-sink'):
                log.info('Found an active module-combine-sink module loaded!')
                self.unload_combined_sink_modules()

            self.combined_sink_devices.clear()
            for sink_device in active_sinks:
                self.combined_sink_devices.append(sink_device.name)
            for supported_sink in inactive_sinks:
                supported_sink['device'].active = True
                self.combined_sink_devices.append(supported_sink['device'].name)

            self.load_combined_sinks(self.combined_sink_devices)
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
        #self.update_plugin_devices()

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

            #self.control_plugin_device(plugin_device, 1.0)
            plugin_device.active = True

    """Run the audio controller thread to handle PulseAudio devices"""
    def run(self):
        while not self._thread_event.is_set():
            try:
                self.handle_devices()

            except PulseOperationFailed:
                log.exception('Failed to handle Pulseaudio devices... Restarting Pulseaudio')
                self.pulse = Pulse()

            except Exception as e:
                log.exception('Failed to handle Pulseaudio devices!')

            finally:
                time.sleep(2)

    def reconnect(self):
        self.sink_device            = None
        self.source_device          = None
        self.combined_sink_devices  = list()
        
        self.devices                = DeviceCatalog()
        self.pulse                  = Pulse() 

        # Load null sink
        self.ar_sink = 'platform-project_mar.stereo'
        self.pulse.module_load('module-null-sink', [
            'sink_name=' + self.ar_sink,
            'sink_properties=device.description=ProjectMAR-Sink-Monitor'
            ])

        # Set null sink monitor as default
        self.pulse.source_default_set('platform-project_mar.stereo.monitor')

    """Close the PulseAudio connection and unload modules"""
    def close(self):
        # self.stop_audio_stream()

        if self.audio_listener_thread:
            self.audio_listener_thread.join()
            self.audio_listener_thread.close()

        for source_name, source_device in self.devices.source_devices.items():
            if not source_device.active:
                continue

            if not source_name.startswith('bluez_source'):
                self.unload_loopback_modules(source_name=source_name)

        self.unload_null_sink_modules()
                
        self.unload_combined_sink_modules()

        self.pulse.close()
        
class BluetoothManager:
    """Controller for managing Bluetooth devices"""
    def __init__(self):
        pass
        
    """Get connected Bluetooth devices using bluetoothctl"""
    def get_connected_devices(self):
        bluetoothctl =  execute('bluetoothctl', 'bluetoothctl', ['bluetoothctl', 'devices', 'Connected'])
        for line in iter(bluetoothctl.process.stdout.readline, ''):
            log.debug('bluetoothctl output: {}'.format(line))
            match = re.match(r'^Device\s(?P<mac_address>.*?)\s(?P<device>.*?)$', line)
            if match:
                mac_address = match.group('mac_address')
                device = match.group('device')
                    
                yield mac_address, device

    """Execute a player command for a Bluetooth device"""
    def player(self, action):
        log.info('Attempting to {} bluetooth audio'.format(action))
        execute_managed(['bluetoothctl', 'player.{}'.format(action)])

    """Connect a Bluetooth device using bluetoothctl.
    @param source_device: The PluginDevice object representing the Bluetooth device to connect.
    """
    def connect_device(self, source_device):
        log.info('Connecting bluetooth device: {}'.format(source_device.name))
        execute_managed(['bluetoothctl', 'connect', source_device.mac_address])
         
    """Disconnect a Bluetooth device using bluetoothctl.
    @param source_device: The PluginDevice object representing the Bluetooth device to disconnect.
    """
    def disconnect_device(self, source_device):
        log.info('Disconnecting bluetooth device: {}'.format(source_device.name))
        execute_managed(['bluetoothctl', 'disconnect', source_device.mac_address])
