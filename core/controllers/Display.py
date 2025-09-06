import ctypes
import logging
import os
import pyudev
import threading
import time

from lib.abstracts import Controller
from lib.common import execute_managed, load_library

log = logging.getLogger()

class drmModeModeInfo(ctypes.Structure):
    _fields_ = [
        ("clock", ctypes.c_uint32),
        ("hdisplay", ctypes.c_uint16),
        ("hsync_start", ctypes.c_uint16),
        ("hsync_end", ctypes.c_uint16),
        ("htotal", ctypes.c_uint16),
        ("hskew", ctypes.c_uint16),
        ("vdisplay", ctypes.c_uint16),
        ("vsync_start", ctypes.c_uint16),
        ("vsync_end", ctypes.c_uint16),
        ("vtotal", ctypes.c_uint16),
        ("vscan", ctypes.c_uint16),
        ("vrefresh", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("name", ctypes.c_char * 32),
    ]

class drmModeConnector(ctypes.Structure):
    DRM_MODE_FLAG_INTERLACE = 0x10

    DRM_MODE_CONNECTED = 1
    DRM_MODE_DISCONNECTED = 2
    DRM_MODE_UNKNOWNCONNECTION = 3

    DRM_MODE_CONNECTOR_Unknown = 0
    DRM_MODE_CONNECTOR_VGA = 1
    DRM_MODE_CONNECTOR_DVII = 2
    DRM_MODE_CONNECTOR_DVID = 3
    DRM_MODE_CONNECTOR_DVIA = 4
    DRM_MODE_CONNECTOR_Composite = 5
    DRM_MODE_CONNECTOR_SVIDEO = 6
    DRM_MODE_CONNECTOR_LVDS = 7
    DRM_MODE_CONNECTOR_Component = 8
    DRM_MODE_CONNECTOR_9PinDIN = 9
    DRM_MODE_CONNECTOR_DisplayPort = 10
    DRM_MODE_CONNECTOR_HDMIA = 11
    DRM_MODE_CONNECTOR_HDMIB = 12
    DRM_MODE_CONNECTOR_TV = 13
    DRM_MODE_CONNECTOR_eDP = 14
    DRM_MODE_CONNECTOR_VIRTUAL = 15
    DRM_MODE_CONNECTOR_DSI = 16
    DRM_MODE_CONNECTOR_DPI = 17
    DRM_MODE_CONNECTOR_WRITEBACK = 18
    DRM_MODE_CONNECTOR_SPI = 19

    _fields_ = [
        ("connector_id", ctypes.c_uint32),
        ("encoder_id", ctypes.c_uint32),
        ("connector_type", ctypes.c_uint32),
        ("connector_type_id", ctypes.c_uint32),
        ("connection", ctypes.c_int),
        ("mmWidth", ctypes.c_uint32),
        ("mmHeight", ctypes.c_uint32),
        ("subpixel", ctypes.c_int),
        ("count_modes", ctypes.c_int),
        ("modes", ctypes.POINTER(drmModeModeInfo)),
        ("count_props", ctypes.c_int),
        ("props", ctypes.POINTER(ctypes.c_uint32)),
        ("prop_values", ctypes.POINTER(ctypes.c_uint64)),
        ("count_encoders", ctypes.c_int),
        ("encoders", ctypes.POINTER(ctypes.c_uint32)),
    ]

class drmModeRes(ctypes.Structure):
    _fields_ = [
        ("count_fbs", ctypes.c_int),
        ("fbs", ctypes.POINTER(ctypes.c_uint32)),
        ("count_crtcs", ctypes.c_int),
        ("crtcs", ctypes.POINTER(ctypes.c_uint32)),
        ("count_connectors", ctypes.c_int),
        ("connectors", ctypes.POINTER(ctypes.c_uint32)),
        ("count_encoders", ctypes.c_int),
        ("encoders", ctypes.POINTER(ctypes.c_uint32)),
        ("min_width", ctypes.c_int),
        ("max_width", ctypes.c_int),
        ("min_height", ctypes.c_int),
        ("max_height", ctypes.c_int),
    ]

class drmModeEncoder(ctypes.Structure):
    _fields_ = [
        ("encoder_id", ctypes.c_uint32),
        ("encoder_type", ctypes.c_uint32),
        ("crtc_id", ctypes.c_uint32),
        ("possible_crtcs", ctypes.c_uint32),
        ("possible_clones", ctypes.c_uint32),
    ]

class drmModeCrtc(ctypes.Structure):
    _fields_ = [
        ("crtc_id", ctypes.c_uint32),
        ("buffer_id", ctypes.c_uint32),
        ("x", ctypes.c_uint32),
        ("y", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("mode_valid", ctypes.c_int),
        ("mode", drmModeModeInfo),
        ("gamma_size", ctypes.c_int),
    ]


class DisplayCtrl(Controller, threading.Thread):
    """Controller for managing X11 and Wayland display devices"""
    def __init__(self, thread_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event, config)

        self.resolution     = '{}x{}'.format(
            self._config.projectm.get('window.fullscreen.width', 1280),
            self._config.projectm.get('window.fullscreen.height', 720)
            )

        self.libdrm = load_library('drm')

        self.libdrm.drmModeGetResources.argtypes = [ctypes.c_int]
        self.libdrm.drmModeGetResources.restype = ctypes.POINTER(drmModeRes)

        self.libdrm.drmModeFreeResources.argtypes = [ctypes.POINTER(drmModeRes)]
        self.libdrm.drmModeFreeResources.restype = None

        self.libdrm.drmModeGetConnector.argtypes = [ctypes.c_int, ctypes.c_uint32]
        self.libdrm.drmModeGetConnector.restype = ctypes.POINTER(drmModeConnector)

        self.libdrm.drmModeFreeConnector.argtypes = [ctypes.POINTER(drmModeConnector)]
        self.libdrm.drmModeFreeConnector.restype = None

        self.libdrm.drmModeGetEncoder.argtypes = [ctypes.c_int, ctypes.c_uint32]
        self.libdrm.drmModeGetEncoder.restype = ctypes.POINTER(drmModeEncoder)

        self.libdrm.drmModeFreeEncoder.argtypes = [ctypes.POINTER(drmModeEncoder)]
        self.libdrm.drmModeFreeEncoder.restype = None

        self.libdrm.drmModeGetCrtc.argtypes = [ctypes.c_int, ctypes.c_uint32]
        self.libdrm.drmModeGetCrtc.restype = ctypes.POINTER(drmModeCrtc)

        self.libdrm.drmModeFreeCrtc.argtypes = [ctypes.POINTER(drmModeCrtc)]
        self.libdrm.drmModeFreeCrtc.restype = None

        self.display_type = self._get_display_type()

        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='drm')

    def _get_display_type(self): 
        session_type = os.getenv('XDG_SESSION_DESKTOP')

        if session_type == 'LXDE-pi-labwc':
            return 'labwc'
        elif session_type == 'LXDE-pi-wayfire':
            return 'wayfire'
        elif session_type == 'LXDE-pi-x':
            return 'x11'

        return None

    def get_refresh_rate(self, mode):
        if mode.htotal == 0 or mode.vtotal == 0:
            return 0.0
        return float(mode.clock) * 1000.0 / (mode.htotal * mode.vtotal)

    def get_connector_name(self, connector: "drmModeConnector") -> str:
        try:
            prefix = {
                drmModeConnector.DRM_MODE_CONNECTOR_Unknown: "Unknown",
                drmModeConnector.DRM_MODE_CONNECTOR_VGA: "VGA",
                drmModeConnector.DRM_MODE_CONNECTOR_DVII: "DVI-I",
                drmModeConnector.DRM_MODE_CONNECTOR_DVID: "DVI-D",
                drmModeConnector.DRM_MODE_CONNECTOR_DVIA: "DVI-A",
                drmModeConnector.DRM_MODE_CONNECTOR_Composite: "Composite",
                drmModeConnector.DRM_MODE_CONNECTOR_SVIDEO: "SVIDEO",
                drmModeConnector.DRM_MODE_CONNECTOR_LVDS: "LVDS",
                drmModeConnector.DRM_MODE_CONNECTOR_Component: "Component",
                drmModeConnector.DRM_MODE_CONNECTOR_9PinDIN: "DIN",
                drmModeConnector.DRM_MODE_CONNECTOR_DisplayPort: "DP",
                drmModeConnector.DRM_MODE_CONNECTOR_HDMIA: "HDMI-A",
                drmModeConnector.DRM_MODE_CONNECTOR_HDMIB: "HDMI-B",
                drmModeConnector.DRM_MODE_CONNECTOR_TV: "TV",
                drmModeConnector.DRM_MODE_CONNECTOR_eDP: "eDP",
                drmModeConnector.DRM_MODE_CONNECTOR_VIRTUAL: "Virtual",
                drmModeConnector.DRM_MODE_CONNECTOR_DSI: "DSI",
                drmModeConnector.DRM_MODE_CONNECTOR_DPI: "DPI",
                drmModeConnector.DRM_MODE_CONNECTOR_WRITEBACK: "Writeback",
                drmModeConnector.DRM_MODE_CONNECTOR_SPI: "SPI",
            }[connector.connector_type]
        except KeyError:
            prefix = "Unknown"
        return f"{prefix}-{connector.connector_type_id}"

    """Get the supported and current display configuration."""
    def get_display_config(self):
        configs = []

        for card_idx in range(2):
            card_name = f"/dev/dri/card{card_idx}"

            try:
                log.info(f'Attempting to open card {card_name}')
                fd = os.open(card_name, os.O_RDONLY)
            except OSError:
                continue
            if fd < 0:
                continue

            try:
                resources = self.libdrm.drmModeGetResources(fd)
                if not resources:
                    log.error("Unable to get DRM resources")
                    continue

                for i in range(resources.contents.count_connectors):
                    conn_id = resources.contents.connectors[i]
                    conn_ptr = self.libdrm.drmModeGetConnector(fd, conn_id)
                    if not conn_ptr:
                        continue

                    conn = conn_ptr.contents

                    if conn.connection == drmModeConnector.DRM_MODE_CONNECTED:

                        config = {
                            'device': self.get_connector_name(conn),
                            'current_resolution': dict(),
                            'resolutions': dict()
                            }

                        enc_ptr = self.libdrm.drmModeGetEncoder(fd, conn.encoder_id)
                        if enc_ptr:
                            encoder = enc_ptr.contents

                            crtc_ptr = self.libdrm.drmModeGetCrtc(fd, encoder.crtc_id)
                            if crtc_ptr:
                                crtc = crtc_ptr.contents
                                if crtc.mode_valid:
                                    mode = crtc.mode
                                    is_interlaced = bool(mode.flags & drmModeConnector.DRM_MODE_FLAG_INTERLACE)
                                    scan_type = "i" if is_interlaced else ""

                                    resolution = f'{mode.hdisplay}x{mode.vdisplay}{scan_type}'
                                    refresh_rate = mode.vrefresh
                                    config['current_resolution'][resolution] = refresh_rate

                                self.libdrm.drmModeFreeCrtc(crtc_ptr)

                            self.libdrm.drmModeFreeEncoder(enc_ptr)

                        for j in range(conn.count_modes):
                            mode = conn.modes[j]
                            is_interlaced = bool(mode.flags & drmModeConnector.DRM_MODE_FLAG_INTERLACE)
                            scan_type = "i" if is_interlaced else ""

                            resolution = f'{mode.hdisplay}x{mode.vdisplay}{scan_type}'
                            refresh_rate = mode.vrefresh

                            if not config['resolutions'].get(resolution):
                                config['resolutions'][resolution] = [refresh_rate]
                            else:
                                config['resolutions'][resolution].append(refresh_rate)

                        configs.append(config)

                    self.libdrm.drmModeFreeConnector(conn_ptr)
            finally:
                os.close(fd)

        return configs

    """Enforce the desired resolution on an X11 display.
    @param display_config: the display configuration dictionary obtained from get_display_config
    """
    def _enforce_x_resolution(self, configs):
        for config in configs:
            if config['current_resolution'].get(self.resolution):
                log.debug(f'{config["device"]} already set to {self.resolution}')
                continue

            elif config['resolutions'].get(self.resolution):
                device, connector, output = config['device'].split('-')
                x11_device = f'{device}-{output}'

                log.info(f'Setting {x11_device} to {self.resolution}')
                success = execute_managed([
                    'xrandr', '--output', x11_device,
                    '--mode', self.resolution
                ])

                if not success:
                    log.error(f'Failed to set resolution on {config["device"]}')

            else:
                log.error(f'Unable to find {self.resolution} in {config["resolutions"].keys()}')
    
    """Enforce the desired resolution on an Wayland display.
    @param display_config: the display configuration dictionary obtained from get_display_config
    """
    def _enforce_wayland_resolution(self, configs):
        for config in configs:
            if config['current_resolution'].get(self.resolution):
                log.debug(f'{config["device"]} already set to {self.resolution}')
                continue

            elif config['resolutions'].get(self.resolution):
                log.info(f'Setting {config["device"]} to {self.resolution}')
                success = execute_managed([
                    'wlr-randr', '--output', config['device'],
                    '--mode', self.resolution
                ])

                if not success:
                    log.error(f'Failed to set {self.resolution} on {config["device"]}')

            else:
                log.error(f'Unable to find {self.resolution} in {config["resolutions"].keys()}')

    """Enforce the desired resolution based on the current display type"""
    def enforce_resolution(self):
        config = self.get_display_config()

        if self.display_type == 'x11':
            self._enforce_x_resolution(config)
        elif self.display_type in ('wayfire', 'labwc'):
            self._enforce_wayland_resolution(config)
        else:
            log.error(f'Unsupported display type: {self.display_type}')

    """Get diagnostics information about the current display configuration"""
    def get_diagnostics(self):
        return self.get_display_config()

    """Run the display controller thread"""
    def run(self):
        if self._environment == 'desktop':
            self.enforce_resolution()

            log.info("Listening for display changes...")

            while not self._thread_event.is_set():
                if self._environment == 'desktop':
                    try:
                        device = self.monitor.poll(timeout=1)
                        if device is None:
                            continue
                    
                        if device.action in ('change', 'add', 'remove'):
                            log.warning(f'Detected a display {device.action} event')

                            self.enforce_resolution()

                    except Exception as e:
                        log.error(f'Failed to enforce resolution: {e}')

                time.sleep(1)

    def close(self):
        pass