from inspect import isclass
from os import environ
from typing import Any, Union

from asyncio_relay_server.utils import load_dict_from_json_file_location, str_to_bool

import dns.resolver

SOCKS_SERVER_PREFIX = "AIOSS_"

BASE_LOGO = """
0                 |─| |─| |                  0
01                | |─| |─|                 10
01011          A Socks Server            10100
010101010           0101             110010100  
01010      Implemented With Asyncio      11010
01                |─| |─| |                 01
0                 | |─| |─|                  0"""

DEFAULT_CONFIG = {
    "LISTEN_HOST": "0.0.0.0",
    "LISTEN_PORT": 1080,
    "ACCESS_LOG": False,
    "DEBUG": False,
    "RESOLVER": "",
    "RESOLVING_ORDER": 46,
    "REQUESTS_LOG_FILE": "/dev/null",
}

class Config(dict):
    LISTEN_HOST: str
    LISTEN_PORT: int
    AUTH_METHOD: int
    ACCESS_LOG: bool
    DEBUG: bool
    RESOLVER: str
    RESOLVING_ORDER: int
    REQUESTS_LOG_FILE: str

    def __init__(self):
        super().__init__({**DEFAULT_CONFIG})

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError as ke:
            raise AttributeError(f"Config has no '{ke.args[0]}'")

    def __setattr__(self, attr, value):
        self[attr] = value

    def load_environment_vars(self, prefix=SOCKS_SERVER_PREFIX):
        """
        Looks for prefixed environment variables and applies
        them to the configuration if present. This is called automatically when
        Socks-Server starts up to load environment variables into config.

        It will automatically hyrdate the following types:

        - ``int``
        - ``float``
        - ``bool``

        Anything else will be imported as a ``str``.

        (This function is referenced from Sanic.)
        """

        if not prefix:
            return

        for k, v in environ.items():
            if k.startswith(prefix):
                _, config_key = k.split(prefix, 1)
                try:
                    self[config_key] = int(v)
                except ValueError:
                    try:
                        self[config_key] = float(v)
                    except ValueError:
                        try:
                            self[config_key] = str_to_bool(v)
                        except ValueError:
                            self[config_key] = v

    def update_config(self, config: Union[str, dict, Any]):
        if not config:
            return

        if isinstance(config, str):
            config = load_dict_from_json_file_location(location=config)

        if not isinstance(config, dict):
            cfg = {}
            if not isclass(config):
                cfg.update(
                    {
                        key: getattr(config, key)
                        for key in config.__class__.__dict__.keys()
                    }
                )

            config = dict(config.__dict__)
            config.update(cfg)

        config = dict(filter(lambda i: i[0].isupper(), config.items()))

        resolver = dns.resolver.Resolver()
        if config.get('RESOLVER'):
            resolver.nameservers = [ config['RESOLVER'] ]
        
        config['resolver']=resolver

        self.update(config)
