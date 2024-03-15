#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
from datetime import timedelta
from ipaddress import IPv4Address
from typing import Set, Dict, Union, Mapping, Optional

from pydantic import BaseSettings
from pydantic.env_settings import SettingsError, env_file_sentinel, read_env_file


class BaseConfig(BaseSettings):

    def _build_environ(
            self,
            _env_file: Union[Path, str,
                             None] = None) -> Dict[str, Optional[str]]:
        """
        Build environment variables suitable for passing to the Model.
        """
        d: Dict[str, Optional[str]] = {}

        if self.__config__.case_sensitive:
            env_vars: Mapping[str, Optional[str]] = os.environ
        else:
            env_vars = {k.lower(): v for k, v in os.environ.items()}

        env_file = _env_file if _env_file != env_file_sentinel else self.__config__.env_file
        env_file_vars = {}
        if env_file is not None:
            env_path = Path(env_file)
            if env_path.is_file():
                env_file_vars = read_env_file(
                    env_path, case_sensitive=self.__config__.case_sensitive)
                env_vars = {**env_file_vars, **env_vars}

        for field in self.__fields__.values():
            env_val: Optional[str] = None
            for env_name in field.field_info.extra['env_names']:
                env_val = env_vars.get(env_name)
                if env_name in env_file_vars:
                    del env_file_vars[env_name]
                if env_val is not None:
                    break

            if env_val is None:
                continue

            if field.is_complex():
                try:
                    env_val = self.__config__.json_loads(env_val)
                except ValueError as e:
                    raise SettingsError(
                        f'error parsing JSON for "{env_name}"'  # type: ignore
                    ) from e
            d[field.alias] = env_val

        if env_file_vars:
            for env_name, env_val in env_file_vars.items():
                try:
                    env_val = self.__config__.json_loads(env_val)
                except ValueError as e:
                    pass

                d[env_name] = env_val

        return d


class Env(BaseSettings):
    environment: str = "prod"

    class Config:
        env_file = ".env"


class Config(BaseConfig):
    """
    NoneBot Config Object

    configs:

    ### `driver`

    - 类型: `str`
    - 默认值: `"nonebot.drivers.fastapi"`
    - 说明:
      nonebot 运行使用后端框架封装 Driver 。继承自 nonebot.driver.BaseDriver 。
    """
    # nonebot configs
    driver: str = "nonebot.drivers.fastapi"
    host: IPv4Address = IPv4Address("127.0.0.1")
    port: int = 8080
    secret: Optional[str] = None
    debug: bool = False

    # bot connection configs
    api_root: Dict[int, str] = {}
    access_token: Optional[str] = None

    # bot runtime configs
    superusers: Set[int] = set()
    nickname: Union[str, Set[str]] = ""
    session_expire_timeout: timedelta = timedelta(minutes=2)

    # custom configs
    # custom configs can be assigned during nonebot.init
    # or from env file using json loads

    class Config:
        extra = "allow"
        env_file = ".env.prod"
