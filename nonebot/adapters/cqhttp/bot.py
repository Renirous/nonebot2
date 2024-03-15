import re
import sys
import hmac
import json
import asyncio

import httpx

from nonebot.log import logger
from nonebot.config import Config
from nonebot.adapters import BaseBot
from nonebot.message import handle_event
from nonebot.typing import Any, Dict, Union, Optional
from nonebot.typing import overrides, Driver, WebSocket, NoReturn
from nonebot.exception import NetworkError, RequestDenied, ApiNotAvailable

from .event import Event
from .exception import ApiError
from .utils import log, get_auth_bearer
from .message import Message, MessageSegment


async def _check_reply(bot: "Bot", event: "Event"):
    """
    :说明:

      检查消息中存在的回复，去除并赋值 ``event.reply``, ``event.to_me``

    :参数:

      * ``bot: Bot``: Bot 对象
      * ``event: Event``: Event 对象
    """
    if event.type != "message":
        return

    try:
        index = list(map(lambda x: x.type == "reply",
                         event.message)).index(True)
    except ValueError:
        return
    msg_seg = event.message[index]
    event.reply = await bot.get_msg(message_id=msg_seg.data["id"])
    # ensure string comparation
    if str(event.reply["sender"]["user_id"]) == str(event.self_id):
        event.to_me = True
    del event.message[index]
    if len(event.message) > index and event.message[index].type == "at":
        del event.message[index]
    if len(event.message) > index and event.message[index].type == "text":
        event.message[index].data["text"] = event.message[index].data[
            "text"].lstrip()
        if not event.message[index].data["text"]:
            del event.message[index]
    if not event.message:
        event.message.append(MessageSegment.text(""))


def _check_at_me(bot: "Bot", event: "Event"):
    """
    :说明:

      检查消息开头或结尾是否存在 @机器人，去除并赋值 ``event.to_me``

    :参数:

      * ``bot: Bot``: Bot 对象
      * ``event: Event``: Event 对象
    """
    if event.type != "message":
        return

    if event.detail_type == "private":
        event.to_me = True
    else:
        at_me_seg = MessageSegment.at(event.self_id)

        # check the first segment
        if event.message[0] == at_me_seg:
            event.to_me = True
            del event.message[0]
            if event.message and event.message[0].type == "text":
                event.message[0].data["text"] = event.message[0].data[
                    "text"].lstrip()
                if not event.message[0].data["text"]:
                    del event.message[0]
            if event.message and event.message[0] == at_me_seg:
                del event.message[0]
                if event.message and event.message[0].type == "text":
                    event.message[0].data["text"] = event.message[0].data[
                        "text"].lstrip()
                    if not event.message[0].data["text"]:
                        del event.message[0]

        if not event.to_me:
            # check the last segment
            i = -1
            last_msg_seg = event.message[i]
            if last_msg_seg.type == "text" and \
                    not last_msg_seg.data["text"].strip() and \
                    len(event.message) >= 2:
                i -= 1
                last_msg_seg = event.message[i]

            if last_msg_seg == at_me_seg:
                event.to_me = True
                del event.message[i:]

        if not event.message:
            event.message.append(MessageSegment.text(""))


def _check_nickname(bot: "Bot", event: "Event"):
    """
    :说明:

      检查消息开头是否存在，去除并赋值 ``event.to_me``

    :参数:

      * ``bot: Bot``: Bot 对象
      * ``event: Event``: Event 对象
    """
    if event.type != "message":
        return

    first_msg_seg = event.message[0]
    if first_msg_seg.type != "text":
        return

    first_text = first_msg_seg.data["text"]

    nicknames = set(filter(lambda n: n, bot.config.nickname))
    if nicknames:
        # check if the user is calling me with my nickname
        nickname_regex = "|".join(nicknames)
        m = re.search(rf"^({nickname_regex})([\s,，]*|$)", first_text,
                      re.IGNORECASE)
        if m:
            nickname = m.group(1)
            log("DEBUG", f"User is calling me {nickname}")
            event.to_me = True
            first_msg_seg.data["text"] = first_text[m.end():]


def _handle_api_result(
        result: Optional[Dict[str, Any]]) -> Union[Any, NoReturn]:
    """
    :说明:

      处理 API 请求返回值。

    :参数:

      * ``result: Optional[Dict[str, Any]]``: API 返回数据

    :返回:

        - ``Any``: API 调用返回数据

    :异常:

        - ``ApiError``: API 调用失败
    """
    if isinstance(result, dict):
        if result.get("status") == "failed":
            raise ApiError(retcode=result.get("retcode"))
        return result.get("data")


class ResultStore:
    _seq = 1
    _futures: Dict[int, asyncio.Future] = {}

    @classmethod
    def get_seq(cls) -> int:
        s = cls._seq
        cls._seq = (cls._seq + 1) % sys.maxsize
        return s

    @classmethod
    def add_result(cls, result: Dict[str, Any]):
        if isinstance(result.get("echo"), dict) and \
                isinstance(result["echo"].get("seq"), int):
            future = cls._futures.get(result["echo"]["seq"])
            if future:
                future.set_result(result)

    @classmethod
    async def fetch(cls, seq: int, timeout: Optional[float]) -> Dict[str, Any]:
        future = asyncio.get_event_loop().create_future()
        cls._futures[seq] = future
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise NetworkError("WebSocket API call timeout") from None
        finally:
            del cls._futures[seq]


class Bot(BaseBot):
    """
    CQHTTP 协议 Bot 适配。继承属性参考 `BaseBot <./#class-basebot>`_ 。
    """

    def __init__(self,
                 driver: Driver,
                 connection_type: str,
                 config: Config,
                 self_id: str,
                 *,
                 websocket: Optional[WebSocket] = None):

        super().__init__(driver,
                         connection_type,
                         config,
                         self_id,
                         websocket=websocket)

    @property
    @overrides(BaseBot)
    def type(self) -> str:
        """
        - 返回: ``"cqhttp"``
        """
        return "cqhttp"

    @classmethod
    @overrides(BaseBot)
    async def check_permission(cls, driver: Driver, connection_type: str,
                               headers: dict,
                               body: Optional[dict]) -> Union[str, NoReturn]:
        """
        :说明:

          CQHTTP (OneBot) 协议鉴权。参考 `鉴权 <https://github.com/howmanybots/onebot/blob/master/v11/specs/communication/authorization.md>`_
        """
        x_self_id = headers.get("x-self-id")
        x_signature = headers.get("x-signature")
        access_token = get_auth_bearer(headers.get("authorization"))

        # 检查连接方式
        if connection_type not in ["http", "websocket"]:
            log("WARNING", "Unsupported connection type")
            raise RequestDenied(405, "Unsupported connection type")

        # 检查self_id
        if not x_self_id:
            log("WARNING", "Missing X-Self-ID Header")
            raise RequestDenied(400, "Missing X-Self-ID Header")

        # 检查签名
        secret = driver.config.secret
        if secret and connection_type == "http":
            if not x_signature:
                log("WARNING", "Missing Signature Header")
                raise RequestDenied(401, "Missing Signature")
            sig = hmac.new(secret.encode("utf-8"),
                           json.dumps(body).encode(), "sha1").hexdigest()
            if x_signature != "sha1=" + sig:
                log("WARNING", "Signature Header is invalid")
                raise RequestDenied(403, "Signature is invalid")

        access_token = driver.config.access_token
        if access_token and access_token != access_token:
            log(
                "WARNING", "Authorization Header is invalid"
                if access_token else "Missing Authorization Header")
            raise RequestDenied(
                403, "Authorization Header is invalid"
                if access_token else "Missing Authorization Header")
        return str(x_self_id)

    @overrides(BaseBot)
    async def handle_message(self, message: dict):
        """
        :说明:

          调用 `_check_reply <#async-check-reply-bot-event>`_, `_check_at_me <#check-at-me-bot-event>`_, `_check_nickname <#check-nickname-bot-event>`_ 处理事件并转换为 `Event <#class-event>`_
        """
        if not message:
            return

        if "post_type" not in message:
            ResultStore.add_result(message)
            return

        try:
            event = Event(message)

            # Check whether user is calling me
            await _check_reply(self, event)
            _check_at_me(self, event)
            _check_nickname(self, event)

            await handle_event(self, event)
        except Exception as e:
            logger.opt(colors=True, exception=e).error(
                f"<r><bg #f8bbd0>Failed to handle event. Raw: {message}</bg #f8bbd0></r>"
            )

    @overrides(BaseBot)
    async def call_api(self, api: str, **data) -> Union[Any, NoReturn]:
        """
        :说明:

          调用 CQHTTP 协议 API

        :参数:

          * ``api: str``: API 名称
          * ``**data: Any``: API 参数

        :返回:

          - ``Any``: API 调用返回数据

        :异常:

          - ``NetworkError``: 网络错误
          - ``ApiError``: API 调用失败
        """
        if "self_id" in data:
            self_id = data.pop("self_id")
            if self_id:
                bot = self.driver.bots[str(self_id)]
                return await bot.call_api(api, **data)

        log("DEBUG", f"Calling API <y>{api}</y>")
        if self.connection_type == "websocket":
            seq = ResultStore.get_seq()
            await self.websocket.send({
                "action": api,
                "params": data,
                "echo": {
                    "seq": seq
                }
            })
            return _handle_api_result(await ResultStore.fetch(
                seq, self.config.api_timeout))

        elif self.connection_type == "http":
            api_root = self.config.api_root.get(self.self_id)
            if not api_root:
                raise ApiNotAvailable
            elif not api_root.endswith("/"):
                api_root += "/"

            headers = {}
            if self.config.access_token is not None:
                headers["Authorization"] = "Bearer " + self.config.access_token

            try:
                async with httpx.AsyncClient(headers=headers) as client:
                    response = await client.post(
                        api_root + api,
                        json=data,
                        timeout=self.config.api_timeout)

                if 200 <= response.status_code < 300:
                    result = response.json()
                    return _handle_api_result(result)
                raise NetworkError(f"HTTP request received unexpected "
                                   f"status code: {response.status_code}")
            except httpx.InvalidURL:
                raise NetworkError("API root url invalid")
            except httpx.HTTPError:
                raise NetworkError("HTTP request failed")

    @overrides(BaseBot)
    async def send(self,
                   event: Event,
                   message: Union[str, Message, MessageSegment],
                   at_sender: bool = False,
                   **kwargs) -> Union[Any, NoReturn]:
        """
        :说明:

          根据 ``event``  向触发事件的主体发送消息。

        :参数:

          * ``event: Event``: Event 对象
          * ``message: Union[str, Message, MessageSegment]``: 要发送的消息
          * ``at_sender: bool``: 是否 @ 事件主体
          * ``**kwargs``: 覆盖默认参数

        :返回:

          - ``Any``: API 调用返回数据

        :异常:

          - ``ValueError``: 缺少 ``user_id``, ``group_id``
          - ``NetworkError``: 网络错误
          - ``ApiError``: API 调用失败
        """
        msg = message if isinstance(message, Message) else Message(message)

        at_sender = at_sender and bool(event.user_id)

        params = {}
        if event.user_id:
            params["user_id"] = event.user_id
        if event.group_id:
            params["group_id"] = event.group_id
        params.update(kwargs)

        if "message_type" not in params:
            if "group_id" in params:
                params["message_type"] = "group"
            elif "user_id" in params:
                params["message_type"] = "private"
            else:
                raise ValueError("Cannot guess message type to reply!")

        if at_sender and params["message_type"] != "private":
            params["message"] = MessageSegment.at(params["user_id"]) + \
                MessageSegment.text(" ") + msg
        else:
            params["message"] = msg
        return await self.send_msg(**params)
