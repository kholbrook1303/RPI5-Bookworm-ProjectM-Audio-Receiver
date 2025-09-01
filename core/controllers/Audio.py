import logging
import os
import random
import pyudev
import re
import time
import threading
import vlc

from pulsectl import Pulse

from lib.abstracts import Controller
from lib.config import APP_ROOT, Config
from lib.constants import DeviceCatalog
from lib.common import execute, execute_managed

log = logging.getLogger()

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

        self.audio_listener_thread  = None
        self.audio_listener_enabled = self._config.audio_ctrl.get('audio_listener_enabled', True)

        self.sink_device            = None
        self.source_device          = None
        self.sink_devices           = list()
        
        self.devices                = DeviceCatalog()

        self.ar_sink                = 'platform-project_mar.stereo'

        config_path = os.path.join(APP_ROOT, 'conf')
        self.supported_cards = self.load_audio_config(config_path, 'audio_cards.conf')
        self.supported_sinks = self.load_audio_config(config_path, 'audio_sinks.conf')
        self.supported_sources = self.load_audio_config(config_path, 'audio_sources.conf')


    """Load audio configuration from a specified path and file.
    @param config_path: The path to the configuration directory.
    @param config_file: The name of the configuration file to load.
    """
    def load_audio_config(self, config_path, config_file):
        supported_dict = dict()
        config = Config(os.path.join(config_path, config_file))
        for item_id in config.general.get(config_file.split('.')[0], list()):
            try:
                item_meta = getattr(config, item_id)
                item_name = item_meta['name']
                if not item_name:
                    continue

                supported_dict[item_name] = item_meta
            except:
                pass

        return supported_dict

    """Execute a PulseAudio method with optional arguments.
    @param func: The PulseAudio method to call.
    @param args: Optional arguments to pass to the method.
    """
    def pulse_audio_callback(self, func, args=None):
        with Pulse('ProjectMAR PulseAudio Callback') as pulse:
            method = getattr(pulse, func)
            if isinstance(args, (list, tuple)):
                return method(*args)
            elif args is not None:
                return method(args)
            else:
                return method()
        
    """Get raw diagnostic information from PulseAudio"""
    def get_raw_diagnostics(self):
        """Yield diagnostic information for sinks, sources, modules, etc"""

        log.info('Getting sinks: sink_list()')
        for sinkInfo in self.pulse_audio_callback('sink_list'):
            log.info('Found sink {}'.format(sinkInfo.name))
            yield 'sinks', sinkInfo.__dict__
            
        log.info('Getting sources: source_list()')
        for sourceInfo in self.pulse_audio_callback('source_list'):
            log.info('Found sink {}'.format(sourceInfo.name))
            yield 'sources', sourceInfo.__dict__
            
        log.info('Getting sink inputs: sink_input_list()')
        for sinkInputInfo in self.pulse_audio_callback('sink_input_list'):
            log.info('Found sink input {}'.format(sinkInputInfo.name))
            yield 'sink_inputs', sinkInputInfo.__dict__
    
        log.info('Getting source outputs: source_output_list()')
        for sourceOutputInfo in self.pulse_audio_callback('source_output_list'):
            log.info('Found sink input {}'.format(sourceOutputInfo.name))
            yield 'source_outputs', sourceOutputInfo.__dict__
            
        log.info('Getting modules: module_list()')
        for moduleInfo in self.pulse_audio_callback('module_list'):
            log.info('Found module {}'.format(moduleInfo.name))
            yield 'modules', moduleInfo.__dict__
            
        log.info('Getting cards: card_list()')
        for cardInfo in self.pulse_audio_callback('card_list'):
            log.info('Found card {}'.format(cardInfo.name))
            yield 'cards', cardInfo.__dict__
            
        log.info('Getting clients: client_list()')
        for clientInfo in self.pulse_audio_callback('client_list'):
            log.info('Found client {}'.format(clientInfo.name))
            yield 'clients', clientInfo.__dict__

    """Set the volume for a device.
    @param device_type: The PulseAudio device type
    @param device: The PulseAudio device to set the volume for.
    @param device_volume: The volume level to set for the device.
    """
    def set_volume(self, device_type, device, device_volume):
        try:
            channels = len(device.volume.values)
            
            log.info('Setting sink {} volume to {}'.format(device.name, device_volume))
            self.pulse_audio_callback('volume_set_all_chans', [device, device_volume])

        except Exception as e:
            log.exception('Failed to set sink {} volume'.format(e))

    """Set the default device
    @param device_type: The PulseAudio device type
    @param device: The PulseAudio device
    """
    def set_default(self, device_type, device_name):
        self.pulse_audio_callback(f'{device_type}_default_set', device_name)

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
        
        for module in self.pulse_audio_callback('module_list'):
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
                self.pulse_audio_callback('module_unload', module.index)

    """Load a loopback module for a specific source and sink.
    @param source_name: The name of the source to load the loopback module for.
    @param sink_name: The name of the sink to load the loopback module for.
    """
    def load_loopback_module(self, source_name, sink_name):
        log.info('Loading module-loopback for source {} sink {}'.format(source_name, sink_name))
        self.pulse_audio_callback('module_load', [
            'module-loopback',
            f'source={source_name} sink={sink_name} latency_msec=20 source_dont_move=true sink_dont_move=true'
        ])

    """Unload null sink modules"""
    def unload_null_sink_modules(self):
        for module in self.get_modules('module-null-sink'):
            log.info('Unloading null sink {}'.format(module.name))
            self.pulse_audio_callback('module_unload', module.index)

    """Unload combined sink modules"""
    def unload_combined_sink_modules(self):
        for module in self.get_modules('module-combine-sink'):
            log.info('Unloading combined sink {}'.format(module.name))
            self.pulse_audio_callback('module_unload', module.index)

    """Load a combined sink module with specified sinks.
    @param combined_sinks: A list of sink names to combine.
    """
    def load_combined_sinks(self, combined_sinks):
        log.info('Loading combined sink for {}'.format(combined_sinks))
        self.pulse_audio_callback('module_load', [
            'module-combine-sink',
            'slaves=' + ','.join(combined_sinks)
            ])

    """Update sink devices from PulseAudio"""
    def setup_combined_sink(self):
        log.info('Setting up combined sink for PulseAudio')
        sinks = [sink.name for sink in self.devices.sink.values()]
        
        load_sink = False
        combined_sinks = self.get_modules('module-combine-sink')
        if len(combined_sinks) > 0:
            combined_sink_slaves = combined_sinks[0].args["slaves"].split(',')

            log.info('Found an active module-combine-sink module loaded!')
            log.info('Found {} combined sinks with {} slaves'.format(len(combined_sinks), len(combined_sink_slaves)))
            if any(sink not in combined_sink_slaves for sink in sinks):
                self.unload_combined_sink_modules()
                load_sink = True
                time.sleep(0.5)
        else:
            load_sink = True

        log.info(f'Found {len(sinks)} sinks: {sinks} reload combined sink: {load_sink}')
        if len(sinks) > 1 and load_sink:
            self.load_combined_sinks(sinks)
            self.sink_device = 'combined'

            self.pulse_audio_callback('sink_default_set', 'combined')

    """Add a new card device to the catalog and set its profile.
    @param card: The PulseAudio card object to add.
    """
    def add_card_device(self, card):
        if card.name.startswith('bluez_source'):
            return

        log.info('Found a new card device: {}'.format(card.name))

        card_profile = None
        if self.audio_mode == 'automatic':
            card_profile_types = self._config.automatic.get('card_profile_types', list())
            card_profile_modes = self._config.automatic.get('card_profile_modes', list())

            if len(card_profile_types) == 0 or len(card_profile_modes) == 0:
                log.warning('Skipping card control as there are missing configurations in projectMAR.conf')
                return

            # Traverse backwards to prioritize input/output devices
            for profile in reversed(card.profile_list):
                if profile.name == 'off':
                    continue
                
                identified = False
                profile_defs = profile.name.split('+')
                for profile_def in profile_defs:
                    if not ':' in profile_def:
                        log.warning(f'Undefined profile type {profile_def}')
                        continue

                    profile_type, profile_mode = profile_def.split(':')

                    if profile_type in card_profile_types and profile_mode in card_profile_modes:
                        card_profile = profile.name
                        identified = True

                if identified:
                    break

        elif self.audio_mode == 'manual':
            if self.supported_cards.get(card.name):
                for card_profile in card.profile_list:
                    card_meta = self.supported_cards[card.name]
                    if card_profile.name == card_meta['profile']:
                        card_profile = card_meta['profile']
            
        if not card_profile:
            return

        if card.profile_active.name == card_profile:
            log.info('Profile {} is already set for card {} '.format(card_profile, card.name))
        else:
            log.info('Setting {} profile for card {} '.format(card_profile, card.name))
            self.pulse_audio_callback('card_profile_set', [card, card_profile])

        card.device = 'pa'
        self.devices.card[card.index] = card

        return

    """Add a new sink device to the catalog and set its properties.
    @param sink: The PulseAudio sink object to add.
    """
    def add_sink_device(self, sink):
        if sink.name == self.ar_sink:
            return

        if sink.name == 'combined':
            return

        log.info('Found a new sink device: {}'.format(sink.name))

        sink_type = None
        if 'Built-in Audio' in sink.description:
            sink_type = 'internal'
        else:
            sink_type = 'external'

        sink_volume = None

        if self.audio_mode == 'automatic':
            sink_device_type = self._config.automatic.get('sink_device_type', None)
            if sink_device_type and sink_type != sink_device_type:
                log.debug('Skipping sink {} as it is not {}'.format(sink.name, sink_device_type))
                return

            sink_volume = self._config.automatic.get('sink_device_volume', 1.0)
            if not isinstance(sink_volume, float):
                log.warning('Sink {} does not have a float value for volume'.format(sink.name))
                sink_volume = 1.0

        if self.audio_mode == 'manual':
            if self.supported_sinks.get(sink.name):
                sink_meta = self.supported_sinks[sink.name]
                if sink_meta['type'] and sink_type != sink_meta['type']:
                    log.debug('Skipping sink {} as it is not {}'.format(sink_type, sink_meta['type']))
                    return
                    
                sink_volume = sink_meta.get('volume', 1.0)
                if not isinstance(sink_volume, float):
                    log.warning('Sink {} does not have a float value for volume'.format(sink.name))
                    sink_volume = 1.0

        if sink.proplist.get('alsa.card') and sink.proplist.get('alsa.long_card_name'):
            alsa_card = sink.proplist['alsa.card']
            alsa_name = sink.proplist['alsa.long_card_name']
            log.debug('Found sink ALSA card {} {}'.format(alsa_name, alsa_card))

            if not self.devices.sink_cards.get(alsa_card):
                self.devices.sink_cards[alsa_card] = alsa_name
        
        self.set_default('sink', sink.name)
        self.set_volume('sink', sink, sink_volume)
        self.sink_device = sink.name

        sink.type = sink_type
        sink.device = 'pa'
        self.devices.sink[sink.index] = sink

        return

    """Add a new source device to the catalog and manage the audio routing.
    @param source: The PulseAudio source object to add.
    """
    def add_source_device(self, source):
        if source.name.startswith('bluez_source'):
            return

        log.debug('Found source device: {} {}'.format(source.name, source))

        if source.name.startswith('alsa_output'):
            loopback_modules = self.get_modules('module-loopback')
            if not any(lm.args['source'] == source.name and lm.args['sink'] == self.ar_sink for lm in loopback_modules):
                self.load_loopback_module(source.name, self.ar_sink)

            log.debug('Source device: {} is not supported'.format(source.name))
            self.devices.unsupported_sources[source.name] = source
            return

        if source.name.endswith('.monitor'):
            log.debug('Source device: {} is not supported'.format(source.name))
            self.devices.unsupported_sources[source.name] = source
            return

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

        if self.audio_mode == 'automatic':
            source_device_type = self._config.automatic.get('source_device_type', None)
            if source_device_type and source_type != source_device_type:
                log.debug('Skipping source {} as it is not {}'.format(source.name, source_device_type))
                return

            source_volume = self._config.automatic.get('source_device_volume', .85)
            if not isinstance(source_volume, float):
                log.warning('Source {} does not have a float value for volume'.format(source.name))
                source_volume = .85

        if self.audio_mode == 'manual':
            if self.supported_sources.get(source.name):
                source_meta = self.supported_sources[source.name]

                source_device_type = source_meta['type']
                if source_device_type and source_type != source_device_type:
                    log.debug('Skipping source {} as it is not {}'.format(source_meta['name'], source_device_type))
                    return

                source_volume = source_meta.get('volume', .85)
                if not isinstance(source_volume, float):
                    log.warning('Source {} does not have a float value for volume'.format(source.name))
                    source_volume = .85

        self.set_volume('source', source, source_volume)

        self.unload_loopback_modules(source_name=source.name)

        if self.sink_device and source_type == 'aux':
            for sink in self.devices.sink.values():
                self.load_loopback_module(source.name, sink.name)

        elif self.sink_device and source_type == 'mic':
            self.load_loopback_module(source.name, self.ar_sink)

        source.type = source_type
        source.device = 'pa'
        self.devices.source[source.index] = source

        return 

    """Remove a card device from the catalog.
    @param card: The PulseAudio card object to remove.
    """
    def remove_card_device(self, card):
        log.warning('Card {} has been disconnected'.format(card.name))
        self.devices.card.pop(card.index, None)

    def remove_sink_device(self, sink):
        log.warning('Sink device {} has been disconnected'.format(sink.name))

        self.devices.sink.pop(sink.index, None)

        if self.sink_device == sink.name:
            self.sink_device = None
        
        if sink.proplist.get('alsa.card') and sink.proplist.get('alsa.long_card_name'):
            alsa_card = sink.proplist['alsa.card']
            alsa_name = sink.proplist['alsa.long_card_name']

            if self.devices.sink_cards.get(alsa_card):
                self.devices.sink_cards.pop(alsa_card)

    """Remove a source device from the catalog and unload its loopback modules.
    @param source: The PulseAudio source object to remove.
    """
    def remove_source_device(self, source):
        if source.name.startswith('bluez_source'):
            return

        log.warning('Source device {} has been disconnected'.format(source.name))
        self.unload_loopback_modules(source_name=source.name)
        self.devices.source.pop(source.index, None)

    """Setup PulseAudio devices and load the null sink."""
    def setup_devices(self):
        # Load null sink
        self.pulse_audio_callback('module_load', [
            'module-null-sink',
            f'sink_name={self.ar_sink} sink_properties=device.description=ProjectMAR-NULL-Sink'
            ])

        # Set null sink monitor as default
        self.pulse_audio_callback('source_default_set', 'platform-project_mar.stereo.monitor')

        for card in self.pulse_audio_callback('card_list'):
            self.add_card_device(card)

        for sink in self.pulse_audio_callback('sink_list'):
            self.add_sink_device(sink)

        self.setup_combined_sink()

        for source in self.pulse_audio_callback('source_list'):
            self.add_source_device(source)

    """Handle PulseAudio events for device changes.
    @param event: The PulseAudio event object containing information about the device change.
    """
    def pulse_event_handler(self, event):
        device      = None
        device_type = event.facility._value
        try:
            match event.t:
                case 'new':
                    log.info(f'PulseAudio new event for device type: {device_type} index: {event.index}')

                    for pulse_item in self.pulse_audio_callback(f'{device_type}_list'):
                        if event.index == pulse_item.index:
                            device = pulse_item
                            break

                    if not device:
                        log.warning(f'Unable to find PulseAudio {device_type} with index {event.index} for event {event.t}')

                    elif device.name == 'combined':
                        pass

                    elif device.name.startswith('bluez_source'):
                        pass

                    else:
                        getattr(self, f'add_{device_type}_device')(device)

                        if device_type == 'sink':
                            self.setup_combined_sink()

                case 'remove':
                    log.info(f'PulseAudio remove event for device type: {device_type} index: {event.index}')

                    devices = getattr(self.devices, device_type)
                    if devices.get(event.index):
                        device = devices[event.index]

                    if not device:
                        log.warning(f'Unable to find PulseAudio {device_type} with index {event.index} for event {event.t}')

                    elif device.name == 'combined':
                        pass

                    else:
                        getattr(self, f'remove_{device_type}_device')(device)

        except Exception as e:
            log.error(f'Failed to handle PulseAudio event: {e}')


    """Run the audio controller thread to handle PulseAudio devices"""
    def run(self):
        self.setup_devices()

        while not self._thread_event.is_set():
            try:
                log.info('starting new pulse audio event listener...')
                with Pulse('ProjectMAR Event Listener') as pulse:
                    pulse.event_mask_set('sink', 'source', 'card')
                    pulse.event_callback_set(self.pulse_event_handler)

                    while not self._thread_event.is_set():
                        pulse.event_listen(timeout=.1)

                pulse.close()
            except Exception as e:
                log.exception(f'Unhandled exception in PulseAudio thread: {e}')

        log.info('Stopping ProjectMAR PulseAudio Event Listener')

    """Close the PulseAudio connection and unload modules"""
    def close(self):
        if self.audio_listener_thread:
            self.audio_listener_thread.join()
            self.audio_listener_thread.close()
            
        for source_index, source_device in self.devices.source.items():
            if not source_device.name.startswith('bluez_source'):
                self.unload_loopback_modules(source_name=source_device.name)
                
        self.unload_combined_sink_modules()

        self.unload_null_sink_modules()
        
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


class VLCManager:
    def __init__(self):
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

    def play(self, filepath):
        print(f"Playing: {filepath}")
        media = self.instance.media_new(filepath)
        self.player.set_media(media)
        self.player.set_sh
        self.player.play()


class PhysicalMediaCtrl(Controller, threading.Thread):
    """Controller for managing physical media audio listeners such as USB and local directories.
    @param thread_event: Event to signal when the thread should stop.
    @param config: Configuration object containing audio settings.
    """
    def __init__(self, thread_event, config):
        super().__init__(thread_event, config)
        threading.Thread.__init__(self)
        
        self.audio_listener_mode    = self._config.audio_ctrl.get('audio_listener_mode', 'usb')
        self.audio_listener_random  = self._config.audio_ctrl.get('audio_listener_random', True)

        self.usb_listener_enabled    = self._config.audio_ctrl.get('usb_listener_enabled', False)
        self.local_listener_enabled = self._config.audio_ctrl.get('local_listener_enabled', False)
        self.local_listener_path          = self._config.audio_ctrl.get('local_listener_path')

        self.vlc_instance = vlc.Instance()        
        self.vlc_list_player = self.vlc_instance.media_list_player_new()
        self.vlc_media_list = self.vlc_instance.media_list_new()
        self.vlc_list_player.set_media_list(self.vlc_media_list)
        self.media_player = self.vlc_list_player.get_media_player()

        audio_devices = self.media_player.audio_output_device_enum()

        all_devices = []

        while audio_devices:
            dev = audio_devices.contents
            device_id = dev.device.decode("utf-8") if dev.device else "Unknown"
            description = dev.description.decode("utf-8") if dev.description else "No Description"
            print(f"Found device: ID={device_id}, Description={description}")
            all_devices.append({
                "device_id": device_id,
                "description": description
            })
            audio_devices = dev.next

        log.info(f'setting the default audio output to {all_devices}')
        self.media_player.audio_output_device_set(None, all_devices[0]['device_id'])

        log.info(self.media_player.audio_output_device_get())

        event_manager = self.media_player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerMediaChanged, self.on_media_changed)

        self.current_file_count = 0
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')    

    def get_supported_audio_files(self, path):
        audio_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(('.mp3', '.wav', '.flac', '.ogg')):
                    audio_files.append(os.path.join(root, file))
        return audio_files

    def build_playlist(self, path):
        log.info(f"Building playlist from: {path}")
        media_paths = self.get_supported_audio_files(path)

        if self.audio_listener_random:
            random.shuffle(media_paths)

        new_media_list = self.vlc_instance.media_list_new()
        for file_path in media_paths:
            media = self.vlc_instance.media_new_path(file_path)
            new_media_list.add_media(media)

        self.vlc_list_player.set_media_list(new_media_list)
        self.vlc_media_list = new_media_list
        self.current_file_count = len(media_paths)

    def on_media_changed(self, event):
        media = self.media_player.get_media()
        if media:
            media.parse_with_options(vlc.MediaParseFlag.local, timeout=5)
            log.info(media.__dict__)
            metadata = {
                'Title': media.get_meta(vlc.Meta.Title),
                'Artist': media.get_meta(vlc.Meta.Artist),
                'Album': media.get_meta(vlc.Meta.Album),
                'Genre': media.get_meta(vlc.Meta.Genre),
                'Track Number': media.get_meta(vlc.Meta.TrackNumber),
                'Duration (sec)': media.get_duration() / 1000
            }

            log.info("Now Playing:")
            for key, value in metadata.items():
                log.info(f"  {key}: {value if value else '(not available)'}")

    def start_playback(self, path):
        self.build_playlist(path)
        if self.current_file_count > 0:
            log.info("Starting VLC playback...")
            self.vlc_list_player.play()
        else:
            log.warning("No audio files found to play.")

    def stop_playback(self):
        log.info("Stopping VLC playback...")
        self.vlc_list_player.stop()

    """Run the local or USB audio listener based on the configured mode"""
    def run(self):
        if self.audio_listener_mode == 'usb' and self.usb_listener_enabled:
            log.info('USB listener enabled, starting CVLC process...')

            listener_path = '/media'
            usb_storage_devices = [
                device for device in self.context.list_devices(subsystem='block', DEVTYPE='disk')
                if device.attributes.asstring('removable') == '1'
            ]

            if len(usb_storage_devices) > 0:
                self.start_playback(listener_path)
            try:
                while not self._thread_event.is_set():
                    device = self.monitor.poll(timeout=1)
                    if device is None:
                        continue

                    if device.get('SUBSYSTEM') == 'block' and device.get('DEVTYPE') == 'disk':
                        if device.action == 'add':
                            log.info(f"USB device connected: {device.device_node} ({device.sys_name} starting CVLC process")
                            time.sleep(1)   # Wait for the device to be ready
                            self.start_playback(listener_path)

                        elif device.action == 'remove':
                            log.warning(f"USB device disconnected: {device.device_node} ({device.sys_name} stopping CVLC process")
                            self.stop_playback()

            except Exception as e:
                print(f"An error occurred: {e}")

        elif self.audio_listener_mode == 'local' and self.local_listener_enabled:

            user_env = os.getenv('USER')
            if self.local_listener_path == '':
                default_path = '/home/' + user_env + '/Music'
                os.makedirs(default_path, exist_ok=True)
                self.local_listener_path = default_path

            log.info(f'Local listener enabled, starting CVLC process listening to {self.local_listener_path}...')
            self.start_playback(self.local_listener_path)

            while not self._thread_event.is_set():
                current_files = self.get_supported_audio_files(self.local_listener_path)
                current_file_count = len(current_files)

                if current_file_count != self.current_file_count:
                    log.info('Local listener file count changed, restarting CVLC for rescan...')
                    self.stop_playback()
                    self.start_playback(self.local_listener_path)

                time.sleep(1)

        else:
            log.error('Invalid audio listener mode configured: {}'.format(self.audio_listener_mode))
            return

    """Close the physical media controller and clean up resources"""
    def close(self):
        log.info('Closing PhysicalMediaCtrl...')
        self.stop_playback()

        return self._close()