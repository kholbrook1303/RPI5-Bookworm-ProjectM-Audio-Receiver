import ctypes
import logging
import sdl2
import signal
import time

from OpenGL import GL

from lib.common import get_environment

from core.controllers.Audio import AudioCtrl, PhysicalMediaCtrl
from core.controllers.Display import DisplayCtrl
from core.controllers.Plugins import PluginCtrl
from core.InputEventListener import InputEventListener, EVDEV_INSTALLED

from core.ProjectMWrapper import ProjectMWrapper
from core.SDLRenderingWindow import SDLRenderingWindow
from core.AudioCapture import AudioCapture

log = logging.getLogger()

CONTROLLER_DEADZONE = 10000  # adjust as needed (range is -32768 to 32767)

class SignalMonitor:
    """Monitor for system signals to gracefully exit the application"""
    exit = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.set_exit)
        signal.signal(signal.SIGTERM, self.set_exit)

    def set_exit(self, signum, frame):
        self.exit = True

class RenderingLoop:
    CONTROLLER_REGISTRY = [
        ('audio_ctrl', AudioCtrl),
        ('plugin_ctrl', PluginCtrl),
        ('display_ctrl', DisplayCtrl)
    ]

    def __init__(self, config, thread_event):
        self.config             = config
        self.ctrl_threads       = list()
        self.signal_event       = SignalMonitor()
        self.thread_event       = thread_event
        self.input_event_lstn   = InputEventListener()
        
        self.sdl_rendering      = SDLRenderingWindow(self.config)
        self.projectm_wrapper   = ProjectMWrapper(self.config, self.sdl_rendering)
        self.audio_capture      = AudioCapture(self.config, self.projectm_wrapper)

        if self.config.audio_ctrl.get('audio_listener_enabled', False):
            handler = PhysicalMediaCtrl(self.thread_event, self.config)
            handler.start()
            self.ctrl_threads.append(handler)

        for config_key, ControllerClass in self.CONTROLLER_REGISTRY:
            if self.config.general.get(config_key, False):
                handler = ControllerClass(self.thread_event, self.config)
                handler.start()
                self.ctrl_threads.append(handler)

        self.controller_axis_states = {
            sdl2.SDL_CONTROLLER_AXIS_LEFTX: 'NEUTRAL',
            sdl2.SDL_CONTROLLER_AXIS_LEFTY: 'NEUTRAL',
            sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 'NEUTRAL',
            sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 'NEUTRAL',
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 'NEUTRAL',
            sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 'NEUTRAL',
        }

        self._renderWidth = None
        self._renderHeight = None

    def __del__(self):
        for controller in self.ctrl_threads:
            controller.join()
            controller.close()

    def run(self):
        if EVDEV_INSTALLED and get_environment() == 'lite':
            # Start evdev input thread
            self.input_event_lstn.start_evdev_listener()

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

        if self.signal_event.exit:
            self.thread_event.set()

        del self.audio_capture
        del self.projectm_wrapper
        del self.sdl_rendering

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
        if self.projectm_wrapper.current_preset_start:
            duration = time.time() - self.projectm_wrapper.current_preset_start
            if duration >= (self.config.projectm.get("projectm.displayduration", 60)):
                return True

        return False
            
    def key_event(self, event, key_down):
        key_modifier = event.key.keysym.mod
        modifier_pressed = False

        if (key_modifier & sdl2.KMOD_LCTRL) or (key_modifier & sdl2.KMOD_RCTRL):
            modifier_pressed = True

        match event.key.keysym.sym:
            case sdl2.SDLK_f:
                if modifier_pressed:
                    self.sdl_rendering.toggle_fullscreen()

            # Removing since audio routing is controlled by projectMAR
            # case sdl2.SDLK_i:
            #     if modifier_pressed:
            #         self.audio_capture.next_audio_device()

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
                log.warning(f'User has opted to remove preset {self.projectm_wrapper.current_preset}')
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

    def controller_axis_event(self, event):
        axis = event.caxis.axis
        value = event.caxis.value

        prev_state = self.controller_axis_states.get(axis, 'NEUTRAL')
        state = 'NEUTRAL'

        # Determine direction based on axis
        if axis in (sdl2.SDL_CONTROLLER_AXIS_LEFTX, sdl2.SDL_CONTROLLER_AXIS_RIGHTX):
            if value < -CONTROLLER_DEADZONE:
                state = 'LEFT'
            elif value > CONTROLLER_DEADZONE:
                state = 'RIGHT'

        elif axis in (sdl2.SDL_CONTROLLER_AXIS_LEFTY, sdl2.SDL_CONTROLLER_AXIS_RIGHTY):
            if value < -CONTROLLER_DEADZONE:
                state = 'UP'
            elif value > CONTROLLER_DEADZONE:
                state = 'DOWN'

        elif axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:
            if value > CONTROLLER_DEADZONE:
                state = 'PRESSED'

        elif axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
            if value > CONTROLLER_DEADZONE:
                state = 'PRESSED'

        # Only trigger action if state changes
        if state != prev_state:
            self.controller_axis_states[axis] = state

            match (axis, state):
                case (sdl2.SDL_CONTROLLER_AXIS_LEFTX, 'LEFT') | (sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT, 'PRESSED'):
                    self.projectm_wrapper.previous_preset()
                    log.debug('User has requested the previous preset')

                case (sdl2.SDL_CONTROLLER_AXIS_LEFTX, 'RIGHT') | (sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 'PRESSED'):
                    self.projectm_wrapper.next_preset()
                    log.debug('User has requested the next preset')

                case (sdl2.SDL_CONTROLLER_AXIS_LEFTY, 'UP'):
                    self.projectm_wrapper.change_beat_sensitivity(0.1)

                case (sdl2.SDL_CONTROLLER_AXIS_LEFTY, 'DOWN'):
                    self.projectm_wrapper.change_beat_sensitivity(-0.1)

                case _:
                    log.debug(f"Unhandled controller axis {hex(axis)} state {state}")


    def controller_button_event(self, event, button_down):
        button = event.cbutton.button

        match event.cbutton.button:
            case sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK | sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK:
                self.projectm_wrapper.toggle_preset_lock()

            case sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                self.projectm_wrapper.change_beat_sensitivity(0.1)

            case sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                self.projectm_wrapper.change_beat_sensitivity(-0.1)

            case sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                self.projectm_wrapper.previous_preset()
                log.debug('User has requested the previous preset')

            case sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                self.projectm_wrapper.next_preset()
                log.debug('User has requested the next preset')

            case _:
                log.info(f'unhandled controller button {hex(button)}')
                pass

    def window_event(self, event):
        match event.window.event:
            case sdl2.SDL_WINDOWEVENT_CLOSE:
                self.thread_event.set()

            case sdl2.SDL_WINDOWEVENT_RESIZED | sdl2.SDL_WINDOWEVENT_SIZE_CHANGED:
                w, h = ctypes.c_int(), ctypes.c_int()
                sdl2.SDL_GetWindowSize(self.sdl_rendering.rendering_window, ctypes.byref(w), ctypes.byref(h))
                width, height = w.value, h.value

                self.projectm_wrapper.set_window_size(width, height)

            case sdl2.SDL_WINDOWEVENT_HIDDEN | sdl2.SDL_WINDOWEVENT_MINIMIZED:
                log.debug('Restoring the window!')
                sdl2.SDL_RestoreWindow(self.sdl_rendering.rendering_window)
                sdl2.SDL_ShowWindow(self.sdl_rendering.rendering_window)

            case sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
                log.warning("Window lost focus")

            case sdl2.SDL_WINDOWEVENT_FOCUS_GAINED:
                log.debug("Window regained focus")

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

                case sdl2.SDL_CONTROLLERAXISMOTION:
                    self.controller_axis_event(event)

                case sdl2.SDL_CONTROLLERBUTTONDOWN:
                    self.controller_button_event(event, True)

                case sdl2.SDL_CONTROLLERBUTTONUP:
                    pass
                    
                case sdl2.SDL_MOUSEBUTTONDOWN:
                    if event.button.button == sdl2.SDL_BUTTON_RIGHT:
                        self.sdl_rendering.toggle_fullscreen()

                case sdl2.SDL_FINGERDOWN:
                    if self.config.projectm.get('touch.enabled', True):
                        rotation = int(self.config.projectm.get('touch.rotation_degrees', 0)) % 360
                        x, y = event.tfinger.x, event.tfinger.y

                        is_left = {
                            0: x < 0.5,
                            90: y < 0.5,
                            180: x >= 0.5,
                            270: y >= 0.5,
                        }.get(rotation, x < 0.5)

                        if is_left:
                            log.debug('Touch on left side - previous preset')
                            self.projectm_wrapper.previous_preset()
                        else:
                            log.debug('Touch on right side - next preset')
                            self.projectm_wrapper.next_preset()

                case sdl2.SDL_WINDOWEVENT:
                    self.window_event(event)

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
