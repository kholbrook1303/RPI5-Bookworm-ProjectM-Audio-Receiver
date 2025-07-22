import logging
import os
import re
import threading
import time

from lib.abstracts import Controller

log = logging.getLogger()

class DisplayCtrl(Controller, threading.Thread):
    """Controller for managing X11 and Wayland display devices"""
    def __init__(self, thread_event, refresh_event, config):
        threading.Thread.__init__(self)
        super().__init__(thread_event)

        self.config         = config
        self.display_type   = os.environ.get('XDG_SESSION_TYPE', None)
        self.thread_event   = thread_event
        self.refresh_event  = refresh_event
        self.resolution     = self.config.display_ctrl.get('resolution', '1280x720')

    """Get the supported and current display configuration for X11"""
    def _get_x_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': dict()
        }

        device = None
        randr = self._execute('xrandr', 'xrandr', ['xrandr'])
        for line in self._read_stream(randr.process.stdout):
            log.debug('xrandr output: {}'.format(line))
            device_match = re.match(r'^(?P<device>\S+)\sconnected', line)
            if device_match:
                device = device_match.group('device')
                display_config['device'] = device
                continue

            res_match = re.match(r'^.*?(?P<resolution>\d+x\d+)\s+(?P<refreshRates>\d{2}\.\d{2}.*?)$', line)
            if res_match and device:
                resolution = res_match.group('resolution')
                refresh_rates = res_match.group('refreshRates').replace('+', '')
                for refresh_rate in refresh_rates.split():
                    if '*' in refresh_rate:
                        display_config['current_resolution'] = resolution

                    clean_rate = refresh_rate.replace('*', '')
                    if self.resolution == resolution:
                        display_config['resolutions'].setdefault(resolution, []).append(clean_rate)

        return display_config

    """Enforce the desired resolution on an X11 display.
    @param display_config: the display configuration dictionary obtained from _get_x_display_config
    """
    def _enforce_x_resolution(self, display_config):
        if not display_config['current_resolution']:
            log.warning('There is currently no display connected: {}'.format(display_config))  
        elif display_config['current_resolution'] == self.resolution:
            log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
        else:
            res_profile = display_config['resolutions'].get(self.resolution)
            log.info('Setting resolution to {} refresh rate to {}'.format(self.resolution, max(res_profile)))
            self.refresh_event.set()

            success = self._execute_managed([
                'xrandr', '--output', display_config['device'], 
                '--mode', self.resolution, '--rate', max(res_profile)
                ])

            if not success:
                log.error('Failed to set resolution on X11 display!')
                
    """Get the supported and current display configuration for Wayland"""
    def _get_wayland_display_config(self):
        display_config = {
            'device': None,
            'description': None,
            'current_resolution': None,
            'resolutions': list()
        }

        device = None
        randr = self._execute('wlr-randr', 'wlr-randr', ['wlr-randr'])
        for line in self._read_stream(randr.process.stdout):
            log.debug('wlr-randr output: {}'.format(line))
            device_match = re.match(r'^(?P<device>\S+)\s"(?P<description>.+)"', line)
            if device_match:
                device = device_match.group('device')
                display_config['device'] = device
                display_config['description'] = device_match.group('description')
                continue

            res_match = re.match(r'^.*?(?P<resolution>\d+x\d+)\spx,\s(?P<refreshRate>\d+\.\d+)\sHz', line)
            if res_match:
                res = res_match.group('resolution')
                rate = res_match.group('refreshRate')
                res_str = f"{res}@{rate}Hz"

                if self.resolution == res:
                    display_config['resolutions'].append(res_str)

                if 'current' in line:
                    display_config['current_resolution'] = res_str

        return display_config

    """Enforce the desired resolution on an Wayland display.
    @param display_config: the display configuration dictionary obtained from _get_wayland_display_config
    """
    def _enforce_wayland_resolution(self, display_config):
        if len(display_config['resolutions']) == 0:
            log.warning('There is currently no display connected: {}'.format(display_config))  
        elif display_config['current_resolution'] == max(display_config['resolutions']):
            log.debug('Resolution is already set to {}'.format(max(display_config['resolutions'])))
        else:
            log.info('Setting resolution to {}'.format(max(display_config['resolutions'])))
            self.refresh_event.set()

            success = self._execute_managed([
                'wlr-randr', '--output', display_config['device'], 
                '--mode', max(display_config['resolutions'])
                ])

            if not success:
                log.error('Failed to set resolution on Wayland display!')

    """Get the display configuration based on the current display type"""
    def get_display_config(self):
        if self.display_type == 'x11':
            return self._get_x_display_config()
        elif self.display_type == 'wayland':
            return self._get_wayland_display_config()
        else:
            raise Exception('Display type {} is not currently supported!'.format(self.display_type))

    """Enforce the desired resolution based on the current display type"""
    def enforce_resolution(self):
        display_config = self.get_display_config()

        if self.display_type == 'x11':
            return self._enforce_x_resolution(display_config)
        elif self.display_type == 'wayland':
            return self._enforce_wayland_resolution(display_config)
        else:
            raise Exception('Display type {} is not currently supported!'.format(self.display_type))

    """Get diagnostics information about the current display configuration"""
    def get_diagnostics(self):
        return self.get_display_config()

    """Run the display controller thread"""
    def run(self):
        while not self.thread_event.is_set():
            if self._environment == 'desktop':
                try:
                    self.enforce_resolution()
                except:
                    log.error('Failed to enforce resolution!')

            time.sleep(5)

    def close(self):
        pass