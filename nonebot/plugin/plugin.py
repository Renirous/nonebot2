from types import ModuleType
from dataclasses import field, dataclass
from typing import Set, Dict, Type, Optional

from nonebot.matcher import Matcher

from .export import Export

plugins: Dict[str, "Plugin"] = {}
"""
:类型: ``Dict[str, Plugin]``
:说明: 已加载的插件
"""


@dataclass(eq=False)
class Plugin(object):
    """存储插件信息"""
    name: str
    """
    - **类型**: ``str``
    - **说明**: 插件名称，使用 文件/文件夹 名称作为插件名
    """
    module: ModuleType
    """
    - **类型**: ``ModuleType``
    - **说明**: 插件模块对象
    """
    module_name: str
    """
    - **类型**: ``str``
    - **说明**: 点分割模块路径
    """
    export: Export = field(default_factory=Export)
    """
    - **类型**: ``Export``
    - **说明**: 插件内定义的导出内容
    """
    matcher: Set[Type[Matcher]] = field(default_factory=set)
    """
    - **类型**: ``Set[Type[Matcher]]``
    - **说明**: 插件内定义的 ``Matcher``
    """
    # TODO
    parent_plugin: Optional["Plugin"] = None
    sub_plugins: Set["Plugin"] = field(default_factory=set)


def get_plugin(name: str) -> Optional[Plugin]:
    """
    :说明:

      获取当前导入的某个插件。

    :参数:

      * ``name: str``: 插件名，与 ``load_plugin`` 参数一致。如果为 ``load_plugins`` 导入的插件，则为文件(夹)名。

    :返回:

      - ``Optional[Plugin]``
    """
    return plugins.get(name)


def get_loaded_plugins() -> Set[Plugin]:
    """
    :说明:

      获取当前已导入的所有插件。

    :返回:

      - ``Set[Plugin]``
    """
    return set(plugins.values())


def _new_plugin(fullname: str, module: ModuleType) -> Plugin:
    _, name = fullname.rsplit(".", 1)
    if name in plugins:
        raise RuntimeError("Plugin already exists! Check your plugin name.")
    plugin = Plugin(name, module, fullname)
    plugins[name] = plugin
    return plugin
