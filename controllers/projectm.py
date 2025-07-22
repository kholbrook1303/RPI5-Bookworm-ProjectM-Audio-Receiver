import logging
import os
import random
import re
import threading
import time

from lib.abstracts import Controller
from lib.config import Config

log = logging.getLogger()

UINPUT_INSTALLED = False
try:
    import uinput
    UINPUT_INSTALLED = True
except ImportError:
    log.warning('python-uinput is not installed and therefore will not be used!')

class ProjectMCtrl(Controller, threading.Thread):
    """Controller for managing the ProjectM visualization.
    @param thread_event: an event to signal the thread to stop
    @param refresh_event: an event to signal a refresh of the visualization
    @param config: the application configuration object
    @param audio_ctrl: the audio controller instance
    @param display_ctrl: the display controller instance
    """
    def __init__(self, thread_event, refresh_event, config, audio_ctrl, display_ctrl):
        threading.Thread.__init__(self)
        super().__init__(thread_event)
        
        self.config         = config
        self.audio_ctrl     = audio_ctrl
        self.display_ctrl   = display_ctrl
        self.thread_event   = thread_event
        self.refresh_event  = refresh_event
        
        self.projectm_path = self.config.projectm_ctrl.get('path', '/opt/ProjectMSDL')
        self.projectm_restore = self.config.projectm_ctrl.get('restore_process', False)      

        self.screenshot_index = 0
        self.screenshot_path = os.path.join(self.projectm_path, 'preset_screenshots')
        if not os.path.exists(self.screenshot_path):
            os.makedirs(self.screenshot_path)
        
        self.preset_start = 0
        self.advanced_shuffle = self.config.projectm_ctrl.get('advanced_shuffle', False)
        self.index_presets = self.config.projectm_ctrl.get('index_presets', False)
        self.monitor_presets = self.config.projectm_ctrl.get('monitor_presets', False)
        self.screenshot_presets = self.config.projectm_ctrl.get('screenshot_presets', False)

        # ProjectM Configurations
        config_path = os.path.join(self.projectm_path, 'projectMSDL.properties')
        self.projectm_config = Config(config_path, config_header='[projectm]')
        self.preset_shuffle = self.projectm_config.projectm['projectm.shuffleenabled']
        self.preset_display_duration = self.projectm_config.projectm['projectm.displayduration']

        preset_path_index = 0
        self.preset_paths = list()
        while True:
            config_key = 'projectm.presetpath'
            if preset_path_index > 0:
                config_key += '.{}'.format(preset_path_index)

            if self.projectm_config.projectm.get(config_key, None):
                log.info('Adding preset path {} {}'.format(config_key, self.projectm_config.projectm[config_key]))
                self.preset_paths.append(self.projectm_config.projectm[config_key])

            else:
                break

            preset_path_index += 1
            
    """Take a screenshot of the current preset.
    @param preset: the name of the preset to take a screenshot of
    """
    def take_screenshot(self, preset):
        preset_name = os.path.splitext(preset)[0]
        preset_name_filtered = preset_name.split(' ', 1)[1]
        preset_screenshot_name = preset_name_filtered + '.png'
        if not preset_screenshot_name in os.listdir(self.screenshot_path):
            if self.screenshot_index > 0:
                time.sleep(3)
                log.info('Taking a screenshot of {0}'.format(preset))
                screenshot_path = os.path.join(self.screenshot_path, preset_screenshot_name)

                try:
                    if self.display_ctrl.display_type == 'wayland':
                        self._execute_managed(['/usr/bin/grim', screenshot_path])
                    elif self.display_ctrl.display_type == 'x11':
                        self._execute_managed(['/usr/bin/scrot', screenshot_path])
                    
                except Exception as e:
                    log.error('Failed to take screenshot of {0}: {1}'.format(preset, e))

            self.screenshot_index += 1
            
    """Monitor the output of the ProjectM process"""
    def monitor_output(self):
        while not self._thread_event.is_set():
            for line in self._read_stream(self._processes['ProjectMDSL'].process.stderr):
                log.debug('ProjectM Output: {0}'.format(line))
            
                try:
                    match = re.search(r'Displaying preset: (?P<name>.*)$', line, re.I)
                    if match:
                        preset = match.group('name').rsplit('/', 1)[1]
                
                        log.info('Currently displaying preset: {0}'.format(preset))
                        self.preset_start = time.time()
                
                        # Take a preview screenshot
                        if self.display_ctrl._environment == 'desktop':
                            if self.screenshot_presets and self.audio_ctrl.source_device:
                                self.take_screenshot(preset)
                except:
                    log.exception('Failed to process output: {}'.format(line))

            time.sleep(1)

    """Force a transition to the next preset.
    @param transition_key: the key to emit for the transition
    """
    def force_transition_preset(self, transition_key):
        try:
            events = [
                transition_key
            ]

            log.info('Manually transitioning to the next visualization...')
            with uinput.Device(events) as device:
                time.sleep(1)
                device.emit_click(transition_key)
        except:
            log.exception('Failed to access uinput device!')

    """Check if the preset has been hung for too long"""
    def preset_hung(self):
        if self.preset_start != 0:
            duration = time.time() - self.preset_start
            if duration >= (self.preset_display_duration):
                return True

        return False

    """Monitor the presets to check if they are hung"""
    def preset_monitor(self):
        while not self._thread_event.is_set():
            if self.monitor_presets and UINPUT_INSTALLED and self.preset_hung():
                log.warning('The visualization has not changed in the alloted timeout!')
                self.force_transition_preset(uinput.KEY_N)

            time.sleep(1)

    """Create indexed presets by renaming them with a six-digit index"""
    def create_indexed_presets(self, presets):
        for index, preset in enumerate(presets, start=1):
            idx_pad = f"{index:06}"
            preset_root, preset_name = preset.rsplit('/', 1)
            if not re.match(r'^\d{6}\s.*?\.milk', preset_name, re.I):
                preset_name_stripped = preset_name
            else:
                preset_name_stripped = preset_name.split(' ', 1)[1]
            dst = os.path.join(preset_root, f"{idx_pad} {preset_name_stripped}")
            try:
                os.rename(preset, dst)
            except Exception as e:
                log.error(f'Failed to rename preset {preset}: {e}')
           
    """Manage the preset playlist by indexing and shuffling presets"""
    def manage_preset_playlist(self):
        presets = list()
        for preset_path in self.preset_paths:
            for root, dirs, files in os.walk(preset_path):
                for name in files:
                    preset_path = os.path.join(root, name)
                    if not preset_path in presets:
                        presets.append(preset_path)

        if self.advanced_shuffle == True:
            random.shuffle(presets)

        if not self.advanced_shuffle and not self.preset_index:
            pass
        else:
            self.create_indexed_presets(presets)
        
    """Run the ProjectM controller"""
    def run(self, beatSensitivity=2.0):   
        self.manage_preset_playlist()
    
        app_path = os.path.join(self.projectm_path, 'projectMSDL')

        projectm_process_attributes = self._execute(
            'projectMSDL', app_path, [app_path, '--beatSensitivity=' + str(beatSensitivity)],
            False
            )

        projectm_process_attributes.restore = self.projectm_restore
        projectm_process_attributes.trigger = self.refresh_event
        if not self.projectm_restore:
            projectm_process_attributes.halt_on_exit = True

        self._processes['ProjectMDSL'] = projectm_process_attributes

        monitors = [
            {'name': 'ProjectMDSL_Output', 'target': self.monitor_output},
            {'name': 'ProjectMDSL_Hang', 'target': self.preset_monitor}
            ]

        for monitor in monitors:
            output_thread = threading.Thread(
                target=monitor['target'],
                )
            output_thread.start()
            self._threads[monitor['name']] = output_thread

        self._monitor_processes()

    """Close the ProjectM controller and all associated threads"""
    def close(self):
        self._close()