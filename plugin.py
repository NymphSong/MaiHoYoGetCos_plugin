import asyncio
from typing import List, Tuple, Type

from src.plugin_system import BasePlugin, register_plugin, ComponentInfo
from src.plugin_system.base.config_types import ConfigField

from .commands import HotCosCommand, RankCosCommand, SearchCosCommand, HelpCommand
from .actions import SendCosAction


@register_plugin
class MaiHoYoPlugin(BasePlugin):
    """米游社COS插件 - 获取原神、崩坏3、星穹铁道、绝区零等游戏的COS图片"""
    plugin_name = "MaiHoYoGetCos_plugin"
    plugin_description = "获取米游社各游戏社区的COS图片"
    plugin_author = "NymphSong"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ['httpx']

    config_section_descriptions = {
        "plugin": "插件基础配置",
        "get_image": "图片获取配置",
        "permission": "权限配置",
    }

    config_schema = {
        "plugin": {
            "enable": ConfigField(
                type=bool, 
                default=True, 
                description="是否启用插件"
            ),
        },
        "get_image": {
            "default_num": ConfigField(
                type=int, 
                default=3, 
                description="默认返回图片数量"
            ),
            "max": ConfigField(
                type=int, 
                default=5, 
                description="单次最大返回图片数量"
            ),
            "image_pool_pages": ConfigField(
                type=int, 
                default=3, 
                description="图片池页数（每页20张）"
            ),
            "cd": ConfigField(
                type=int, 
                default=30, 
                description="用户触发冷却时间(秒)"
            ),
            "delay": ConfigField(
                type=float, 
                default=0.5, 
                description="逐张发送时每张图片的发送间隔(秒)"
            ),
            "send_mode": ConfigField(
                type=str, 
                default="auto", 
                description="发送模式: auto(自动) / forward(合并转发) / separate(逐张发送)"
            ),
            "forward_threshold": ConfigField(
                type=int, 
                default=2, 
                description="自动模式下，图片数量≥此值时使用合并转发"
            ),
        },
        "permission": {
            "permission_type": ConfigField(
                type=str, 
                default="blacklist", 
                description="权限类型: whitelist(白名单，仅列表内允许) / blacklist(黑名单，列表内不允许)"
            ),
            "permission_list": ConfigField(
                type=list, 
                default=[], 
                description="QQ号权限列表（根据 permission_type 决定是白名单还是黑名单）"
            ),
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.get_config("plugin.enable", True):
            self.enable_plugin = True
        else:
            self.enable_plugin = False

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (HotCosCommand.get_command_info(), HotCosCommand),
            (RankCosCommand.get_command_info(), RankCosCommand),
            (SearchCosCommand.get_command_info(), SearchCosCommand),
            (HelpCommand.get_command_info(), HelpCommand),
            (SendCosAction.get_action_info(), SendCosAction),
        ]
