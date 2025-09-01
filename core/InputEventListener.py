import asyncio
import logging
import threading
import sdl2

log = logging.getLogger()

EVDEV_INSTALLED = False
try:
    import evdev
    EVDEV_INSTALLED = True
except ImportError:
    log.warning('evdev is not installed and therefore will not be used!')

class InputEventListener:
    def __init__(self):
        self.pressed_modifiers  = set()

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