import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

import uvicorn

from utils import cfg
from db import SessionManager
from utils.downloader import predownload
from endpoints import app
from pipelines import llama

if __name__ == '__main__':

    if cfg.get_debug_state():
        logging.getLogger().setLevel(logging.DEBUG)

    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    predownload('binaries.yaml', 'models.yaml')

    HOST = cfg.get_host()
    PORT = cfg.get_port()

    sm = SessionManager()
    app.add_event_handler('startup', sm.init_models)
    app.add_event_handler('startup', llama.get_llama_pipeline)
    uvicorn.run(app, host=HOST, port=int(PORT),
                log_config={"version": 1, "disable_existing_loggers": False,
                            "streams":
                                {
                                    "default":
                                        {
                                            "class": "logging.StreamHandler",
                                            "stream": sys.stdout
                                        }
                                }
                            }
                )

# TODOList 1:
# TODO: create a user (crud, service) [-]
# TODO: get user_id from jwt web token instead of request [-]
# TODO: figure out a way to securely serve telegram users [-]
#
# TODOList 2:
# TODO: add streaming endpoint [-]
# TODO: a initial way to compress chat history [-]
# TODO: delete first parental key in .yaml because not necessary [-] (binaries.yaml -> ['binaries'][helpful configs])