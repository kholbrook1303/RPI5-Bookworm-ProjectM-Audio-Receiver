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
        self.device = None
        self.keymap = self.generate_keymap()
        self.modmap = {
            evdev.ecodes.KEY_LEFTCTRL: sdl2.KMOD_LCTRL,
            evdev.ecodes.KEY_RIGHTCTRL: sdl2.KMOD_RCTRL,
            evdev.ecodes.KEY_LEFTSHIFT: sdl2.KMOD_LSHIFT,
            evdev.ecodes.KEY_RIGHTSHIFT: sdl2.KMOD_RSHIFT,
            evdev.ecodes.KEY_LEFTALT: sdl2.KMOD_LALT,
            evdev.ecodes.KEY_RIGHTALT: sdl2.KMOD_RALT,
            evdev.ecodes.KEY_LEFTMETA: sdl2.KMOD_LGUI,
            evdev.ecodes.KEY_RIGHTMETA: sdl2.KMOD_RGUI,
        }

        self.loop = None
        self.thread = None
        self.stop_event = threading.Event()

    def generate_keymap(self):
        """Auto-generate an evdev to SDL keymap using key names."""
        keymap = {}
        for code,name in evdev.ecodes.keys.items():
            if not isinstance(name, str):
                continue

            if not name.startswith('KEY_'):
                continue
            keyname = name[4:].lower()
            sdl_key = sdl2.SDL_GetKeyFromName(keyname.encode())
            if sdl_key != sdl2.SDLK_UNKNOWN:
                keymap[code] = sdl_key

        return keymap

    def get_keyboard_device(self):
        """Try to automatically pick the first keyboard device."""
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            if "keyboard" in dev.name.lower():
                return dev

        return None

    def start_evdev_listener(self):
        """Starts the evdev async loop in a background thread"""
        if self.thread and self.thread.is_alive():
            log.warning("Listener already running")
            return

        self.device = self.get_keyboard_device()
        if not self.device:
            log.warning("No keyboard device found via evdev")
            return

        self.stop_event.clear()

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.evdev_reader())

        log.info(f"Listening to {self.device.name} via evdev")
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def close(self):
        """Signal the async loop to stop and close the device."""
        log.info("Stopping evdev listener")
        if not self.loop:
            return

        self.stop_event.set()

        # Cancel all tasks and stop the event loop
        def stop_loop():
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            self.loop.stop()

        self.loop.call_soon_threadsafe(stop_loop)
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
        log.info("Evdev listener stopped")

    async def evdev_reader(self):
        try:
            async for event in self.device.async_read_loop():
                if self.stop_event.is_set():
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue

                key_event = evdev.categorize(event)
                key_code = key_event.scancode
                key_state = key_event.keystate  # 0 = up, 1 = down

                # Track modifier keys
                if key_code in self.modmap:
                    mod = self.modmap[key_code]
                    if key_state == 1:
                        self.pressed_modifiers.add(mod)
                    else:
                        self.pressed_modifiers.discard(mod)
                    continue  # Don't push modifier keys as SDL events directly

                sdl_key = self.keymap.get(key_code)
                if not sdl_key:
                    log.debug(f'Unmapped evdev key code: {key_code}')
                    continue

                sdl_type = sdl2.SDL_KEYDOWN if key_state else sdl2.SDL_KEYUP

                # Combine modifiers into SDL-compatible bitmask
                mod_state = 0
                for mod in self.pressed_modifiers:
                    mod_state |= mod

                sdl_event = sdl2.SDL_Event()
                sdl_event.type = sdl_type
                sdl_event.key.type = sdl_type
                sdl_event.key.state = (
                    sdl2.SDL_PRESSED if key_state else sdl2.SDL_RELEASED
                )
                sdl_event.key.repeat = 0
                sdl_event.key.keysym.sym = sdl_key
                sdl_event.key.keysym.scancode = sdl2.SDL_GetScancodeFromKey(sdl_key)
                sdl_event.key.keysym.mod = mod_state

                sdl2.SDL_PushEvent(sdl_event)

        except asyncio.CancelledError:
            pass
        finally:
            log.debug("Evdev reader task finished")