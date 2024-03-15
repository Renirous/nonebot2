from typing import Callable, Any, Awaitable, Union, List, TYPE_CHECKING

from nonebot.helpers import render_expression

if TYPE_CHECKING:
    from nonebot.command import CommandSession

ArgFilter_T = Callable[[Any], Union[Any, Awaitable[Any]]]


class ValidateError(ValueError):
    def __init__(self, message=None):
        self.message = message


async def run_arg_filters(session: 'CommandSession',
                          arg_filters: List[ArgFilter_T]) -> None:
    arg = session.current_arg
    for f in arg_filters:
        try:
            res = f(arg)
            if isinstance(res, Awaitable):
                res = await res
            arg = res
        except ValidateError as e:
            # validation failed
            failure_message = e.message
            if failure_message is None:
                failure_message = render_expression(
                    session.bot.config.DEFAULT_VALIDATION_FAILURE_EXPRESSION
                )
            session.pause(failure_message)

    # passed all filters
    session.state[session.current_key] = arg
