import logging

logging.basicConfig(level=logging.INFO)

import uvicorn

from utils import cfg
from db import get_session_manager
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

    app.add_event_handler('startup', get_session_manager().init_models)
    app.add_event_handler('startup', llama.get_llama_pipeline)
    uvicorn.run("manager:app", reload=False, host=HOST, port=int(PORT))

# TODO: switch to SessionManger factory get_session_manager.
# TODO: switch from get from env something functions to PydanticSettings.
# TODO: add streaming endpoint.
# TODO: bring better logging.
# TODO: bring better error handling and raising. truncate traceback up to project's files excluding .venv modules.
# TODO: a initial way to compress chat history.
