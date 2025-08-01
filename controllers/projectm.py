import ctypes
import logging
import os
import random
import re
import threading
import time
import sdl2
import sdl2.ext
import struct

import sounddevice as sd
import numpy as np

from OpenGL import GL

from lib.abstracts import Controller
from lib.config import Config, APP_ROOT

log = logging.getLogger()

UINPUT_INSTALLED = False
try:
    import uinput
    UINPUT_INSTALLED = True
except ImportError:
    log.warning('python-uinput is not installed and therefore will not be used!')

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

PROJECTM_MONO = 1
PROJECTM_STEREO = 2

PresetSwitchedCallback = ctypes.CFUNCTYPE(None, ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
PresetSwitchFailedCallback = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_void_p)

@PresetSwitchedCallback
def on_preset_switched(is_hard_cut, index, context):
    instance = ctypes.cast(context, ctypes.POINTER(ctypes.py_object)).contents.value
    instance.on_preset_switched(is_hard_cut, index)

@PresetSwitchFailedCallback
def on_preset_switch_failed(error_msg, context):
    instance = ctypes.cast(context, ctypes.POINTER(ctypes.py_object)).contents.value
    instance.on_preset_switch_failed(error_msg)

class ProjectMWrapper:
    def __init__(self, config, sdl_window, gl_context, screenshot_path, logger=None):
        # Load the shared library (adjust the path as needed)
        self.projectm_lib = ctypes.CDLL("/usr/local/lib/libprojectM-4.so")
        self.projectm_playlist_lib = ctypes.CDLL("/usr/local/lib/libprojectM-4-playlist.so")

        self._projectM = None
        self._playlist = None
        self._config = config  # Should be a dict-like object
        self._sdl_window = sdl_window
        self._gl_context = gl_context
        self._screenshot_path = screenshot_path

        self._current_preset = None
        self._current_preset_index = None
        self._current_preset_start = None

        # Set up projectm function signatures (examples, adjust as needed)
        self.projectm_lib.projectm_create.restype = ctypes.c_void_p
        self.projectm_lib.projectm_destroy.argtypes = [ctypes.c_void_p]
        self.projectm_lib.projectm_set_window_size.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.projectm_lib.projectm_set_fps.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.projectm_lib.projectm_set_mesh_size.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.projectm_lib.projectm_set_aspect_correction.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_lib.projectm_set_preset_locked.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_lib.projectm_set_preset_duration.argtypes = [ctypes.c_void_p, ctypes.c_double]
        self.projectm_lib.projectm_set_soft_cut_duration.argtypes = [ctypes.c_void_p, ctypes.c_double]
        self.projectm_lib.projectm_set_hard_cut_enabled.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_lib.projectm_set_hard_cut_duration.argtypes = [ctypes.c_void_p, ctypes.c_double]
        self.projectm_lib.projectm_set_hard_cut_sensitivity.argtypes = [ctypes.c_void_p, ctypes.c_float]
        self.projectm_lib.projectm_set_beat_sensitivity.argtypes = [ctypes.c_void_p, ctypes.c_float]
        self.projectm_lib.projectm_get_beat_sensitivity.argtypes = [ctypes.c_void_p]
        self.projectm_lib.projectm_get_beat_sensitivity.restype = ctypes.c_float
        self.projectm_lib.projectm_opengl_render_frame.argtypes = [ctypes.c_void_p]
        self.projectm_lib.projectm_get_mesh_size.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        self.projectm_lib.projectm_get_preset_locked.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_lib.projectm_get_preset_locked.restype = ctypes.c_bool
        self.projectm_lib.projectm_pcm_add_float.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_uint, ctypes.c_int]
        self.projectm_lib.projectm_pcm_add_float.restype = None
        self.projectm_lib.projectm_set_texture_search_paths.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)), ctypes.c_int]
        self.projectm_lib.projectm_set_texture_search_paths.restype = None

        # future feature
        self.projectm_lib.projectm_sprite_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        self.projectm_lib.projectm_sprite_create.restype = ctypes.c_uint
        self.projectm_lib.projectm_sprite_get_max_sprites.argtypes = [ctypes.c_void_p]
        self.projectm_lib.projectm_sprite_get_max_sprites.restype = ctypes.c_uint

        # Set up projectm playlist function signatures (examples, adjust as needed)
        self.projectm_playlist_lib.projectm_playlist_create.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_create.restype = ctypes.c_void_p
        self.projectm_playlist_lib.projectm_playlist_destroy.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_set_shuffle.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_add_preset.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_add_path.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_remove_preset.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.projectm_playlist_lib.projectm_playlist_remove_preset.restype = ctypes.c_bool
        self.projectm_playlist_lib.projectm_playlist_sort.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int, ctypes.c_int]
        self.projectm_playlist_lib.projectm_playlist_size.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_size.restype = ctypes.c_size_t
        self.projectm_playlist_lib.projectm_playlist_play_next.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_play_previous.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_set_position.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_get_shuffle.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_get_shuffle.restype = ctypes.c_bool
        self.projectm_playlist_lib.projectm_playlist_item.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.projectm_playlist_lib.projectm_playlist_item.restype = ctypes.c_char_p
        self.projectm_playlist_lib.projectm_playlist_free_string.argtypes = [ctypes.c_char_p]
        self.projectm_playlist_lib.projectm_playlist_free_string.restype = None
        self.projectm_playlist_lib.projectm_playlist_set_preset_switched_event_callback.argtypes = [ctypes.c_void_p, PresetSwitchedCallback, ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_set_preset_switch_failed_event_callback.argtypes = [ctypes.c_void_p, PresetSwitchFailedCallback, ctypes.c_void_p]

        # Setup callback and userdata
        self._preset_switched_event_callback = on_preset_switched
        self._preset_switch_failed_event_callback = on_preset_switch_failed
        self._user_data = ctypes.py_object(self)
        self._user_data_ptr = ctypes.cast(ctypes.pointer(self._user_data), ctypes.c_void_p)

    def initialize(self, canvas_width, canvas_height):
        if not self._projectM:
            self._projectM = self.projectm_lib.projectm_create()
            if not self._projectM:
                log.error("Failed to initialize projectM.")
                raise RuntimeError("projectM initialization failed")

            fps = self._config.projectm["projectm.fps"]
            if fps <= 0:
                fps = 60

            self.set_window_size(canvas_width, canvas_height)
            # self.projectm_lib.projectm_set_window_size(self._projectM, canvas_width, canvas_height)
            self.projectm_lib.projectm_set_fps(self._projectM, fps)
            self.projectm_lib.projectm_set_mesh_size(self._projectM, self._config.projectm["projectm.meshx"], self._config.projectm["projectm.meshy"])
            self.projectm_lib.projectm_set_aspect_correction(self._projectM, self._config.projectm["projectm.aspectcorrectionenabled"])
            self.projectm_lib.projectm_set_preset_locked(self._projectM, self._config.projectm["projectm.presetlocked"])
            self.projectm_lib.projectm_set_preset_duration(self._projectM, self._config.projectm["projectm.displayduration"])
            self.projectm_lib.projectm_set_soft_cut_duration(self._projectM, self._config.projectm["projectm.transitionduration"])
            self.projectm_lib.projectm_set_hard_cut_enabled(self._projectM, self._config.projectm["projectm.hardcutsenabled"])
            self.projectm_lib.projectm_set_hard_cut_duration(self._projectM, self._config.projectm["projectm.hardcutduration"])
            self.projectm_lib.projectm_set_hard_cut_sensitivity(self._projectM, float(self._config.projectm["projectm.hardcutsensitivity"]))
            self.projectm_lib.projectm_set_beat_sensitivity(self._projectM, float(self._config.projectm["projectm.beatsensitivity"]))

            self._playlist = self.projectm_playlist_lib.projectm_playlist_create(self._projectM)
            if not self._playlist:
                log.error("Failed to create the projectM preset playlist manager instance.")
                raise RuntimeError("Playlist initialization failed")

            # Shuffling should be ignored until they fix the playlist order to be able to
            # move to previous preset on shuffle, otherwise you can use the following:
            # self.projectm_playlist_lib.projectm_playlist_set_shuffle(self._playlist, self._config.projectm["projectm.shuffleenabled"])

            # Texture paths (if needed)
            texture_path_index = 0
            texture_paths = list()
            while True:
                config_key = 'projectm.texturepath'
                if texture_path_index > 0:
                    config_key += '.{}'.format(texture_path_index)

                if self._config.projectm.get(config_key, None):
                    log.info('Adding preset path {} {}'.format(config_key, self._config.projectm[config_key]))
                    texture_paths.append(self._config.projectm[config_key])

                else:
                    break

                texture_path_index += 1

            # Check if the texturePaths list is not empty
            if texture_paths:
                # Create a list of C-style string pointers (char* in C++)
                texture_path_list = [ctypes.create_string_buffer(path.encode('utf-8')) for path in texture_paths]

                # Create a pointer to an array of `char*` pointers (C-style array of strings)
                texture_path_array = (ctypes.POINTER(ctypes.c_char_p) * len(texture_path_list))()

                # Fill the array with the pointers to the texture paths
                for i, path in enumerate(texture_path_list):
                    texture_path_array[i] = ctypes.cast(ctypes.pointer(path), ctypes.POINTER(ctypes.c_char_p))

                # Now call the C function with the texture path array and size
                self.projectm_lib.projectm_set_texture_search_paths(self._projectM, texture_path_array, len(texture_paths))

            preset_path_index = 0
            preset_paths = list()
            while True:
                config_key = 'projectm.presetpath'
                if preset_path_index > 0:
                    config_key += '.{}'.format(preset_path_index)

                if self._config.projectm.get(config_key, None):
                    log.info('Adding preset path {} {}'.format(config_key, self._config.projectm[config_key]))
                    preset_paths.append(self._config.projectm[config_key])

                else:
                    break

                preset_path_index += 1

            for preset_path in preset_paths:
                if os.path.isfile(preset_path):
                    self.projectm_playlist_lib.projectm_playlist_add_preset(self._playlist, preset_path.encode(), False)
                else:
                    log.info(f'Adding preset path {preset_path}')
                    self.projectm_playlist_lib.projectm_playlist_add_path(self._playlist, preset_path.encode(), True, False)

            # Sorting constants (replace with actual values)
            SORT_PREDICATE_FILENAME_ONLY = 0
            SORT_ORDER_ASCENDING = 0
            size = self.projectm_playlist_lib.projectm_playlist_size(self._playlist)
            self.projectm_playlist_lib.projectm_playlist_sort(self._playlist, 0, size, SORT_PREDICATE_FILENAME_ONLY, SORT_ORDER_ASCENDING)

            log.info('Registering callbacks')

            # Register the preset event callbacks
            self.projectm_playlist_lib.projectm_playlist_set_preset_switched_event_callback(
                self._playlist,
                self._preset_switched_event_callback,
                self._user_data_ptr
            )

            self.projectm_playlist_lib.projectm_playlist_set_preset_switch_failed_event_callback(
                self._playlist,
                self._preset_switch_failed_event_callback,
                self._user_data_ptr
            )

    def uninitialize(self):
        if self._projectM:
            self.projectm_lib.projectm_destroy(self._projectM)
            self._projectM = None
        if self._playlist:
            self.projectm_playlist_lib.projectm_playlist_destroy(self._playlist)
            self._playlist = None

    def on_preset_switched(self, is_hard_cut: bool, index: int):
        name_ptr = self.projectm_playlist_lib.projectm_playlist_item(self._playlist, index)
        self._current_preset = ctypes.string_at(name_ptr).decode("utf-8")
        self._current_preset_index = index
        self._current_preset_start = time.time()
        log.info(f"[{is_hard_cut=}] Preset switched to: {self._current_preset}")

        if self._config.projectm["window.displaypresetnameintitle"]:
            sdl2.SDL_SetWindowTitle(self._sdl_window, self._current_preset.rsplit('/', 1)[1].encode())

    def on_preset_switch_failed(self, error_msg: str):
        error_string = ctypes.string_at(error_msg).decode("utf-8")
        log.error(f'Failed to switch preset with error {error_string}')

    def set_window_size(self, canvas_width, canvas_height):
        self.projectm_lib.projectm_set_window_size(self._projectM, canvas_width, canvas_height)

    def add_pcm(self, samples: np.ndarray, channels: int = PROJECTM_STEREO):
        if not self._projectM:
            raise RuntimeError("projectM instance not initialized")

        samples = np.ascontiguousarray(samples, dtype=np.float32)

        # Total samples must be divisible by number of channels
        count_per_channel = samples.size // channels
        ptr = samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        self.projectm_lib.projectm_pcm_add_float(
            self._projectM, ptr, count_per_channel, channels
        )

    def render_frame(self):
        # You must clear the OpenGL context yourself before calling this
        self.projectm_lib.projectm_opengl_render_frame(self._projectM)

    def display_initial_preset(self):
        if not self._config.projectm["projectm.enablesplash"]:
            # Shuffling should be ignored until they fix the playlist order to be able to
            # move to previous preset on shuffle, otherwise you can use the following:
            # self.projectm_playlist_lib.projectm_playlist_play_next(self._playlist, True)

            self.projectm_playlist_lib.projectm_playlist_set_position(self._playlist, 0, True)

    def get_item(self, index):
        item = self.projectm_playlist_lib.projectm_playlist_item(self._playlist, index)
        if not item:
            raise IndexError(f"Item at index {index} does not exist in the playlist")

        return item.decode('utf-8')

    def delete_preset(self, physical=False):
        self.projectm_playlist_lib.projectm_playlist_remove_preset(self._playlist, self._current_preset_index)
        if physical:
            try:
                os.remove(self._current_preset)
            except Exception as e:
                log.error(f'Failed to delete preset {self._current_preset} with error: {e}')

    def next_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_next(self._playlist, softcut)

    def previous_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_previous(self._playlist, softcut)

    def lock_preset(self, locked):
        self.projectm_lib.projectm_get_preset_locked(self._projectM, locked)

    def set_preset_index(self, index, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_set_position(self._playlist, index, softcut)

    def change_beat_sensitivity(self, value):
        current = self.projectm_lib.projectm_get_beat_sensitivity(self._projectM)
        self.projectm_lib.projectm_set_beat_sensitivity(self._projectM, current + value)
        log.info(f"User has changed the Beat Sensitivity to: {self.projectm_lib.projectm_get_beat_sensitivity(self._projectM):.2f}")

    def target_fps(self):
        return self._config.projectm["projectm.fps"]

    def update_real_fps(self, fps):
        self.projectm_lib.projectm_set_fps(self._projectM, int(round(fps)))

    def get_mesh_size(self):
        mesh_x = ctypes.c_size_t()
        mesh_y = ctypes.c_size_t()
        self.projectm_lib.projectm_get_mesh_size(self._projectM, ctypes.byref(mesh_x), ctypes.byref(mesh_y))
        return mesh_x.value, mesh_y.value

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

        self.screenshot_path = os.path.join(self.projectm_path, 'preset_screenshots')
        if not os.path.exists(self.screenshot_path):
            os.makedirs(self.screenshot_path)
        
        self.index_presets = self.config.projectm_ctrl.get('index_presets', False)
        # self.monitor_presets = self.config.projectm_ctrl.get('monitor_presets', False)
        # self.screenshot_presets = self.config.projectm_ctrl.get('screenshot_presets', False)

        # ProjectM Configurations
        config_path = os.path.join(APP_ROOT, 'conf', 'projectMSDL.conf')
        self.projectm_config = Config(config_path)
        self.shuffle_presets = self.projectm_config.projectm["projectm.shuffleenabled"]
        self.preset_display_duration = self.projectm_config.projectm['projectm.displayduration']

        self.projectm_wrapper = None

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
    def preset_hung(self, wrapper):
        if wrapper._current_preset_start:
            duration = time.time() - wrapper._current_preset_start
            if duration >= (self.preset_display_duration):
                return True

        return False

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
        log.info(f'shuffle presets {self.shuffle_presets}')
        presets = list()
        for preset_path in self.preset_paths:
            for root, dirs, files in os.walk(preset_path):
                for name in files:
                    preset_path = os.path.join(root, name)
                    if not preset_path in presets:
                        presets.append(preset_path)

        if self.shuffle_presets == True:
            random.shuffle(presets)

        if not self.shuffle_presets and not self.index_presets:
            pass
        else:
            self.create_indexed_presets(presets)

    def create_audio_stream(self, sample_rate=44100, buffer_size=512):
        def callback(indata, frames, time, status):
            if status:
                print("[Audio Warning]", status)

            self.projectm_wrapper.add_pcm(indata.flatten(), channels=PROJECTM_STEREO)

        stream = sd.InputStream(
            channels=2,
            samplerate=sample_rate,
            blocksize=buffer_size,
            dtype='float32',
            callback=callback,
        )
        return stream

    def resize_opengl_window(self, window, new_width, new_height, fullscreen=False):
        if not fullscreen:
            sdl2.SDL_SetWindowFullscreen(window, 0)
        else:
            sdl2.SDL_SetWindowFullscreen(window, 1)

        # Resize the SDL window
        sdl2.SDL_SetWindowSize(window, new_width, new_height)

        # Update the OpenGL viewport to match the new window size
        GL.glViewport(0, 0, new_width, new_height)

        # Adjust projection matrix or other settings if needed (e.g., for aspect ratio changes)
        # Here we set a simple orthographic projection for demonstration purposes
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, new_width, new_height, 0, -1, 1)  # Simple 2D orthographic projection

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

        self.projectm_wrapper.set_window_size(new_width, new_height)
        
    """Run the ProjectM controller"""
    def run(self):
        self.manage_preset_playlist()

        log.info('Loading frontendSDL...')

        # Initialize SDL2 with video and events
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) != 0:
            log.error("SDL_Init Error:", sdl2.SDL_GetError())
            return

        # Set OpenGL attributes
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 2)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 1)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DOUBLEBUFFER, 1)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DEPTH_SIZE, 24)

        window = sdl2.SDL_CreateWindow(
            b"projectM Python SDL2",
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            WINDOW_WIDTH, WINDOW_HEIGHT,
            sdl2.SDL_WINDOW_OPENGL | sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        )
        if not window:
            log.error("SDL_CreateWindow Error:", sdl2.SDL_GetError())
            sdl2.SDL_Quit()
            return

        gl_context = sdl2.SDL_GL_CreateContext(window)
        if not gl_context:
            log.error("SDL_GL_CreateContext Error:", sdl2.SDL_GetError())
            sdl2.SDL_DestroyWindow(window)
            sdl2.SDL_Quit()
            return

        sdl2.ext.mouse.hide_cursor()

        w = self.config.display_ctrl['resolution_width']
        h = self.config.display_ctrl['resolution_height']

        # Initialize ProjectMWrapper
        self.projectm_wrapper = ProjectMWrapper(self.projectm_config, window, gl_context, self.screenshot_path)
        self.projectm_wrapper.initialize(w, h)
        self.projectm_wrapper.display_initial_preset()

        # Start audio stream
        stream = self.create_audio_stream()
        stream.start()

        locked = self.projectm_config.projectm["projectm.presetlocked"]
        event = sdl2.SDL_Event()
        clock = sdl2.SDL_GetTicks()
        
        while not self._thread_event.is_set():
            while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
                current_window_flags = sdl2.SDL_GetWindowFlags(window)

                if event.type == sdl2.SDL_QUIT:
                    running = False
                elif event.type == sdl2.SDL_KEYDOWN:
                    if event.key.keysym.sym == sdl2.SDLK_n:
                        log.debug('User has requested the next preset')
                        self.projectm_wrapper.next_preset()
                    elif event.key.keysym.sym == sdl2.SDLK_p:
                        self.projectm_wrapper.previous_preset()
                        log.debug('User has requested the previous preset')
                    elif event.key.keysym.sym == sdl2.SDLK_DELETE:
                        self.projectm_wrapper.delete_preset(physical=True)
                        log.warning(f'User has opted to remove preset {self.projectm_wrapper._current_preset}')
                        self.projectm_wrapper.next_preset()
                    elif event.key.keysym.sym == sdl2.SDLK_SPACE:
                        if locked:
                            locked = False
                        else:
                            locked = True

                        self.projectm_wrapper.lock_preset(locked)
                        log.info(f'User has initiated a preset lock: {locked}')
                    elif (event.key.keysym.sym == sdl2.SDLK_q and 
                            ((event.key.keysym.mod & sdl2.KMOD_LCTRL) or (event.key.keysym.mod & sdl2.KMOD_RCTRL))):
                        self._thread_event.set()
                        break
                    elif event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                        if current_window_flags & sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP:
                            log.info('Window is currently in full screen')
                            self.resize_opengl_window(window, self.projectm_config.projectm['window.width'], self.projectm_config.projectm['window.height'])  # Resize to 1024x768
                    elif event.key.keysym.sym == sdl2.SDLK_UP:
                        self.projectm_wrapper.change_beat_sensitivity(.1)
                    elif event.key.keysym.sym == sdl2.SDLK_DOWN:
                        self.projectm_wrapper.change_beat_sensitivity(-.1)

                elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                    if event.button.button == sdl2.SDL_BUTTON_RIGHT:
                        if current_window_flags & sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP:
                            self.resize_opengl_window(window, self.projectm_config.projectm['window.width'], self.projectm_config.projectm['window.height'], fullscreen=False)  # Resize to 1024x768
                        else:
                            self.resize_opengl_window(window, WINDOW_WIDTH, WINDOW_HEIGHT, fullscreen=True)  # Resize to 1024x768

                elif event.type == sdl2.SDL_WINDOWEVENT:
                    if event.window.event == sdl2.SDL_WINDOWEVENT_CLOSE:
                        self._thread_event.set()
                        break

                    if event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED or event.window.event == sdl2.SDL_WINDOWEVENT_SIZE_CHANGED:
                        w, h = ctypes.c_int(), ctypes.c_int()
                        sdl2.SDL_GetWindowSize(window, ctypes.byref(w), ctypes.byref(h))
                        width, height = w.value, h.value

                        self.projectm_wrapper.set_window_size(width, height)

                    if event.window.event == sdl2.SDL_WINDOWEVENT_HIDDEN or event.window.event == sdl2.SDL_WINDOWEVENT_MINIMIZED:
                        # Try to restore or re-show the window
                        sdl2.SDL_RestoreWindow(window)
                        sdl2.SDL_ShowWindow(window)
                    elif event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
                        log.warning("Window lost focus")
                    elif event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_GAINED:
                        log.info("Window regained focus")

            # Clear the OpenGL context
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            # Render projectM frame
            self.projectm_wrapper.render_frame()

            # Swap buffers
            sdl2.SDL_GL_SwapWindow(window)

            # Frame limiting (simple)
            sdl2.SDL_Delay(int(1000 / self.projectm_config.projectm["projectm.fps"]))

            if self.preset_hung(self.projectm_wrapper):
                self.force_transition_preset(uinput.KEY_N)
        # Cleanup
        stream.stop()
        stream.close()
        self.projectm_wrapper.uninitialize()
        sdl2.ext.quit()
        sdl2.SDL_GL_DeleteContext(gl_context)
        sdl2.SDL_DestroyWindow(window)
        sdl2.SDL_Quit()

    """Close the ProjectM controller and all associated threads"""
    def close(self):
        self._close()