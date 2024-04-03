import json
import logging
import logging.handlers

from datetime import datetime

loggers = {}
log = logging.getLogger()

class JsonFormatter(logging.Formatter):
    def formatException(self, exc_info):
        result = super(JsonFormatter, self).formatException(exc_info)
        json_result = {
        "timestamp": f"{datetime.now()}",
        "level": "ERROR",
        "Module": "projectMAR",
        "message": f"{result}",
        }
        return json.dumps(json_result)

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