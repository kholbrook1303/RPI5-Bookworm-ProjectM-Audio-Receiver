import json
import logging
import logging.handlers

from datetime import datetime

loggers = {}
log = logging.getLogger()

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for logging messages"""
    def formatException(self, exc_info):
        result = super(JsonFormatter, self).formatException(exc_info)
        json_result = {
        "timestamp": f"{datetime.now()}",
        "level": "ERROR",
        "Module": "projectMAR",
        "message": f"{result}",
        }
        return json.dumps(json_result)

"""Initialize the logging system with a JSON formatter
@param name: the name of the logger or file to log to
@param level: the logging level (default is DEBUG)
@param kwargs: additional keyword arguments for configuring the logger
"""
def log_init(name, level=logging.DEBUG, **kwargs):
    json_formatter = JsonFormatter(
        '{"timestamp":"%(asctime)s", "level":"%(levelname)s", "Module":"%(module)s", "message":"%(message)s"}'
        )

    if name.endswith('.log'):
        hdlr = logging.handlers.TimedRotatingFileHandler(
            name,
            when=kwargs.get('frequency', 'midnight'),
            interval=kwargs.get('interval', 1),
            backupCount=kwargs.get('backups', 5)
            )
        hdlr.setFormatter(json_formatter)
        hdlr.setLevel(level)

    if name == "console":
        hdlr = logging.StreamHandler()
        hdlr.setFormatter(json_formatter)
        hdlr.setLevel(level)
       
    loggers[name] = hdlr
    log.addHandler(hdlr)
    log.setLevel(level)