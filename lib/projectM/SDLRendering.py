import ctypes
import logging
import sdl2

from lib.common import get_environment

log = logging.getLogger()

class SDLRendering:
    def __init__(self, projectm_config):
        self.projectm_config = projectm_config
        self.rendering_window = None
        self.gl_context = None

        self._fullscreen = False
        self.last_window_width = ctypes.c_int()
        self.last_window_height = ctypes.c_int()

        self.create_sdl_window()

    def uninitialize(self):
        sdl2.SDL_GL_DeleteContext(self.gl_context)
        sdl2.SDL_DestroyWindow(self.rendering_window)
        self.rendering_window = None
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_VIDEO)

    def get_drawable_size(self, width, height):
        sdl2.SDL_GL_GetDrawableSize(self.rendering_window, width, height)

    def toggle_fullscreen(self):
        if self._fullscreen:
            self.windowed()
        else:
            self.fullscreen()

    def fullscreen(self):
        sdl2.SDL_GetWindowSize(self.rendering_window, self.last_window_width, self.last_window_height)
        sdl2.SDL_ShowCursor(False)
        
        fullscreen_width = self.projectm_config.get('window.fullscreen.width', 1280)
        fullscreen_height = self.projectm_config.get('window.fullscreen.height', 720)
        if get_environment() == 'lite':
            
            if (fullscreen_width > 0 and fullscreen_height > 0):
                sdl2.SDL_RestoreWindow(self.rendering_window)
                sdl2.SDL_SetWindowSize(self.rendering_window, fullscreen_width, fullscreen_height)

            sdl2.SDL_SetWindowFullscreen(self.rendering_window, sdl2.SDL_WINDOW_FULLSCREEN)

        else:
            sdl2.SDL_SetWindowFullscreen(self.rendering_window, sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP)
    
        self._fullscreen = True

    def windowed(self):
        sdl2.SDL_SetWindowFullscreen(self.rendering_window, 0)
        sdl2.SDL_SetWindowBordered(self.rendering_window, sdl2.SDL_FALSE if self.projectm_config.get('window.borderless', False) else sdl2.SDL_TRUE)

        width = self.last_window_width.value
        height = self.last_window_height.value

        if (width > 0 and height > 0):
            sdl2.SDL_SetWindowSize(self.rendering_window, width, height)
            sdl2.SDL_ShowCursor(True)

        self._fullscreen = False

    def show_cursor(self, visible=False):
        sdl2.SDL_ShowCursor(visible)

    def swap(self):
        sdl2.SDL_GL_SwapWindow(self.rendering_window)

    def set_sdl_window_title(self, title):
        sdl2.SDL_SetWindowTitle(self.rendering_window, title)

    def create_sdl_window(self):
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO):
            log.error("SDL_Init Error:", sdl2.SDL_GetError())
            return

        # TODO: Set display bounds

        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MAJOR_VERSION, 2)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_MINOR_VERSION, 1)
        sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_CONTEXT_PROFILE_MASK, sdl2.SDL_GL_CONTEXT_PROFILE_CORE)
        # sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DOUBLEBUFFER, 1)
        # sdl2.SDL_GL_SetAttribute(sdl2.SDL_GL_DEPTH_SIZE, 24)

        width = self.projectm_config.get('window.width', 800)
        height = self.projectm_config.get('window.height', 600)
        left = self.projectm_config.get('window.left', 0)
        top = self.projectm_config.get('window.top', 0)

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

        if self.projectm_config.get('window.fullscreen', False):
            self.fullscreen()
        else:
            self.windowed()

    def update_swap_interval(self):
        if self.projectm_config.get('window.waitforverticalsync', True):
            sdl2.SDL_GL_SetSwapInterval(0)
            return

        if self.projectm_config.get('window.adaptiveverticalsync', True):
            if sdl2.SDL_GL_SetSwapInterval(-1) == 0:
                return
