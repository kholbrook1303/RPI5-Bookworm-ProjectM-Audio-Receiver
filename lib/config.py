import os
import sys

from configparser import ConfigParser, RawConfigParser

APP_ROOT = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
        ), '..'
    )   

class Config:
    """Configuration class for loading and managing application settings.
    @param config_path: path to the configuration file.
    @param config_header: optional header to prepend to the configuration file.
    """
    def __init__(self, config_path, config_header=None):
        try:
            if config_header:
                config = RawConfigParser(allow_no_value=True)
                with open(config_path) as config_file:
                    data = config_file.read()
                    config.read_string(config_header + '\n' + data)
                    
            else:
                config = ConfigParser(allow_no_value=True)
                config.read(config_path)

            for section in config.sections():
                setattr(self, section, dict())

                for name, str_value in config.items(section):
                    if name == "audio_plugins":
                        value = config.get(section, name).split(",")
                    elif name == "audio_cards":
                        value = config.get(section, name).split(",")
                    elif name == "audio_sinks":
                        value = config.get(section, name).split(",")
                    elif name == "audio_sources":
                        value = config.get(section, name).split(",")
                    elif name == "card_profile_types":
                        value = config.get(section, name).split(",")
                    elif name == "card_profile_modes":
                        value = config.get(section, name).split(",")
                    elif self._is_str_bool(str_value):
                        value = config.getboolean(section, name)
                    elif self._is_str_int(str_value):
                        value = config.getint(section, name)
                    elif self._is_str_float(str_value):
                        value = config.getfloat(section, name)
                    else:
                        value = config.get(section, name)

                    getattr(self, section)[name] = value

        except Exception as e:
            print ("Error loading configuration file", e)
            sys.exit(-1)
        
    """Check if string is a boolean.
    @param value: object to be verified.
    """
    def _is_str_bool(self, value):
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return True

        return False
    
    """Check if string is an float.
    @param value: object to be verified.
    """
    def _is_str_float(self, value):
        try:
            float(value)
            return True
        except:
            return False
        
    """Check if string is an integer.
    @param value: object to be verified.
    """
    def _is_str_int(self, value):
        try:
            int(value)
            return True
        except:
            return False