"""
CQHTTP (OneBot) v11 协议适配
============================

协议详情请看: `CQHTTP`_ | `OneBot`_

.. _CQHTTP:
    https://github.com/howmanybots/onebot/blob/master/README.md
.. _OneBot:
    https://github.com/howmanybots/onebot/blob/master/README.md
"""

from .utils import log
from .event import Event
from .message import Message, MessageSegment
from .bot import Bot, _check_at_me, _check_nickname, _check_reply
