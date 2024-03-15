"""
事件响应器
==========

该模块实现事件响应器的创建与运行，并提供一些快捷方法来帮助用户更好的与机器人进行对话 。
"""

from types import ModuleType
from datetime import datetime
from contextvars import ContextVar
from collections import defaultdict
from contextlib import AsyncExitStack
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Type,
    Union,
    TypeVar,
    Callable,
    NoReturn,
    Optional,
)

from nonebot import params
from nonebot.rule import Rule
from nonebot.log import logger
from nonebot.dependencies import Dependent
from nonebot.permission import USER, Permission
from nonebot.adapters import (
    Bot,
    Event,
    Message,
    MessageSegment,
    MessageTemplate,
)
from nonebot.consts import (
    ARG_KEY,
    ARG_STR_KEY,
    RECEIVE_KEY,
    REJECT_TARGET,
    LAST_RECEIVE_KEY,
)
from nonebot.exception import (
    PausedException,
    StopPropagation,
    SkippedException,
    FinishedException,
    RejectedException,
)
from nonebot.typing import (
    Any,
    T_State,
    T_Handler,
    T_ArgsParser,
    T_TypeUpdater,
    T_DependencyCache,
    T_PermissionUpdater,
)

if TYPE_CHECKING:
    from nonebot.plugin import Plugin

T = TypeVar("T")

matchers: Dict[int, List[Type["Matcher"]]] = defaultdict(list)
"""
:类型: ``Dict[int, List[Type[Matcher]]]``
:说明: 用于存储当前所有的事件响应器
"""
current_bot: ContextVar[Bot] = ContextVar("current_bot")
current_event: ContextVar[Event] = ContextVar("current_event")
current_state: ContextVar[T_State] = ContextVar("current_state")
current_handler: ContextVar[Dependent] = ContextVar("current_handler")


class MatcherMeta(type):
    if TYPE_CHECKING:
        module: Optional[str]
        plugin_name: Optional[str]
        module_name: Optional[str]
        module_prefix: Optional[str]
        type: str
        rule: Rule
        permission: Permission
        handlers: List[T_Handler]
        priority: int
        block: bool
        temp: bool
        expire_time: Optional[datetime]

    def __repr__(self) -> str:
        return (
            f"<Matcher from {self.module_name or 'unknown'}, "
            f"type={self.type}, priority={self.priority}, "
            f"temp={self.temp}>"
        )

    def __str__(self) -> str:
        return repr(self)


class Matcher(metaclass=MatcherMeta):
    """事件响应器类"""

    plugin: Optional["Plugin"] = None
    """
    :类型: ``Optional[Plugin]``
    :说明: 事件响应器所在插件
    """
    module: Optional[ModuleType] = None
    """
    :类型: ``Optional[ModuleType]``
    :说明: 事件响应器所在插件模块
    """
    plugin_name: Optional[str] = None
    """
    :类型: ``Optional[str]``
    :说明: 事件响应器所在插件名
    """
    module_name: Optional[str] = None
    """
    :类型: ``Optional[str]``
    :说明: 事件响应器所在点分割插件模块路径
    """

    type: str = ""
    """
    :类型: ``str``
    :说明: 事件响应器类型
    """
    rule: Rule = Rule()
    """
    :类型: ``Rule``
    :说明: 事件响应器匹配规则
    """
    permission: Permission = Permission()
    """
    :类型: ``Permission``
    :说明: 事件响应器触发权限
    """
    handlers: List[Dependent[Any]] = []
    """
    :类型: ``List[Handler]``
    :说明: 事件响应器拥有的事件处理函数列表
    """
    priority: int = 1
    """
    :类型: ``int``
    :说明: 事件响应器优先级
    """
    block: bool = False
    """
    :类型: ``bool``
    :说明: 事件响应器是否阻止事件传播
    """
    temp: bool = False
    """
    :类型: ``bool``
    :说明: 事件响应器是否为临时
    """
    expire_time: Optional[datetime] = None
    """
    :类型: ``Optional[datetime]``
    :说明: 事件响应器过期时间点
    """

    _default_state: T_State = {}
    """
    :类型: ``T_State``
    :说明: 事件响应器默认状态
    """

    _default_parser: Optional[Dependent[None]] = None
    """
    :类型: ``Optional[Dependent]``
    :说明: 事件响应器默认参数解析函数
    """
    _default_type_updater: Optional[Dependent[str]] = None
    """
    :类型: ``Optional[Dependent]``
    :说明: 事件响应器类型更新函数
    """
    _default_permission_updater: Optional[Dependent[Permission]] = None
    """
    :类型: ``Optional[Dependent]``
    :说明: 事件响应器权限更新函数
    """

    HANDLER_PARAM_TYPES = [
        params.DependParam,
        params.BotParam,
        params.EventParam,
        params.StateParam,
        params.MatcherParam,
        params.DefaultParam,
    ]

    def __init__(self):
        """实例化 Matcher 以便运行"""
        self.handlers = self.handlers.copy()
        self.state = self._default_state.copy()

    def __repr__(self) -> str:
        return (
            f"<Matcher from {self.module_name or 'unknown'}, type={self.type}, "
            f"priority={self.priority}, temp={self.temp}>"
        )

    def __str__(self) -> str:
        return repr(self)

    @classmethod
    def new(
        cls,
        type_: str = "",
        rule: Optional[Rule] = None,
        permission: Optional[Permission] = None,
        handlers: Optional[List[Union[T_Handler, Dependent[Any]]]] = None,
        temp: bool = False,
        priority: int = 1,
        block: bool = False,
        *,
        plugin: Optional["Plugin"] = None,
        module: Optional[ModuleType] = None,
        expire_time: Optional[datetime] = None,
        default_state: Optional[T_State] = None,
        default_parser: Optional[T_ArgsParser] = None,
        default_type_updater: Optional[T_TypeUpdater] = None,
        default_permission_updater: Optional[T_PermissionUpdater] = None,
    ) -> Type["Matcher"]:
        """
        :说明:

          创建一个新的事件响应器，并存储至 `matchers <#matchers>`_

        :参数:

          * ``type_: str``: 事件响应器类型，与 ``event.get_type()`` 一致时触发，空字符串表示任意
          * ``rule: Optional[Rule]``: 匹配规则
          * ``permission: Optional[Permission]``: 权限
          * ``handlers: Optional[List[T_Handler]]``: 事件处理函数列表
          * ``temp: bool``: 是否为临时事件响应器，即触发一次后删除
          * ``priority: int``: 响应优先级
          * ``block: bool``: 是否阻止事件向更低优先级的响应器传播
          * ``plugin: Optional[Plugin]``: 事件响应器所在插件
          * ``module: Optional[ModuleType]``: 事件响应器所在模块
          * ``default_state: Optional[T_State]``: 默认状态 ``state``
          * ``expire_time: Optional[datetime]``: 事件响应器最终有效时间点，过时即被删除

        :返回:

          - ``Type[Matcher]``: 新的事件响应器类
        """

        NewMatcher = type(
            "Matcher",
            (Matcher,),
            {
                "plugin": plugin,
                "module": module,
                "plugin_name": plugin and plugin.name,
                "module_name": module and module.__name__,
                "type": type_,
                "rule": rule or Rule(),
                "permission": permission or Permission(),
                "handlers": [
                    handler
                    if isinstance(handler, Dependent)
                    else Dependent[Any].parse(
                        call=handler, allow_types=cls.HANDLER_PARAM_TYPES
                    )
                    for handler in handlers
                ]
                if handlers
                else [],
                "temp": temp,
                "expire_time": expire_time,
                "priority": priority,
                "block": block,
                "_default_state": default_state or {},
                "_default_parser": default_parser,
                "_default_type_updater": default_type_updater,
                "_default_permission_updater": default_permission_updater,
            },
        )

        matchers[priority].append(NewMatcher)

        return NewMatcher

    @classmethod
    async def check_perm(
        cls,
        bot: Bot,
        event: Event,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[T_DependencyCache] = None,
    ) -> bool:
        """
        :说明:

          检查是否满足触发权限

        :参数:

          * ``bot: Bot``: Bot 对象
          * ``event: Event``: 上报事件

        :返回:

          - ``bool``: 是否满足权限
        """
        event_type = event.get_type()
        return event_type == (cls.type or event_type) and await cls.permission(
            bot, event, stack, dependency_cache
        )

    @classmethod
    async def check_rule(
        cls,
        bot: Bot,
        event: Event,
        state: T_State,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[T_DependencyCache] = None,
    ) -> bool:
        """
        :说明:

          检查是否满足匹配规则

        :参数:

          * ``bot: Bot``: Bot 对象
          * ``event: Event``: 上报事件
          * ``state: T_State``: 当前状态

        :返回:

          - ``bool``: 是否满足匹配规则
        """
        event_type = event.get_type()
        return event_type == (cls.type or event_type) and await cls.rule(
            bot, event, state, stack, dependency_cache
        )

    @classmethod
    def args_parser(cls, func: T_ArgsParser) -> T_ArgsParser:
        """
        :说明:

          装饰一个函数来更改当前事件响应器的默认参数解析函数

        :参数:

          * ``func: T_ArgsParser``: 参数解析函数
        """
        cls._default_parser = Dependent[None].parse(
            call=func, allow_types=cls.HANDLER_PARAM_TYPES
        )
        return func

    @classmethod
    def type_updater(cls, func: T_TypeUpdater) -> T_TypeUpdater:
        """
        :说明:

          装饰一个函数来更改当前事件响应器的默认响应事件类型更新函数

        :参数:

          * ``func: T_TypeUpdater``: 响应事件类型更新函数
        """
        cls._default_type_updater = Dependent[str].parse(
            call=func, allow_types=cls.HANDLER_PARAM_TYPES
        )
        return func

    @classmethod
    def permission_updater(cls, func: T_PermissionUpdater) -> T_PermissionUpdater:
        """
        :说明:

          装饰一个函数来更改当前事件响应器的默认会话权限更新函数

        :参数:

          * ``func: T_PermissionUpdater``: 会话权限更新函数
        """
        cls._default_permission_updater = Dependent[Permission].parse(
            call=func, allow_types=cls.HANDLER_PARAM_TYPES
        )
        return func

    @classmethod
    def append_handler(
        cls, handler: T_Handler, parameterless: Optional[List[Any]] = None
    ) -> Dependent[Any]:
        handler_ = Dependent[Any].parse(
            call=handler,
            parameterless=parameterless,
            allow_types=cls.HANDLER_PARAM_TYPES,
        )
        cls.handlers.append(handler_)
        return handler_

    @classmethod
    def handle(
        cls, parameterless: Optional[List[Any]] = None
    ) -> Callable[[T_Handler], T_Handler]:
        """
        :说明:

          装饰一个函数来向事件响应器直接添加一个处理函数

        :参数:

          * ``parameterless: Optional[List[Any]]``: 非参数类型依赖列表
        """

        def _decorator(func: T_Handler) -> T_Handler:
            cls.append_handler(func, parameterless=parameterless)
            return func

        return _decorator

    @classmethod
    def receive(
        cls, id: Optional[str] = None, parameterless: Optional[List[Any]] = None
    ) -> Callable[[T_Handler], T_Handler]:
        """
        :说明:

          装饰一个函数来指示 NoneBot 在接收用户新的一条消息后继续运行该函数

        :参数:

          * ``parameterless: Optional[List[Any]]``: 非参数类型依赖列表
        """

        async def _receive(event: Event, matcher: "Matcher") -> Union[None, NoReturn]:
            if matcher.get_receive(id):
                return
            if matcher.get_target() == RECEIVE_KEY.format(id=id):
                matcher.set_receive(id, event)
                return
            matcher.set_target(RECEIVE_KEY.format(id=id))
            raise RejectedException

        parameterless = [params.Depends(_receive), *(parameterless or [])]

        def _decorator(func: T_Handler) -> T_Handler:

            if cls.handlers and cls.handlers[-1].call is func:
                func_handler = cls.handlers[-1]
                for depend in reversed(parameterless):
                    func_handler.prepend_parameterless(depend)
            else:
                cls.append_handler(
                    func,
                    parameterless=parameterless if cls.handlers else parameterless,
                )

            return func

        return _decorator

    @classmethod
    def got(
        cls,
        key: str,
        prompt: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
        args_parser: Optional[T_ArgsParser] = None,
        parameterless: Optional[List[Any]] = None,
    ) -> Callable[[T_Handler], T_Handler]:
        """
        :说明:

          装饰一个函数来指示 NoneBot 当要获取的 ``key`` 不存在时接收用户新的一条消息并经过 ``ArgsParser`` 处理后再运行该函数，如果 ``key`` 已存在则直接继续运行

        :参数:

          * ``key: str``: 参数名
          * ``prompt: Optional[Union[str, Message, MessageSegment, MessageFormatter]]``: 在参数不存在时向用户发送的消息
          * ``args_parser: Optional[T_ArgsParser]``: 可选参数解析函数，空则使用默认解析函数
          * ``parameterless: Optional[List[Any]]``: 非参数类型依赖列表
        """

        async def _key_getter(event: Event, matcher: "Matcher"):
            if matcher.get_arg(key):
                return
            if matcher.get_target() == ARG_KEY.format(key=key):
                matcher.set_arg(key, event)
                return
            matcher.set_target(ARG_KEY.format(key=key))
            raise RejectedException

        _parameterless = [
            params.Depends(_key_getter),
            *(parameterless or []),
        ]

        def _decorator(func: T_Handler) -> T_Handler:

            if cls.handlers and cls.handlers[-1].call is func:
                func_handler = cls.handlers[-1]
                for depend in reversed(_parameterless):
                    func_handler.prepend_parameterless(depend)
            else:
                cls.append_handler(func, parameterless=_parameterless)

            return func

        return _decorator

    @classmethod
    async def send(
        cls, message: Union[str, Message, MessageSegment, MessageTemplate], **kwargs
    ) -> Any:
        """
        :说明:

          发送一条消息给当前交互用户

        :参数:

          * ``message: Union[str, Message, MessageSegment]``: 消息内容
          * ``**kwargs``: 其他传递给 ``bot.send`` 的参数，请参考对应 adapter 的 bot 对象 api
        """
        bot = current_bot.get()
        event = current_event.get()
        state = current_state.get()
        if isinstance(message, MessageTemplate):
            _message = message.format(**state)
        else:
            _message = message
        return await bot.send(event=event, message=_message, **kwargs)

    @classmethod
    async def finish(
        cls,
        message: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
        **kwargs,
    ) -> NoReturn:
        """
        :说明:

          发送一条消息给当前交互用户并结束当前事件响应器

        :参数:

          * ``message: Union[str, Message, MessageSegment]``: 消息内容
          * ``**kwargs``: 其他传递给 ``bot.send`` 的参数，请参考对应 adapter 的 bot 对象 api
        """
        bot = current_bot.get()
        event = current_event.get()
        state = current_state.get()
        if isinstance(message, MessageTemplate):
            _message = message.format(**state)
        else:
            _message = message
        if _message is not None:
            await bot.send(event=event, message=_message, **kwargs)
        raise FinishedException

    @classmethod
    async def pause(
        cls,
        prompt: Optional[Union[str, Message, MessageSegment, MessageTemplate]] = None,
        **kwargs,
    ) -> NoReturn:
        """
        :说明:

          发送一条消息给当前交互用户并暂停事件响应器，在接收用户新的一条消息后继续下一个处理函数

        :参数:

          * ``prompt: Union[str, Message, MessageSegment]``: 消息内容
          * ``**kwargs``: 其他传递给 ``bot.send`` 的参数，请参考对应 adapter 的 bot 对象 api
        """
        bot = current_bot.get()
        event = current_event.get()
        state = current_state.get()
        if isinstance(prompt, MessageTemplate):
            _prompt = prompt.format(**state)
        else:
            _prompt = prompt
        if _prompt is not None:
            await bot.send(event=event, message=_prompt, **kwargs)
        raise PausedException

    @classmethod
    async def reject(
        cls, prompt: Optional[Union[str, Message, MessageSegment]] = None, **kwargs
    ) -> NoReturn:
        """
        :说明:

          发送一条消息给当前交互用户并暂停事件响应器，在接收用户新的一条消息后重新运行当前处理函数

        :参数:

          * ``prompt: Union[str, Message, MessageSegment]``: 消息内容
          * ``**kwargs``: 其他传递给 ``bot.send`` 的参数，请参考对应 adapter 的 bot 对象 api
        """
        bot = current_bot.get()
        event = current_event.get()
        state = current_state.get()
        if isinstance(prompt, MessageTemplate):
            _prompt = prompt.format(**state)
        else:
            _prompt = prompt
        if _prompt is not None:
            await bot.send(event=event, message=_prompt, **kwargs)
        raise RejectedException

    def get_receive(self, id: Optional[str], default: T = None) -> Union[Event, T]:
        if id is None:
            return self.state.get(LAST_RECEIVE_KEY, default)
        return self.state.get(RECEIVE_KEY.format(id=id), default)

    def set_receive(self, id: Optional[str], event: Event) -> None:
        if id is not None:
            self.state[RECEIVE_KEY.format(id=id)] = event
        self.state[LAST_RECEIVE_KEY] = event

    def get_arg(self, key: str, default: T = None) -> Union[Event, T]:
        return self.state.get(ARG_KEY.format(key=key), default)

    def get_arg_str(self, key: str, default: T = None) -> Union[str, T]:
        return self.state.get(ARG_STR_KEY.format(key=key), default)

    def set_arg(self, key: str, event: Event) -> None:
        self.state[ARG_KEY.format(key=key)] = event
        self.state[ARG_STR_KEY.format(key=key)] = str(event.get_message())

    def set_target(self, target: str) -> None:
        self.state[REJECT_TARGET] = target

    def get_target(self, default: T = None) -> Union[str, T]:
        return self.state.get(REJECT_TARGET, default)

    def stop_propagation(self):
        """
        :说明:

          阻止事件传播
        """
        self.block = True

    async def update_type(self, bot: Bot, event: Event) -> str:
        updater = self.__class__._default_type_updater
        if not updater:
            return "message"
        return await updater(bot=bot, event=event, state=self.state, matcher=self)

    async def update_permission(self, bot: Bot, event: Event) -> Permission:
        updater = self.__class__._default_permission_updater
        if not updater:
            return USER(event.get_session_id(), perm=self.permission)
        return await updater(bot=bot, event=event, state=self.state, matcher=self)

    async def simple_run(
        self,
        bot: Bot,
        event: Event,
        state: T_State,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[T_DependencyCache] = None,
    ):
        b_t = current_bot.set(bot)
        e_t = current_event.set(event)
        s_t = current_state.set(self.state)
        try:
            # Refresh preprocess state
            self.state.update(state)

            while self.handlers:
                handler = self.handlers.pop(0)
                current_handler.set(handler)
                logger.debug(f"Running handler {handler}")
                try:
                    await handler(
                        matcher=self,
                        bot=bot,
                        event=event,
                        state=self.state,
                        stack=stack,
                        dependency_cache=dependency_cache,
                    )
                except SkippedException as e:
                    logger.debug(
                        f"Handler {handler} param {e.param.name} value {e.value} "
                        f"mismatch type {e.param._type_display()}, skipped"
                    )
        except StopPropagation:
            self.block = True
        finally:
            logger.info(f"Matcher {self} running complete")
            current_bot.reset(b_t)
            current_event.reset(e_t)
            current_state.reset(s_t)

    # 运行handlers
    async def run(
        self,
        bot: Bot,
        event: Event,
        state: T_State,
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[T_DependencyCache] = None,
    ):
        try:
            await self.simple_run(bot, event, state, stack, dependency_cache)

        except RejectedException:
            handler = current_handler.get()
            self.handlers.insert(0, handler)

            type_ = await self.update_type(bot, event)
            permission = await self.update_permission(bot, event)

            Matcher.new(
                type_,
                Rule(),
                permission,
                self.handlers,
                temp=True,
                priority=0,
                block=True,
                plugin=self.plugin,
                module=self.module,
                expire_time=datetime.now() + bot.config.session_expire_timeout,
                default_state=self.state,
                default_parser=self.__class__._default_parser,
                default_type_updater=self.__class__._default_type_updater,
                default_permission_updater=self.__class__._default_permission_updater,
            )
        except PausedException:
            type_ = await self.update_type(bot, event)
            permission = await self.update_permission(bot, event)

            Matcher.new(
                type_,
                Rule(),
                permission,
                self.handlers,
                temp=True,
                priority=0,
                block=True,
                plugin=self.plugin,
                module=self.module,
                expire_time=datetime.now() + bot.config.session_expire_timeout,
                default_state=self.state,
                default_parser=self.__class__._default_parser,
                default_type_updater=self.__class__._default_type_updater,
                default_permission_updater=self.__class__._default_permission_updater,
            )
        except FinishedException:
            pass
