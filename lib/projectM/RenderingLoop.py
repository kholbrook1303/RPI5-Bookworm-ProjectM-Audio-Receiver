import asyncio
import ctypes
import logging
import sdl2
import signal
import threading
import time

from OpenGL import GL

from lib.common import get_environment
from lib.projectM.ProjectMWrapper import ProjectMWrapper
from lib.projectM.SDLRendering import SDLRendering
from lib.projectM.AudioCapture import AudioCapture

log = logging.getLogger()

EVDEV_INSTALLED = False
try:
    import evdev
    EVDEV_INSTALLED = True
except ImportError:
    log.warning('evdev is not installed and therefore will not be used!')

PROJECTM_MONO = 1
PROJECTM_STEREO = 2

class SignalMonitor:
    """Monitor for system signals to gracefully exit the application"""
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True

class RenderingLoop:
    def __init__(self, config, thread_event):
        self.config = config
        self.pressed_modifiers = set()

        self.signal_event   = SignalMonitor()
        self.thread_event   = thread_event
        
        self.sdl_rendering      = SDLRendering(self.config)
        self.projectm_wrapper   = ProjectMWrapper(self.config, self.sdl_rendering)
        self.audio_capture      = AudioCapture(self.config, self.projectm_wrapper)

        self._renderWidth = None
        self._renderHeight = None

    def run(self):
        if EVDEV_INSTALLED and get_environment() == 'lite':
            # Start evdev input thread
            self.start_evdev_listener()

        # Start projectM
        self.projectm_wrapper.display_initial_preset()

        while not self.thread_event.is_set() and not self.signal_event.exit:
            self.poll_events()
            self.check_viewport_size()

            # Clear the OpenGL context
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

            # Render projectM frame
            self.projectm_wrapper.render_frame()

            # Swap buffers
            self.sdl_rendering.swap()

            # Frame limiting (simple)
            sdl2.SDL_Delay(int(1000 / self.config.projectm.get("projectm.fps", 60)))

            if self.preset_hung() and not self.projectm_wrapper.get_preset_locked():
                self.simulate_keypress(sdl2.SDLK_n)

        self.audio_capture.uninitialize()

        self.projectm_wrapper.uninitialize()

        self.sdl_rendering.uninitialize()

    """Simulate a keypress
    @param sdl_key: the key to emit
    """
    def simulate_keypress(self, sdl_key):
        try:
            sdl_event = sdl2.SDL_Event()
            sdl_event.type = sdl2.SDL_KEYDOWN
            sdl_event.key.type = sdl2.SDL_KEYDOWN
            sdl_event.key.state = sdl2.SDL_PRESSED
            sdl_event.key.repeat = 0
            sdl_event.key.keysym.sym = sdl_key
            sdl_event.key.keysym.scancode = sdl2.SDL_GetScancodeFromKey(sdl2.SDL_KEYDOWN)
            sdl_event.key.keysym.mod = 0x00

            sdl2.SDL_PushEvent(sdl_event)
        except:
            log.exception('failed to process sdl event!')

    """Check if the preset has been hung for too long"""
    def preset_hung(self):
        if self.projectm_wrapper._current_preset_start:
            duration = time.time() - self.projectm_wrapper._current_preset_start
            if duration >= (self.config.projectm.get("projectm.displayduration", 60)):
                return True

        return False

    def process_audio(self, indata, frames, time, status):
            if status:
                print("[Audio Warning]", status)

            self.projectm_wrapper.add_pcm(indata.flatten(), channels=PROJECTM_STEREO)
            
    def key_event(self, event, key_down):
        key_modifier = event.key.keysym.mod
        modifier_pressed = False

        if (key_modifier & sdl2.KMOD_LCTRL) or (key_modifier & sdl2.KMOD_RCTRL):
            modifier_pressed = True

        match event.key.keysym.sym:
            case sdl2.SDLK_f:
                if modifier_pressed:
                    self.sdl_rendering.toggle_fullscreen()

            case sdl2.SDLK_i:
                if modifier_pressed:
                    self.audio_capture.next_audio_device()

            case sdl2.SDLK_n:
                log.debug('User has requested the next preset')
                self.projectm_wrapper.next_preset()

            case sdl2.SDLK_p:
                self.projectm_wrapper.previous_preset()
                log.debug('User has requested the previous preset')

            case sdl2.SDLK_q:
                if modifier_pressed:
                    log.info('User initiated exit!')
                    self.thread_event.set()

            case sdl2.SDLK_y:
                if modifier_pressed:
                    if self.projectm_wrapper.get_preset_shuffle():
                        self.projectm_wrapper.shuffle_playlist(False)
                    else:
                        log.info('User has initiated playlist shuffling')
                        self.projectm_wrapper.shuffle_playlist(True)

            case sdl2.SDLK_DELETE:
                log.warning(f'User has opted to remove preset {self.projectm_wrapper._current_preset}')
                self.projectm_wrapper.delete_preset(physical=True)

            case sdl2.SDLK_SPACE:
                log.info(f'Preset lock status: {self.projectm_wrapper.get_preset_locked()}')
                if self.projectm_wrapper.get_preset_locked():
                    self.projectm_wrapper.lock_preset(False)
                else:
                    log.info('User has initiated a preset lock')
                    self.projectm_wrapper.lock_preset(True)
            
            case sdl2.SDLK_ESCAPE:
                self.sdl_rendering.toggle_fullscreen()
            
            case sdl2.SDLK_UP:
                self.projectm_wrapper.change_beat_sensitivity(.1)

            case sdl2.SDLK_DOWN:
                self.projectm_wrapper.change_beat_sensitivity(-.1)

            case _:
                pass

    def poll_events(self):
        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:

            match event.type:
                case sdl2.SDL_QUIT:
                    self.thread_event.set()
                    break
                
                case sdl2.SDL_KEYDOWN:
                    self.key_event(event, True)
                    
                case sdl2.SDL_MOUSEBUTTONDOWN:
                    if event.button.button == sdl2.SDL_BUTTON_RIGHT:
                        self.sdl_rendering.toggle_fullscreen()
                        
                case sdl2.SDL_WINDOWEVENT:
                    if event.window.event == sdl2.SDL_WINDOWEVENT_CLOSE:
                        self.thread_event.set()
                        break

                    if event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED or event.window.event == sdl2.SDL_WINDOWEVENT_SIZE_CHANGED:
                        w, h = ctypes.c_int(), ctypes.c_int()
                        sdl2.SDL_GetWindowSize(self.sdl_rendering.rendering_window, ctypes.byref(w), ctypes.byref(h))
                        width, height = w.value, h.value

                        self.projectm_wrapper.set_window_size(width, height)

                    if event.window.event == sdl2.SDL_WINDOWEVENT_HIDDEN or event.window.event == sdl2.SDL_WINDOWEVENT_MINIMIZED:
                        log.debug('Restoring the window!')
                        sdl2.SDL_RestoreWindow(self.sdl_rendering.rendering_window)
                        sdl2.SDL_ShowWindow(self.sdl_rendering.rendering_window)

                    elif event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
                        log.warning("Window lost focus")

                    elif event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_GAINED:
                        log.debug("Window regained focus")

                case _:
                    pass

    def check_viewport_size(self):
        renderWidth = ctypes.c_int()
        renderHeight = ctypes.c_int()

        self.sdl_rendering.get_drawable_size(renderWidth, renderHeight)
        if (renderWidth != self._renderWidth or renderHeight != self._renderHeight):
            self.projectm_wrapper.set_window_size(renderWidth, renderHeight)
            self._renderWidth = renderWidth
            self._renderHeight = renderHeight

    def get_keyboard_devices_by_name(self):
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for device in devices:
            if "keyboard" in device.name.lower():
                return device
            
        return None

    def start_evdev_listener(self):
        """Starts the evdev async loop in a background thread"""
        device = self.get_keyboard_devices_by_name()
        if not device:
            log.warning("No evdev keyboard device found")
            return

        def evdev_loop():
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.evdev_reader(device))

        log.info(f'Using evdev to monitor device {device} input')
        t = threading.Thread(target=evdev_loop, daemon=True)
        t.start()

    async def evdev_reader(self, device):
        EVDEV_TO_SDL_KEYMAP = {
            evdev.ecodes.KEY_F: sdl2.SDLK_f,
            evdev.ecodes.KEY_I: sdl2.SDLK_i,
            evdev.ecodes.KEY_N: sdl2.SDLK_n,
            evdev.ecodes.KEY_P: sdl2.SDLK_p,
            evdev.ecodes.KEY_Q: sdl2.SDLK_q,
            evdev.ecodes.KEY_Y: sdl2.SDLK_y,
            evdev.ecodes.KEY_DELETE: sdl2.SDLK_DELETE,
            evdev.ecodes.KEY_SPACE: sdl2.SDLK_SPACE,
            evdev.ecodes.KEY_ESC: sdl2.SDLK_ESCAPE,
            evdev.ecodes.KEY_UP: sdl2.SDLK_UP,
            evdev.ecodes.KEY_DOWN: sdl2.SDLK_DOWN,
        }

        EVDEV_TO_SDL_KEYMOD = {
            evdev.ecodes.KEY_LEFTCTRL: sdl2.KMOD_LCTRL,
            evdev.ecodes.KEY_RIGHTCTRL: sdl2.KMOD_RCTRL,
            }

        async for event in device.async_read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                key_event = evdev.categorize(event)
                key_code = key_event.scancode
                key_state = key_event.keystate  # 0 = up, 1 = down

                # Track modifier keys
                if key_code in EVDEV_TO_SDL_KEYMOD:
                    if key_state == 1:
                        self.pressed_modifiers.add(EVDEV_TO_SDL_KEYMOD[key_code])
                    else:
                        self.pressed_modifiers.discard(EVDEV_TO_SDL_KEYMOD[key_code])
                    continue  # Don't push modifier keys as SDL events directly

                if key_code not in EVDEV_TO_SDL_KEYMAP:
                    continue

                sdl_key = EVDEV_TO_SDL_KEYMAP[key_code]
                sdl_type = sdl2.SDL_KEYDOWN if key_state == 1 else sdl2.SDL_KEYUP

                # Combine modifiers into SDL-compatible bitmask
                mod_state = 0
                for mod in self.pressed_modifiers:
                    mod_state |= mod

                sdl_event = sdl2.SDL_Event()
                sdl_event.type = sdl_type
                sdl_event.key.type = sdl_type
                sdl_event.key.state = sdl2.SDL_PRESSED if sdl_type == sdl2.SDL_KEYDOWN else sdl2.SDL_RELEASED
                sdl_event.key.repeat = 0
                sdl_event.key.keysym.sym = sdl_key
                sdl_event.key.keysym.scancode = sdl2.SDL_GetScancodeFromKey(sdl_key)
                sdl_event.key.keysym.mod = mod_state

                sdl2.SDL_PushEvent(sdl_event)