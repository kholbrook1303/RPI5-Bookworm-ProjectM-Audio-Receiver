import ctypes
import logging
import os
import random
import re
import time
import shutil

import numpy as np

from lib.common import load_library

log = logging.getLogger()

# projectM playlist sorting predicates
SORT_PREDICATE_FULL_PATH        = 0 # Sort by full path name
SORT_PREDICATE_FILENAME_ONLY    = 1 # Sort only by preset filename

# projectM playlist sorting order
SORT_ORDER_ASCENDING            = 0 # Sort in alphabetically ascending order.
SORT_ORDER_DESCENDING           = 1 # Sort in alphabetically descending order.

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
    def __init__(self, config, sdl_rendering):
        self.config = config
        self.sdl_rendering = sdl_rendering

        log.info('The projectM settings are as follows:')
        for key, val in self.config.projectm.items():
            log.info(f'{key}: {val}')
            
        self.projectm = None
        self.projectm_lib = load_library('projectM-4')
        
        self.projectm_playlist = None
        self.projectm_playlist_lib = load_library('projectM-4-playlist')

        self.preset_paths = list()
        self.texture_paths = list()

        self.current_preset = None
        self.current_preset_start = None

        # Set up projectm function signatures
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
        self.projectm_lib.projectm_get_preset_locked.argtypes = [ctypes.c_void_p]
        self.projectm_lib.projectm_get_preset_locked.restype = ctypes.c_bool
        self.projectm_lib.projectm_pcm_add_float.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_uint, ctypes.c_int]
        self.projectm_lib.projectm_pcm_add_float.restype = None
        self.projectm_lib.projectm_set_texture_search_paths.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)), ctypes.c_int]
        self.projectm_lib.projectm_set_texture_search_paths.restype = None

        # Future user sprites feature
        # self.projectm_lib.projectm_sprite_create.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        # self.projectm_lib.projectm_sprite_create.restype = ctypes.c_uint
        # self.projectm_lib.projectm_sprite_get_max_sprites.argtypes = [ctypes.c_void_p]
        # self.projectm_lib.projectm_sprite_get_max_sprites.restype = ctypes.c_uint

        # Set up projectm playlist function signatures
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
        self.projectm_playlist_lib.projectm_playlist_get_position.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_get_position.restype = ctypes.c_uint
        self.projectm_playlist_lib.projectm_playlist_set_position.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_bool]
        self.projectm_playlist_lib.projectm_playlist_get_shuffle.argtypes = [ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_get_shuffle.restype = ctypes.c_bool
        self.projectm_playlist_lib.projectm_playlist_item.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.projectm_playlist_lib.projectm_playlist_item.restype = ctypes.c_char_p
        self.projectm_playlist_lib.projectm_playlist_free_string.argtypes = [ctypes.c_char_p]
        self.projectm_playlist_lib.projectm_playlist_free_string.restype = None
        self.projectm_playlist_lib.projectm_playlist_set_preset_switched_event_callback.argtypes = [ctypes.c_void_p, PresetSwitchedCallback, ctypes.c_void_p]
        self.projectm_playlist_lib.projectm_playlist_set_preset_switch_failed_event_callback.argtypes = [ctypes.c_void_p, PresetSwitchFailedCallback, ctypes.c_void_p]

        if not self.projectm:
            canvas_width = ctypes.c_int()
            canvas_height = ctypes.c_int()

            self.projectm = self.projectm_lib.projectm_create()
            if not self.projectm:
                log.error("Failed to initialize projectM. Possible reasons are a lack of required OpenGL features or GPU resources.")
                raise RuntimeError("projectM initialization failed")

            fps = self.config.projectm.get("projectm.fps", 60)
            if fps <= 0:
                fps = 60

            self.set_window_size(canvas_width, canvas_height)
            self.projectm_lib.projectm_set_fps(self.projectm, fps)
            self.projectm_lib.projectm_set_mesh_size(self.projectm, self.config.projectm.get("projectm.meshx", 64), self.config.projectm.get("projectm.meshy", 32))
            self.projectm_lib.projectm_set_aspect_correction(self.projectm, self.config.projectm.get("projectm.aspectcorrectionenabled", True))
            self.projectm_lib.projectm_set_preset_locked(self.projectm, self.config.projectm.get("projectm.presetlocked", False))
            self.projectm_lib.projectm_set_preset_duration(self.projectm, self.config.projectm.get("projectm.displayduration", 60))
            self.projectm_lib.projectm_set_soft_cut_duration(self.projectm, self.config.projectm.get("projectm.transitionduration", 0))
            self.projectm_lib.projectm_set_hard_cut_enabled(self.projectm, self.config.projectm.get("projectm.hardcutsenabled", True))
            self.projectm_lib.projectm_set_hard_cut_duration(self.projectm, self.config.projectm.get("projectm.hardcutduration", 30))
            self.projectm_lib.projectm_set_hard_cut_sensitivity(self.projectm, float(self.config.projectm.get("projectm.hardcutsensitivity", 2)))
            self.projectm_lib.projectm_set_beat_sensitivity(self.projectm, float(self.config.projectm.get("projectm.beatsensitivity", 2)))

            self.projectm_playlist = self.projectm_playlist_lib.projectm_playlist_create(self.projectm)
            if not self.projectm_playlist:
                log.error("Failed to create the projectM preset playlist manager instance.")
                raise RuntimeError("Playlist initialization failed")

            # self.projectm_playlist_lib.projectm_playlist_set_shuffle(self.projectm_playlist, self.config.projectm.get("projectm.shuffleenabled", False))
            self.projectm_playlist_lib.projectm_playlist_set_shuffle(self.projectm_playlist, False)

            texture_path_index = 0
            while True:
                config_key = 'projectm.texturepath'
                if texture_path_index > 0:
                    config_key += '.{}'.format(texture_path_index)

                if self.config.projectm.get(config_key, None):
                    log.info('Adding texture path {} {}'.format(config_key, self.config.projectm.get(config_key)))
                    self.texture_paths.append(self.config.projectm.get(config_key))

                else:
                    break

                texture_path_index += 1

            if self.texture_paths:
                texture_path_list = [ctypes.create_string_buffer(path.encode('utf-8')) for path in self.texture_paths]
                texture_path_array = (ctypes.POINTER(ctypes.c_char_p) * len(texture_path_list))()

                for i, path in enumerate(texture_path_list):
                    texture_path_array[i] = ctypes.cast(ctypes.pointer(path), ctypes.POINTER(ctypes.c_char_p))

                self.projectm_lib.projectm_set_texture_search_paths(self.projectm, texture_path_array, len(self.texture_paths))

            preset_path_index = 0
            while True:
                config_key = 'projectm.presetpath'
                if preset_path_index > 0:
                    config_key += '.{}'.format(preset_path_index)

                if self.config.projectm.get(config_key, None):
                    log.info('Adding preset path {} {}'.format(config_key, self.config.projectm.get(config_key)))
                    self.preset_paths.append(self.config.projectm.get(config_key))

                else:
                    break

                preset_path_index += 1

            if self.config.projectm.get("projectm.shuffleenabled", False):
                log.info(f'Randomizing preset indexes for shuffle mode...')
                presets = list()
                for preset_path in self.preset_paths:
                    for root, dirs, files in os.walk(preset_path):
                        for name in files:
                            preset_path = os.path.join(root, name)
                            if not preset_path in presets:
                                presets.append(preset_path)

                random.shuffle(presets)
                self.create_indexed_presets(presets)

            for preset_path in self.preset_paths:
                if os.path.isfile(preset_path):
                    self.projectm_playlist_lib.projectm_playlist_add_preset(self.projectm_playlist, preset_path.encode(), False)
                else:
                    log.info(f'Adding preset path {preset_path}')
                    self.projectm_playlist_lib.projectm_playlist_add_path(self.projectm_playlist, preset_path.encode(), True, False)

            # Sorting constants
            size = self.projectm_playlist_lib.projectm_playlist_size(self.projectm_playlist)
            self.projectm_playlist_lib.projectm_playlist_sort(
                self.projectm_playlist, 0, size, 
                SORT_PREDICATE_FILENAME_ONLY, SORT_ORDER_ASCENDING
            )

            # Setup callback and userdata
            self._preset_switched_event_callback = on_preset_switched
            self._preset_switch_failed_event_callback = on_preset_switch_failed
        
            user_data = ctypes.py_object(self)
            self._user_data_ptr = ctypes.cast(ctypes.pointer(user_data), ctypes.c_void_p)

            # Register the preset event callbacks
            self.projectm_playlist_lib.projectm_playlist_set_preset_switched_event_callback(
                self.projectm_playlist,
                self._preset_switched_event_callback,
                self._user_data_ptr
            )

            self.projectm_playlist_lib.projectm_playlist_set_preset_switch_failed_event_callback(
                self.projectm_playlist,
                self._preset_switch_failed_event_callback,
                self._user_data_ptr
            )

    def __del__(self):
        if self.projectm:
            self.projectm_lib.projectm_destroy(self.projectm)
            self.projectm = None
        if self.projectm_playlist:
            self.projectm_playlist_lib.projectm_playlist_destroy(self.projectm_playlist)
            self.projectm_playlist = None

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

    def on_preset_switched(self, is_hard_cut: bool, index: int):
        name_ptr = self.projectm_playlist_lib.projectm_playlist_item(self.projectm_playlist, index)
        self.current_preset = ctypes.string_at(name_ptr).decode("utf-8")
        self.current_preset_start = time.time()
        log.info(f"[{is_hard_cut=}] Preset switched to: {self.current_preset}")

        if self.config.projectm.get("window.displaypresetnameintitle", True):
            self.sdl_rendering.set_sdl_window_title(self.current_preset.rsplit('/', 1)[1].encode())

    def on_preset_switch_failed(self, error_msg: str):
        error_string = ctypes.string_at(error_msg).decode("utf-8")
        log.error(f'Failed to switch preset with error {error_string}')

    def get_active_preset_index(self):
        return self.projectm_playlist_lib.projectm_playlist_get_position(self.projectm_playlist)

    def get_preset_item(self, index):
        item = self.projectm_playlist_lib.projectm_playlist_item(self.projectm_playlist, index)
        if not item:
            raise IndexError(f"Item at index {index} does not exist in the playlist")

        return item.decode('utf-8')

    def display_initial_preset(self):
        if not self.config.projectm.get("projectm.enablesplash", False):
            self.projectm_playlist_lib.projectm_playlist_set_position(self.projectm_playlist, 0, True)

            # Currently it is best to handle shuffling by creating an index for each preset and randomizing it
            # libprojectM uses a random preset for shuffle so you cannot go to previous/next and get expected results
            # if self.config.projectm.get("projectm.shuffleenabled", False):
            #     self.projectm_playlist_lib.projectm_playlist_play_next(self.projectm_playlist, True)
            # else:
            #     self.projectm_playlist_lib.projectm_playlist_set_position(self.projectm_playlist, 0, True)

    def delete_preset(self, physical=False):
        preset_index = self.get_active_preset_index()
        if preset_index:
            preset_name = self.get_preset_item(preset_index)

            log.info(f'User has requested to delete preset {preset_name} with index {preset_index}')
            self.projectm_playlist_lib.projectm_playlist_remove_preset(self.projectm_playlist, preset_index)
            
            try:
                if physical and self.config.projectm.get("projectm.presetdeletebachupenabled", True):
                    backup_path = self.config.projectm.get('projectm.presetdeletebachuppath', '/opt/ProjectMAR/preset_backup')

                    match_path = None
                    for preset_path in self.preset_paths:
                        if preset_name.startswith(preset_path):
                            match_path = preset_path
                            break

                    if match_path:
                        backup_path = preset_name.replace(match_path, backup_path)
                        backup_dir = os.path.dirname(backup_path)
                        os.makedirs(backup_dir, exist_ok=True)

                        shutil.move(preset_name, backup_path)

                elif physical:
                    os.remove(preset_name)

            except Exception as e:
                log.error(f'Failed to delete/backup preset {preset_name} with error: {e}')

            self.next_preset()

    def next_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_next(self.projectm_playlist, softcut)

    def previous_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_previous(self.projectm_playlist, softcut)

    def set_preset_index(self, index, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_set_position(self.projectm_playlist, index, softcut)

    def get_preset_shuffle(self):
        return self.projectm_playlist_lib.projectm_playlist_get_shuffle(self.projectm_playlist)

    def shuffle_playlist(self, shuffle):
        self.projectm_playlist_lib.projectm_playlist_set_shuffle(self.projectm_playlist, shuffle)

    def get_preset_locked(self):
        return self.projectm_lib.projectm_get_preset_locked(self.projectm)

    def toggle_preset_lock(self):
        locked = self.get_preset_locked()
        if locked:
            log.debug(f'User has requested to unlock the presets')
            self.projectm_wrapper.lock_preset(False)
        else:
            log.debug(f'User has requested to lock the presets')
            self.projectm_wrapper.lock_preset(True)

    def change_beat_sensitivity(self, value):
        current = self.projectm_lib.projectm_get_beat_sensitivity(self.projectm)
        self.projectm_lib.projectm_set_beat_sensitivity(self.projectm, current + value)
        log.debug(f"User has changed the Beat Sensitivity to: {self.projectm_lib.projectm_get_beat_sensitivity(self.projectm):.2f}")

    def set_window_size(self, canvas_width, canvas_height):
        self.projectm_lib.projectm_set_window_size(self.projectm, canvas_width, canvas_height)

    def add_pcm(self, samples: np.ndarray, frame_count: int, channels: int):
        if not self.projectm:
            raise RuntimeError("projectM instance not initialized")

        samples = np.ascontiguousarray(samples, dtype=np.float32)
        ptr = samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        self.projectm_lib.projectm_pcm_add_float(
            self.projectm, ptr, frame_count, channels
        )

    def render_frame(self):
        self.projectm_lib.projectm_opengl_render_frame(self.projectm)

    def target_fps(self):
        return self.config.projectm.get("projectm.fps", 60)

    def update_real_fps(self, fps):
        self.projectm_lib.projectm_set_fps(self.projectm, int(round(fps)))

    def get_mesh_size(self):
        mesh_x = ctypes.c_size_t()
        mesh_y = ctypes.c_size_t()
        self.projectm_lib.projectm_get_mesh_size(self.projectm, ctypes.byref(mesh_x), ctypes.byref(mesh_y))
        return mesh_x.value, mesh_y.value