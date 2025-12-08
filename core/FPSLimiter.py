import sdl2

class FPSLimiter:
    """
    Limits FPS by adding a delay if necessary.
    Also keeps track of actual FPS.
    """

    def __init__(self):
        self._last_tick_count = 0
        self._target_frame_time = 0
        self._last_frame_times = [0] * 10
        self._next_frame_times_offset = 0

    def target_fps(self, fps: int):
        """
        Sets the target frames per second value.
        :param fps: Targeted frames per second. Set to 0 for unlimited FPS.
        """
        if fps > 0:
            self._target_frame_time = int(1000 / fps)
        else:
            self._target_frame_time = 0

    def fps(self) -> float:
        """
        Calculates the current real FPS as an average over the last ten frames.
        Returns 0 if all frame times are zero.
        """
        valid_times = [t for t in self._last_frame_times if t > 0]
        if not valid_times:
            return 0.0

        avg_frame_time = sum(valid_times) / len(valid_times)
        return 1000.0 / avg_frame_time

    def start_frame(self):
        """
        Marks the start of a new frame.
        Should be the first call in the render loop.
        """
        self._last_tick_count = sdl2.SDL_GetTicks()

    def end_frame(self):
        """
        Marks the end of a frame.
        Will pause if required to lower FPS to target value.
        Also records the last frame time for FPS calculation.
        """
        frame_time = sdl2.SDL_GetTicks() - self._last_tick_count

        if self._target_frame_time and frame_time < self._target_frame_time:
            sdl2.SDL_Delay(self._target_frame_time - frame_time)
            frame_time = sdl2.SDL_GetTicks() - self._last_tick_count

        self._last_frame_times[self._next_frame_times_offset] = frame_time
        self._next_frame_times_offset = (self._next_frame_times_offset + 1) % 10
