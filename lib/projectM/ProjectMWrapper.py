import ctypes
import logging
import os
import time

import numpy as np

log = logging.getLogger()

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

        log.info('The projectM settings are as follows:')
        for key, val in self.config.projectm.items():
            log.info(f'{key}: {val}')

        self.projectm_lib = ctypes.CDLL("/usr/local/lib/libprojectM-4.so")
        self.projectm_playlist_lib = ctypes.CDLL("/usr/local/lib/libprojectM-4-playlist.so")

        self._projectM = None
        self._playlist = None
        self._sdl_rendering = sdl_rendering

        self._current_preset = None
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

        if not self._projectM:
            canvas_width = ctypes.c_int()
            canvas_height = ctypes.c_int()

            self._projectM = self.projectm_lib.projectm_create()
            if not self._projectM:
                log.error("Failed to initialize projectM. Possible reasons are a lack of required OpenGL features or GPU resources.")
                raise RuntimeError("projectM initialization failed")

            fps = self.config.projectm.get("projectm.fps", 60)
            if fps <= 0:
                fps = 60

            self.set_window_size(canvas_width, canvas_height)
            self.projectm_lib.projectm_set_fps(self._projectM, fps)
            self.projectm_lib.projectm_set_mesh_size(self._projectM, self.config.projectm.get("projectm.meshx", 64), self.config.projectm.get("projectm.meshy", 32))
            self.projectm_lib.projectm_set_aspect_correction(self._projectM, self.config.projectm.get("projectm.aspectcorrectionenabled", True))
            self.projectm_lib.projectm_set_preset_locked(self._projectM, self.config.projectm.get("projectm.presetlocked", False))
            self.projectm_lib.projectm_set_preset_duration(self._projectM, self.config.projectm.get("projectm.displayduration", 60))
            self.projectm_lib.projectm_set_soft_cut_duration(self._projectM, self.config.projectm.get("projectm.transitionduration", 0))
            self.projectm_lib.projectm_set_hard_cut_enabled(self._projectM, self.config.projectm.get("projectm.hardcutsenabled", True))
            self.projectm_lib.projectm_set_hard_cut_duration(self._projectM, self.config.projectm.get("projectm.hardcutduration", 30))
            self.projectm_lib.projectm_set_hard_cut_sensitivity(self._projectM, float(self.config.projectm.get("projectm.hardcutsensitivity", 2)))
            self.projectm_lib.projectm_set_beat_sensitivity(self._projectM, float(self.config.projectm.get("projectm.beatsensitivity", 2)))

            self._playlist = self.projectm_playlist_lib.projectm_playlist_create(self._projectM)
            if not self._playlist:
                log.error("Failed to create the projectM preset playlist manager instance.")
                raise RuntimeError("Playlist initialization failed")

            self.projectm_playlist_lib.projectm_playlist_set_shuffle(self._playlist, self.config.projectm.get("projectm.shuffleenabled", False))

            texture_path_index = 0
            texture_paths = list()
            while True:
                config_key = 'projectm.texturepath'
                if texture_path_index > 0:
                    config_key += '.{}'.format(texture_path_index)

                if self.config.projectm.get(config_key, None):
                    log.info('Adding preset path {} {}'.format(config_key, self.config.projectm.get(config_key)))
                    texture_paths.append(self.config.projectm.get(config_key))

                else:
                    break

                texture_path_index += 1

            if texture_paths:
                texture_path_list = [ctypes.create_string_buffer(path.encode('utf-8')) for path in texture_paths]
                texture_path_array = (ctypes.POINTER(ctypes.c_char_p) * len(texture_path_list))()

                for i, path in enumerate(texture_path_list):
                    texture_path_array[i] = ctypes.cast(ctypes.pointer(path), ctypes.POINTER(ctypes.c_char_p))

                self.projectm_lib.projectm_set_texture_search_paths(self._projectM, texture_path_array, len(texture_paths))

            preset_path_index = 0
            preset_paths = list()
            while True:
                config_key = 'projectm.presetpath'
                if preset_path_index > 0:
                    config_key += '.{}'.format(preset_path_index)

                if self.config.projectm.get(config_key, None):
                    log.info('Adding preset path {} {}'.format(config_key, self.config.projectm.get(config_key)))
                    preset_paths.append(self.config.projectm.get(config_key))

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

            # Setup callback and userdata
            self._preset_switched_event_callback = on_preset_switched
            self._preset_switch_failed_event_callback = on_preset_switch_failed
        
            user_data = ctypes.py_object(self)
            self._user_data_ptr = ctypes.cast(ctypes.pointer(user_data), ctypes.c_void_p)

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
        self._current_preset_start = time.time()
        log.info(f"[{is_hard_cut=}] Preset switched to: {self._current_preset}")

        if self.config.projectm.get("window.displaypresetnameintitle", True):
            self._sdl_rendering.set_sdl_window_title(self._current_preset.rsplit('/', 1)[1].encode())

    def on_preset_switch_failed(self, error_msg: str):
        error_string = ctypes.string_at(error_msg).decode("utf-8")
        log.error(f'Failed to switch preset with error {error_string}')

    def get_active_preset_index(self):
        return self.projectm_playlist_lib.projectm_playlist_get_position(self._playlist)

    def get_preset_item(self, index):
        item = self.projectm_playlist_lib.projectm_playlist_item(self._playlist, index)
        if not item:
            raise IndexError(f"Item at index {index} does not exist in the playlist")

        return item.decode('utf-8')

    def display_initial_preset(self):
        if not self.config.projectm.get("projectm.enablesplash", False):
            if self.config.projectm.get("projectm.shuffleenabled", False):
                self.projectm_playlist_lib.projectm_playlist_play_next(self._playlist, True)
            else:
                self.projectm_playlist_lib.projectm_playlist_set_position(self._playlist, 0, True)

    def delete_preset(self, physical=False):
        preset_index = self.get_active_preset_index()
        if preset_index:
            preset_name = self.get_preset_item(preset_index)

            log.info(f'Delete operation identified {preset_index} {preset_name}')
            self.projectm_playlist_lib.projectm_playlist_remove_preset(self._playlist, preset_index)

            if physical:
                try:
                    os.remove(preset_name)
                except Exception as e:
                    log.error(f'Failed to delete preset {preset_name} with error: {e}')

            self.next_preset()

    def next_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_next(self._playlist, softcut)

    def previous_preset(self, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_play_previous(self._playlist, softcut)

    def set_preset_index(self, index, softcut=True):
        self.projectm_playlist_lib.projectm_playlist_set_position(self._playlist, index, softcut)

    def get_preset_locked(self):
        return self.projectm_lib.projectm_get_preset_locked(self._projectM)

    def lock_preset(self, locked):
        self.projectm_lib.projectm_set_preset_locked(self._projectM, locked)

    def change_beat_sensitivity(self, value):
        current = self.projectm_lib.projectm_get_beat_sensitivity(self._projectM)
        self.projectm_lib.projectm_set_beat_sensitivity(self._projectM, current + value)
        log.info(f"User has changed the Beat Sensitivity to: {self.projectm_lib.projectm_get_beat_sensitivity(self._projectM):.2f}")

    def set_window_size(self, canvas_width, canvas_height):
        self.projectm_lib.projectm_set_window_size(self._projectM, canvas_width, canvas_height)

    def add_pcm(self, samples: np.ndarray, channels):
        if not self._projectM:
            raise RuntimeError("projectM instance not initialized")

        samples = np.ascontiguousarray(samples, dtype=np.float32)

        count_per_channel = samples.size // channels
        ptr = samples.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        self.projectm_lib.projectm_pcm_add_float(
            self._projectM, ptr, count_per_channel, channels
        )

    def render_frame(self):
        self.projectm_lib.projectm_opengl_render_frame(self._projectM)

    def target_fps(self):
        return self.config.projectm.get("projectm.fps", 60)

    def update_real_fps(self, fps):
        self.projectm_lib.projectm_set_fps(self._projectM, int(round(fps)))

    def get_mesh_size(self):
        mesh_x = ctypes.c_size_t()
        mesh_y = ctypes.c_size_t()
        self.projectm_lib.projectm_get_mesh_size(self._projectM, ctypes.byref(mesh_x), ctypes.byref(mesh_y))
        return mesh_x.value, mesh_y.value