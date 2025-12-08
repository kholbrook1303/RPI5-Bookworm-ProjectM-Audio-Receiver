import ctypes
import logging
import sdl2

from lib.common import get_environment

log = logging.getLogger()

class SDLRenderingWindow:
    def __init__(self, config):
        self.config = config
        self.rendering_window = None
        self.gl_context = None

        self.fullscreen_active = False
        self.last_window_width = ctypes.c_int()
        self.last_window_height = ctypes.c_int()

        self.controllers = list()

        self.create_sdl_window()

    def close(self):
        log.info('Destroying SDL rendering window')
        self.destroy_sdl_window()

    def get_drawable_size(self, width, height):
        sdl2.SDL_GL_GetDrawableSize(self.rendering_window, width, height)

    def swap(self):
        sdl2.SDL_GL_SwapWindow(self.rendering_window)

    def toggle_fullscreen(self):
        if get_environment() != 'lite':
            if self.fullscreen_active:
                self.windowed()
            else:
                self.fullscreen()

    def fullscreen(self):
        sdl2.SDL_GetWindowSize(self.rendering_window, self.last_window_width, self.last_window_height)
        sdl2.SDL_ShowCursor(False)
        
        fullscreen_width = self.config.projectm.get('window.fullscreen.width', 1280)
        fullscreen_height = self.config.projectm.get('window.fullscreen.height', 720)
        if get_environment() == 'lite':
            
            if (fullscreen_width > 0 and fullscreen_height > 0):
                sdl2.SDL_RestoreWindow(self.rendering_window)
                sdl2.SDL_SetWindowSize(self.rendering_window, fullscreen_width, fullscreen_height)

            sdl2.SDL_SetWindowFullscreen(self.rendering_window, sdl2.SDL_WINDOW_FULLSCREEN)

        else:
            sdl2.SDL_SetWindowFullscreen(self.rendering_window, sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP)
    
        self.fullscreen_active = True

    def windowed(self):
        sdl2.SDL_SetWindowFullscreen(self.rendering_window, 0)
        sdl2.SDL_SetWindowBordered(
            self.rendering_window, 
            sdl2.SDL_FALSE if self.config.projectm.get('window.borderless', False) else sdl2.SDL_TRUE
            )

        width = self.last_window_width.value
        height = self.last_window_height.value

        if (width > 0 and height > 0):
            sdl2.SDL_SetWindowSize(self.rendering_window, width, height)
            sdl2.SDL_ShowCursor(True)

        self.fullscreen_active = False

    def show_cursor(self, visible=False):
        sdl2.SDL_ShowCursor(visible)

    def set_sdl_window_title(self, title):
        sdl2.SDL_SetWindowTitle(self.rendering_window, title)

    def create_sdl_window(self):
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_JOYSTICK):
            log.error("SDL_Init Error:", sdl2.SDL_GetError())
            return

        width = self.config.projectm.get('window.width', 800)
        height = self.config.projectm.get('window.height', 600)
        left = self.config.projectm.get('window.left', 0)
        top = self.config.projectm.get('window.top', 0)
        positionOverridden = self.config.projectm.get('window.overrideposition', False)

        if not positionOverridden:
            left = sdl2.SDL_WINDOWPOS_UNDEFINED
            top = sdl2.SDL_WINDOWPOS_UNDEFINED

        display = self.config.projectm.get('window.monitor', 0)
        if display > 0:
            numDisplays = sdl2.SDL_GetNumVideoDisplays();
            if (display > numDisplays):
                display = numDisplays

            bounds = sdl2.SDL_Rect()
            result = sdl2.SDL_GetDisplayBounds(display - 1, bounds);

            if positionOverridden:
                left += bounds.x
                top += bounds.y
            else:
                left = bounds.x
                top = bounds.y

        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 2)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 0)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_PROFILE_MASK, sdl2.SDL_GL_CONTEXT_PROFILE_ES)

        self.rendering_window = sdl2.SDL_CreateWindow(
            b"projectM Python SDL2", left, top, width, height, 
            sdl2.SDL_WINDOW_OPENGL | sdl2.SDL_WINDOW_RESIZABLE | sdl2.SDL_WINDOW_ALLOW_HIGHDPI
        )
        if not self.rendering_window:
            log.error("SDL_CreateWindow Error:", sdl2.SDL_GetError())
            sdl2.SDL_Quit()
            return

        self.gl_context = sdl2.SDL_GL_CreateContext(self.rendering_window)
        if not self.gl_context:
            log.error("SDL_GL_CreateContext Error:", sdl2.SDL_GetError())
            sdl2.SDL_DestroyWindow(self.rendering_window)
            sdl2.SDL_Quit()
            return

        self.set_sdl_window_title(b"projectM")
        sdl2.SDL_GL_MakeCurrent(self.rendering_window, self.gl_context)
        self.update_swap_interval()

        if get_environment() == 'lite' or self.config.projectm.get('window.fullscreen', False):
            self.fullscreen()
        else:
            self.windowed()

    def destroy_sdl_window(self):
        sdl2.SDL_GL_DeleteContext(self.gl_context)
        sdl2.SDL_DestroyWindow(self.rendering_window)
        self.rendering_window = None
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_JOYSTICK)

    def update_swap_interval(self):
        if self.config.projectm.get('window.waitforverticalsync', True):
            sdl2.SDL_GL_SetSwapInterval(0)
            return

        if self.config.projectm.get('window.adaptiveverticalsync', True):
            if sdl2.SDL_GL_SetSwapInterval(-1) == 0:
                return
