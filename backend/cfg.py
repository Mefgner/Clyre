import os
import re
import sys
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


def cached(_func: Callable):
    def wrapper(*args, **kwargs):
        global config_cache
        key = (_func.__name__, args, tuple(kwargs.keys()), tuple(kwargs.values()))
        if not config_cache.get(key):
            config_cache[key] = _func(*args, **kwargs)
        return config_cache[key]

    return wrapper


def load_dotenv():
    dotenv_path = get_base_dir() / '.env'
    if not dotenv_path.exists():
        dotenv_path = get_base_dir() / 'configs' / 'base.env'
    return dotenv.load_dotenv(dotenv_path)


def dict_from_yaml(file_path: Path, main_obj: str) -> dict:
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        if main_obj:
            if main_obj not in data:
                raise ValueError(f"Main object '{main_obj}' not found in YAML file '{file_path.name}'")
            return data[main_obj]
        return data


@cached
def get_base_dir() -> Path: return Path(__file__).parent.resolve()


@cached
def get_work_dir() -> Path:
    platform_info = dict_from_yaml(get_base_dir() / 'configs' / 'platform.yaml', 'platform')
    if not platform_info:
        raise ValueError('No platform information found in platform.yaml')

    for p in platform_info:
        if sys.platform == p['name']:
            workdir = Path(os.path.expanduser(os.path.expandvars(p['workdir']))).resolve()
            workdir.mkdir(parents=True, exist_ok=True)
            return workdir
    else:
        raise ValueError('Platform not found')


@cached
def from_env(var_name: str):
    value = os.getenv(var_name)
    if value is None:
        load_dotenv()
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Environment variable '{var_name}' is not set.")
    return value


create_functions({
    # General configuration
    'get_clyre_version': 'CLYRE_VERSION',
    'get_debug_state': 'DEBUG',
    # Server configuration
    'get_host': 'HOST',
    'get_port': 'PORT',
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
})

if TYPE_CHECKING:
    # General
    get_clyre_version: Callable[[], str]
    get_debug_state: Callable[[], str]
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


def get_resolved_db_path() -> Path:
    db_file_path_pattern = re.compile(r'^\.(/\w+)+(\.\w{2,})?$')
    db_path = get_db_path()
    if db_file_path_pattern.match(db_path):
        # Absolute path for the db .sqlite file
        db_path = get_work_dir().joinpath(db_path)

        db_path.touch(exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        return db_path
    raise ValueError("DB_PATH is not a valid relative path pattern or is not set.")


def get_default_llama_executable() -> Path:
    binaries = dict_from_yaml(get_base_dir() / 'configs' / 'binaries.yaml', 'binaries')

    for b in binaries:
        if b.get('type') == 'llama.cpp' and b.get('platform') == sys.platform:
            dest_subdir = b['dest_subdir']
            sha256 = b['sha256']
            sha_suffix = sha256.split(':', 1)[1]
            folder = b['folder']
            executable = b['exe_name']
            return get_work_dir() / dest_subdir / sha_suffix / folder / executable
    raise ValueError("No default llama executable")



@cached
def get_default_llama_model_path() -> Path:
    models = dict_from_yaml(get_base_dir() / 'configs' / 'models.yaml', 'models')
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

    return (get_work_dir() / dest_subdir / sha_suffix / filename).resolve()


@cached
def resolve_llama_model_path(model_name: str) -> str | None:
    models = dict_from_yaml(get_base_dir() / 'configs' / 'models.yaml', 'models')
    for m in models:
        if m.get('name') == model_name and m.get('framework') == 'llama':
            sha = m.get('sha256', '')
            sha_suffix = sha.split(':', 1)[1]
            dest_subdir = m['dest_subdir']
            filename = m['filename']
            return str((get_work_dir() / dest_subdir / sha_suffix / filename).resolve())
    raise ValueError(f"Model '{model_name}' not found or not compatible with llama.cpp")


def get_default_llama_model_name():
    models = dict_from_yaml(get_base_dir() / 'configs' / 'models.yaml', 'models')
    for m in models:
        if m.get('framework') == 'llama':
            return m.get('name')
    raise ValueError("No llama.cpp-compatible model found in models.yaml")


load_dotenv()


