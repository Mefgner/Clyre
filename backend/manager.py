import logging
import sys

import uvicorn

from utils import cfg
from db import SessionManager
from utils.downloader import predownload
from endpoints import app
from pipelines import llama

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    predownload('binaries.yaml', 'models.yaml')

    HOST = cfg.get_host()
    PORT = cfg.get_port()

    sm = SessionManager()
    app.add_event_handler('startup', sm.init_models)
    app.add_event_handler('startup', llama.get_llama_pipeline)

    uvicorn.run(app, host=HOST, port=int(PORT))

# TODOList 1:
# TODO: create a user (crud, service) [-]
# TODO: get user_id from jwt web token instead of request [-]
# TODO: figure out a way to securely pole telegram users [-]
#
# TODOList 2:
# TODO: add streaming endpoint [-]
# TODO: a initial way to compress chat history [-]