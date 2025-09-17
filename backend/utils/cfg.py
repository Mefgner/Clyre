import datetime
import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable, TYPE_CHECKING

import dotenv
import yaml

config_cache = {}


def create_functions(mapping: dict[str, str]):
    if not isinstance(mapping, dict):
        raise TypeError("mapping must be a dictionary")
    mod_globals = sys.modules[__name__].__dict__

    for func_name, env_var in mapping.items():
        if not isinstance(func_name, str) or not isinstance(env_var, str):
            raise TypeError("Both keys and values in mapping must be strings")

        def _make_getter(name: str, var: str):
            def _getter():
                return from_env(var)

            _getter.__name__ = name
            _getter.__qualname__ = name
            _getter.__doc__ = f"Returns a {var} from a virtual environment."
            return _getter

        if func_name in mod_globals:
            raise ValueError(f"Имя уже занято в модуле: {func_name}")
        mod_globals[func_name] = _make_getter(func_name, env_var)


def load_dotenv():
    logging.info('Loading .env file')
    dotenv_path = get_app_root_dir() / '.env'
    if not dotenv_path.exists():
        dotenv_path = get_app_root_dir() / 'configs' / 'base.env'
    return dotenv.load_dotenv(dotenv_path)


def dict_from_yaml(absolute_file_path: Path) -> dict:
    with open(absolute_file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        if not data:
            raise ValueError(f'Configuration is not set in {absolute_file_path.name}')
        return data


@lru_cache(maxsize=1)
def get_app_root_dir() -> Path:
    res = Path(__file__).parent.parent.resolve()
    logging.debug(f'Getting application root directory {res}')
    return res


@lru_cache(maxsize=1)
def get_app_runtime_dir() -> Path:
    platform_info = dict_from_yaml(get_app_root_dir() / 'configs' / 'platform.yaml')
    if not platform_info:
        raise ValueError('No platform information found in platform.yaml')

    for p in platform_info:
        if sys.platform == p['name']:
            workdir = Path(os.path.expanduser(os.path.expandvars(p['workdir']))).resolve()
            logging.debug(f'platform path: {workdir}')
            workdir.mkdir(parents=True, exist_ok=True)
            return workdir
    else:
        raise ValueError('Platform not found')


@lru_cache(maxsize=96)
def from_env(var_name: str):
    value = os.getenv(var_name)
    if value is None:
        load_dotenv()
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Environment variable '{var_name}' is not set.")
    return value


functions_to_create = {
    # General configuration
    'get_clyre_version': 'CLYRE_VERSION',
    'get_debug_state': 'DEBUG',
    # Server configuration
    'get_host': 'HOST',
    'get_port': 'PORT',
    # Hashing configuration
    'get_hashing_secret': 'HASHING_SECRET',
    'get_access_token_secret': 'ACCESS_TOKEN_SECRET',
    'get_refresh_token_secret': 'REFRESH_TOKEN_SECRET',
    'get_service_secret': 'SERVICE_SECRET',
    # Backend configuration
    'get_db_engine': 'DB_ENGINE',
    'get_db_runtime': 'DB_RUNTIME',
    'get_db_path': 'DB_PATH',
    # Llama configuration
    'get_llama_win_host': 'LLAMA_WIN_HOST',
    'get_llama_win_port': 'LLAMA_WIN_PORT',
    'get_llama_url': 'LLAMA_URL',
    # Vector config
    # 'get_vector_db': 'VECTOR_DB',
    # 'get_vector_dim': 'VECTOR_DIM',
    # 'get_vector_path': 'VECTOR_PATH',
    # 'get_normalize_vectors': 'NORMALIZE_VECTORS',
    # 'get_distance_metric': 'DISTANCE',
}

create_functions(functions_to_create)

if TYPE_CHECKING:
    # General
    get_clyre_version: Callable[[], str]
    get_debug_state: Callable[[], str]
    # Hashing
    get_hashing_secret: Callable[[], str]
    get_access_token_secret: Callable[[], str]
    get_refresh_token_secret: Callable[[], str]
    get_service_secret: Callable[[], str]
    # get_access_token_dur_minutes: Callable[[], str]
    # get_refresh_token_dur_days: Callable[[], str]
    # Server
    get_host: Callable[[], str]
    get_port: Callable[[], str]
    # Backend
    get_db_engine: Callable[[], str]
    get_db_runtime: Callable[[], str]
    get_db_path: Callable[[], str]
    # Llama
    get_llama_win_host: Callable[[], str]
    get_llama_win_port: Callable[[], str]
    get_llama_url: Callable[[], str]
    # Vector
    # get_vector_db: Callable[[], str]
    # get_vector_dim: Callable[[], str]
    # get_vector_path: Callable[[], str]
    # get_normalize_vectors: Callable[[], str]
    # get_distance_metric: Callable[[], str]


@lru_cache(maxsize=1)
def get_resolved_db_path() -> Path:
    db_file_path_pattern = re.compile(r'^\.(/\w+)+(\.\w{2,})?$')
    db_path = get_db_path()
    if db_file_path_pattern.match(db_path):
        # Absolute path for the db .sqlite file
        db_path = get_app_runtime_dir().joinpath(db_path)

        db_path.touch(exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        return db_path
    raise ValueError("DB_PATH is not a valid relative path pattern or is not set.")


@lru_cache(maxsize=1)
def get_default_llama_executable() -> Path:
    binaries = dict_from_yaml(get_app_root_dir() / 'configs' / 'binaries.yaml')

    for b in binaries:
        if b.get('type') == 'llama.cpp' and b.get('platform') == sys.platform:
            dest_subdir = b['dest_subdir']
            sha256 = b['sha256']
            sha_suffix = sha256.split(':', 1)[1]
            folder = b['folder']
            executable = b['exe_name']
            return get_app_runtime_dir() / dest_subdir / sha_suffix / folder / executable
    raise ValueError("No default llama executable")


@lru_cache(maxsize=1)
def get_default_llama_model_path() -> Path:
    models = dict_from_yaml(get_app_root_dir() / 'configs' / 'models.yaml')
    target = None

    for m in models:
        if m.get('framework') == 'llama':
            target = m
            break

    if not target:
        raise ValueError("No llama.cpp-compatible model found in models.yaml")

    sha = target.get('sha256', '')
    sha_suffix = sha.split(':', 1)[1]
    dest_subdir = target['dest_subdir']
    filename = target['filename']

    return (get_app_runtime_dir() / dest_subdir / sha_suffix / filename).resolve()


@lru_cache(maxsize=16)
def resolve_llama_model_path(model_name: str) -> str | None:
    models = dict_from_yaml(get_app_root_dir() / 'configs' / 'models.yaml')
    for m in models:
        if m.get('name') == model_name and m.get('framework') == 'llama':
            sha = m.get('sha256', '')
            sha_suffix = sha.split(':', 1)[1]
            dest_subdir = m['dest_subdir']
            filename = m['filename']
            return str((get_app_runtime_dir() / dest_subdir / sha_suffix / filename).resolve())
    raise ValueError(f"Model '{model_name}' not found or not compatible with llama.cpp")


@lru_cache(maxsize=1)
def get_default_llama_model_name():
    models = dict_from_yaml(get_app_root_dir() / 'configs' / 'models.yaml')
    for m in models:
        if m.get('framework') == 'llama':
            return m.get('name')
    raise ValueError("No llama.cpp-compatible model found in models.yaml")


@lru_cache(maxsize=1)
def get_access_token_dur_minutes() -> datetime.timedelta:
    return datetime.timedelta(minutes=int(from_env('ACCESS_TOKEN_DUR_MINUTES')))


@lru_cache(maxsize=1)
def get_refresh_token_dur_days() -> datetime.timedelta:
    return datetime.timedelta(days=int(from_env('REFRESH_TOKEN_DUR_DAYS')))


__all__ = [*functions_to_create.keys(), 'get_app_root_dir', 'get_app_runtime_dir', 'from_env', 'get_resolved_db_path',
           'get_default_llama_executable', 'get_default_llama_model_path', 'resolve_llama_model_path',
           'get_default_llama_model_name', 'get_access_token_dur_minutes', 'get_refresh_token_dur_days']
