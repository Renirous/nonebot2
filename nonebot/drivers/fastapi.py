#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
from typing import Dict, Optional
from ipaddress import IPv4Address

import uvicorn
from fastapi.security import OAuth2PasswordBearer
from starlette.websockets import WebSocketDisconnect
from fastapi import Body, status, Header, FastAPI, WebSocket as FastAPIWebSocket

from nonebot.log import logger
from nonebot.config import Config
from nonebot.adapters import BaseBot
from nonebot.adapters.cqhttp import Bot as CQBot
from nonebot.drivers import BaseDriver, BaseWebSocket


class Driver(BaseDriver):

    def __init__(self, config: Config):
        self._server_app = FastAPI(
            debug=config.debug,
            openapi_url=None,
            docs_url=None,
            redoc_url=None,
        )

        self.config = config
        self._clients: Dict[int, BaseBot] = {}

        self._server_app.post("/{adapter}/")(self._handle_http)
        self._server_app.post("/{adapter}/http")(self._handle_http)
        self._server_app.websocket("/{adapter}/ws")(self._handle_ws_reverse)
        self._server_app.websocket("/{adapter}/ws/")(self._handle_ws_reverse)

    @property
    def server_app(self):
        return self._server_app

    @property
    def asgi(self):
        return self._server_app

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger("fastapi")

    @property
    def bots(self) -> Dict[int, BaseBot]:
        return self._clients

    def run(self,
            host: Optional[IPv4Address] = None,
            port: Optional[int] = None,
            *,
            app: Optional[str] = None,
            **kwargs):
        LOGGING_CONFIG = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "logging.Formatter",
                    "fmt": "[%(asctime)s %(name)s] %(levelname)s: %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": "INFO"
                },
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": "INFO",
                },
            },
        }
        uvicorn.run(app or self.server_app,
                    host=host or str(self.config.host),
                    port=port or self.config.port,
                    reload=app and self.config.debug,
                    debug=self.config.debug,
                    log_config=LOGGING_CONFIG,
                    **kwargs)

    async def _handle_http(self,
                           adapter: str,
                           data: dict = Body(...),
                           access_token: str = OAuth2PasswordBearer(
                               "/", auto_error=False)):
        # TODO: Check authorization
        logger.debug(f"Received message: {data}")
        if adapter == "cqhttp":
            bot = CQBot("http", self.config)
            await bot.handle_message(data)
        return {"status": 200, "message": "success"}

    async def _handle_ws_reverse(self,
                                 adapter: str,
                                 websocket: FastAPIWebSocket,
                                 self_id: int = Header(None),
                                 access_token: str = OAuth2PasswordBearer(
                                     "/", auto_error=False)):
        websocket = WebSocket(websocket)

        # TODO: Check authorization

        # Create Bot Object
        if adapter == "coolq":
            bot = CQBot("websocket", self.config, self_id, websocket=websocket)
        else:
            await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            return

        await websocket.accept()
        self._clients[self_id] = bot

        while not websocket.closed:
            data = await websocket.receive()

            if not data:
                continue

            await bot.handle_message(data)

        del self._clients[self_id]


class WebSocket(BaseWebSocket):

    def __init__(self, websocket: FastAPIWebSocket):
        super().__init__(websocket)
        self._closed = None

    @property
    def closed(self):
        return self._closed

    async def accept(self):
        await self.websocket.accept()
        self._closed = False

    async def close(self, code: int = status.WS_1000_NORMAL_CLOSURE):
        await self.websocket.close(code=code)
        self._closed = True

    async def receive(self) -> Optional[dict]:
        data = None
        try:
            data = await self.websocket.receive_json()
        except ValueError:
            logger.debug("Received an invalid json message.")
        except WebSocketDisconnect:
            self._closed = True
            logger.error("WebSocket disconnected by peer.")

        return data

    async def send(self, data: dict) -> None:
        await self.websocket.send_json(data)
