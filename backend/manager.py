import uvicorn

import cfg
from db import SessionManager
from downloader import predownload
from endpoints import app
from pipelines import llama

if __name__ == '__main__':
    predownload('binaries.yaml', 'models.yaml')

    HOST = cfg.get_host()
    PORT = cfg.get_port()

    sm = SessionManager()
    app.add_event_handler('startup', sm.init_models)
    app.add_event_handler('startup', llama.get_llama_pipeline().warmup)

    uvicorn.run(app, host=HOST, port=int(PORT))
