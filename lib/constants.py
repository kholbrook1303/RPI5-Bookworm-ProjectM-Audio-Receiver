class ProcessAttributes:
    """Attributes for a process that is managed by the system.
    @param name: the name of the process
    @param process: the process instance
    @param path: the path to the executable
    @param args: an array of arguments including the executable
    """
    def __init__(self, name, process, path, args):
        self.name           = name
        self.process        = process
        self.path           = path
        self.args           = args
        self.restore        = False
        self.halt_on_exit   = False
        self.trigger        = None

class PluginDevice:
    """Attributes for a plugin device.
    @param device_name: the name of the plugin device
    @param device_index: the index of the plugin device
    @param device_meta: optional metadata for the plugin device
    """
    def __init__(self, device_name, device_index, device_meta=None):
        self.name           = device_name
        self.description    = None
        self.index          = device_index
        self.active         = False
        self.device         = None
        self.type           = 'aux'
        self.meta           = device_meta

class DeviceCatalog:
    """Catalog for managing devices and their attributes"""
    def __init__(self):
        self.card                   = dict()
        self.module                 = dict()
        self.sink                   = dict()
        self.source                 = dict()
        self.sink_cards             = dict()
        self.bluetooth_devices      = dict()
        self.plugin_devices         = dict()
        self.unsupported_sinks      = dict()
        self.unsupported_sources    = dict()