import json
from os import environ as os_environ
from re import findall as re_findall
from socket import AF_INET, AF_INET6, inet_pton

from asyncio_relay_server.exceptions import LoadFileError


def str_to_bool(val: str) -> bool:
    """Takes string and tries to turn it into bool as human would do.

    If val is in case insensitive ("y", "yes", "yep", "yup", "t","true", "on",
     "enable", "enabled", "1") returns True.

    If val is in case insensitive ("n", "no", "f", "false", "off", "disable",
    "disabled", "0") returns False.

    Else Raise ValueError.
    """

    val = val.lower()
    if val in {
        "y",
        "yes",
        "yep",
        "yup",
        "t",
        "true",
        "on",
        "enable",
        "enabled",
        "1",
    }:
        return True
    # fmt: off
    elif val in {
        "n",
        "no",
        "f",
        "false",
        "off",
        "disable",
        "disabled",
        "0"
    }:
        return False
    # fmt: on
    else:
        raise ValueError(f"Invalid truth value {val}")


def load_dict_from_json_file_location(location: str) -> dict:
    """Load a dict from a json file location.

    :param location: The location of the file
    :return: A dict
    :raise LoadFileError: If environment variables in the location are not set
    :raise FileNotFoundError: If the file corresponding to the location does not exist
    """

    if "$" in location:
        # A) Check if location contains any environment variables
        #    in format ${some_env_var}.
        env_vars_in_location = set(re_findall(r"\${(.+?)}", location))

        # B) Check these variables exists in environment.
        not_defined_env_vars = env_vars_in_location.difference(os_environ.keys())
        if not_defined_env_vars:
            raise LoadFileError(
                "The following environment variables are not set: "
                f"{', '.join(not_defined_env_vars)}"
            )

        # C) Substitute them in location.
        for env_var in env_vars_in_location:
            location = location.replace("${" + env_var + "}", os_environ[env_var])

    with open(location) as f:
        return json.loads(f.read())
