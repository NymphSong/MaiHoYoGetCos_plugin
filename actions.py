import asyncio
import random
from typing import Tuple

from src.common.logger import get_logger
from src.common.data_models.message_data_model import ReplyContentType
from src.plugin_system import BaseAction, ActionActivationType
from src.plugin_system.apis import generator_api

from .hoyospider import (
    ForumType,
    Hot,
    Rank,
    RankType,
    Search,
    dbycos_hot,
    genshin_hot,
    honkai3rd_hot,
    starrail_hot,
    zzz_hot,
)
from .utils import check_cd, should_use_forward

logger = get_logger("GenshinCos.actions")

# 游戏名称映射
GAME_NAME_MAP = {
    "原神": ["原神", "genshin", "ys", "op", "原", "原神cos", "原神COS"],
    "崩坏3": ["崩坏3", "崩坏三", "bh3", "蹦蹦蹦", "崩三", "崩坏3cos", "崩坏三cos"],
    "星穹铁道": ["星穹铁道", "崩铁", "星铁", "铁道", "sr", "starrail", "星穹铁道cos", "崩铁cos"],
    "绝区零": ["绝区零", "zzz", "绝区", "零", "绝区零cos", "绝区零COS"],
    "大别野": ["大别野", "dby", "米游社", "大别野cos"],
}

FORUM_MAP = {
    "原神": ForumType.GenshinCos,
    "崩坏3": ForumType.Honkai3rdPic,
    "星穹铁道": ForumType.StarRailCos,
    "绝区零": ForumType.ZZZ,
    "大别野": ForumType.DBYCOS,
}

HOT_SPIDER_MAP = {
    "原神": genshin_hot,
    "崩坏3": honkai3rd_hot,
    "星穹铁道": starrail_hot,
    "绝区零": zzz_hot,
    "大别野": dbycos_hot,
}


async def reply_send(action: BaseAction, chat_stream, extra_info: str) -> bool:
    """生成回复并发送"""
    success, response = await generator_api.generate_reply(
        chat_stream=chat_stream,
        chat_id=chat_stream.stream_id,
        extra_info=extra_info
    )
    for reply in response.reply_set.reply_data:
        reply_content = reply.content
        await action.send_text(content=reply_content, typing=True)
    return True


class SendCosAction(BaseAction):
    """发送COS图片动作 - 响应自然语言请求"""

    action_name = "send_cos"
    action_description = "根据用户请求发送米游社COS图片，支持原神、崩坏3、星穹铁道、绝区零等游戏"

    activation_type = ActionActivationType.KEYWORD
    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD

    activation_keywords = [
        "cos", "COS", "Cos",
        "cos图", "COS图", "cos图片", "COS图片",
        "coser", "COSER", "Coser",
        "看cos", "看COS", "看 Cos",
        "发cos", "发COS", "发 Cos",
        "米游社cos", "米游社COS",
        "原神cos", "崩坏3cos", "崩铁cos", "星穹铁道cos", "绝区零cos",
        "原神COS", "崩坏3COS", "崩铁COS", "星穹铁道COS", "绝区零COS",
    ]
    keyword_case_sensitive = False
    action_parameters = {
        "game": "需要发送cos的游戏名称（原神/崩坏3/星穹铁道/绝区零/大别野）",
        "character": "需要发送cos的具体角色名称",
        "num": "需要的图片数量（若无则默认3）",
    }
    action_require = [
        "用户要求看COS图片时使用",
        "用户提到想看某个游戏的COS时使用",
        "用户提到想看某个角色的COS时使用",
        "用户提到想看米游社图片时使用",
        "聊天氛围适合分享COS图片时使用",
    ]
    associated_types = ["text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(SendCosAction, '_user_data'):
            SendCosAction._user_data = {}

    def check_permission(self, qq_account: str) -> bool:
        """检查qq号为qq_account的用户是否拥有权限"""
        permission_list = self.get_config("permission.permission_list", [])
        permission_type = self.get_config("permission.permission_type", "blacklist")
        logger.info(f'[{self.action_name}] {permission_type}: {str(permission_list)}')
        if permission_type == 'whitelist':
            return qq_account in permission_list
        elif permission_type == 'blacklist':
            return qq_account not in permission_list
        else:
            logger.error('permission_type错误，可能为拼写错误')
            return False

    def _detect_game(self, text: str) -> str:
        """从文本中检测游戏名称"""
        text_lower = text.lower()
        
        # 检测各个游戏的关键词
        game_keywords = {
            "原神": ["原神", "genshin", "ys", "op", "原"],
            "崩坏3": ["崩坏3", "崩坏三", "bh3", "蹦蹦蹦", "崩三"],
            "星穹铁道": ["星穹铁道", "崩铁", "星铁", "铁道", "sr", "starrail"],
            "绝区零": ["绝区零", "zzz", "绝区", "零区"],
            "大别野": ["大别野", "dby", "米游社"],
        }
        
        for game_name, keywords in game_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return game_name
        
        # 默认返回原神
        return "原神"

    def _detect_character(self, text: str) -> str:
        """从文本中检测角色名称"""
        # 常见角色关键词（可根据需要扩展）
        character_keywords = [
            "甘雨", "胡桃", "雷电将军", "神里绫华", "纳西妲", "芙宁娜",
            "银狼", "卡芙卡", "镜流", "黄泉", "流萤",
            "布洛妮娅", "琪亚娜", "雷电芽衣", "爱莉希雅",
            "艾莲", "朱鸢", "简", "柳",
        ]
        
        for char in character_keywords:
            if char in text:
                return char
        
        return ""

    def _detect_num(self, text: str) -> int:
        """从文本中检测图片数量"""
        import re
        # 匹配 "x3", "3张", "三张" 等
        patterns = [
            r'(\d+)\s*张',
            r'[xX](\d+)',
            r'(\d+)\s*个',
            r'[来|发|给].*?(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    num = int(match.group(1))
                    return min(max(num, 1), 10)  # 限制1-10
                except ValueError:
                    pass
        
        # 默认从配置读取，但这里无法访问配置，所以在 execute 中处理
        return 0  # 返回0表示未检测到，使用配置默认值

    async def execute(self) -> Tuple[bool, str]:
        # ===== 权限检查 =====
        user_id = self.user_id
        if not self.check_permission(user_id):
            logger.info(f"{user_id} 无 {self.action_name} 权限")
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"拒绝执行发送COS图片动作：用户 {user_id} 权限不足",
                action_done=False,
            )
            await reply_send(self, self.chat_stream, f"你想发COS图片，但用户 {user_id} 没有权限，请用符合人格的方式进行拒绝的回复")
            return False, "无权限"
        else:
            logger.info(f"{user_id} 拥有 {self.action_name} 权限")
        
        # ===== 从 self.action_data 获取参数（优先）=====
        # 游戏名称
        game_name = self.action_data.get("game", "")
        # 角色名称
        character = self.action_data.get("character", "")
        # 图片数量
        num_str = self.action_data.get("num", "")
        
        # 如果 action_data 中没有，则从消息文本检测（兜底）
        message_text = self.action_message.processed_plain_text if self.action_message else ""
        
        if not game_name:
            game_name = self._detect_game(message_text)
        if not character:
            character = self._detect_character(message_text)
        
        # 获取配置
        default_num = self.get_config("get_image.default_num", 3)
        max_images = self.get_config("get_image.max", 5)
        cd = self.get_config("get_image.cd", 30)
        delay = self.get_config("get_image.delay", 0.1)
        
        # 处理数量：优先使用 action_data，其次是文本检测，最后是默认值
        if num_str:
            try:
                num = int(num_str)
                num = min(max(num, 1), 10)  # 限制1-10
            except ValueError:
                num = self._detect_num(message_text)
        else:
            num = self._detect_num(message_text)
        
        # 如果未检测到数量，使用默认值
        if num <= 0:
            num = default_num
        num = min(num, max_images)
        
        # CD检查
        out_cd, delta, SendCosAction._user_data = check_cd(user_id, SendCosAction._user_data, cd)
        if not out_cd:
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"用户请求COS图片，但冷却中（还剩{delta}秒）",
                action_done=False,
            )
            await reply_send(self, self.chat_stream, f"你想给用户发COS图片，但是系统冷却中（还剩{delta}秒），请告诉用户稍后再试")
            return False, f"冷却中，还剩{delta}秒"
        
        try:
            # 如果有角色名，使用搜索；否则使用热门
            if character:
                logger.info(f"搜索{game_name}的{character}COS图片")
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"正在搜索{game_name}的{character}COS图片",
                    action_done=False,
                )
                
                search = Search(FORUM_MAP[game_name], character)
                image_urls = await search.async_get_urls(page_size=20)
                search_keyword = character
            else:
                logger.info(f"获取{game_name}的热门COS图片")
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"正在获取{game_name}的热门COS图片",
                    action_done=False,
                )
                
                spider = HOT_SPIDER_MAP.get(game_name)
                if not spider:
                    await reply_send(self, self.chat_stream, f"你想发COS图片，但是{game_name}暂不支持")
                    return False, f"{game_name}暂不支持"
                
                image_urls = await spider.async_get_urls(page_size=20)
                search_keyword = "热门"
            
            if not image_urls:
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"未找到{game_name}的{search_keyword}COS图片",
                    action_done=False,
                )
                await reply_send(self, self.chat_stream, f"你想发COS图片，但是没找到相关图片，请告诉用户未找到")
                return False, "未找到图片"
            
            # 随机选择
            selected = random.sample(image_urls, min(num, len(image_urls)))
            
            # 发送图片
            send_mode = self.get_config("get_image.send_mode", "auto")
            threshold = self.get_config("get_image.forward_threshold", 2)
            use_forward = should_use_forward(send_mode, len(selected), threshold)
            
            if use_forward:
                # 合并转发
                await self._send_forward_images(selected, f"{game_name}-{search_keyword}")
            else:
                # 逐张发送（使用imageurl避免识图）
                total = len(selected)
                for i, url in enumerate(selected, 1):
                    try:
                        await self.send_custom("imageurl", url)
                        if i < total:
                            await asyncio.sleep(delay)
                    except Exception as e:
                        logger.warning(f"发送图片失败: {url[:50]}..., 错误: {e}")
                        continue
            
            # 记录动作完成
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"成功发送了{len(selected)}张{game_name}的{search_keyword}COS图片",
                action_done=True,
            )
            
            # 生成回复
            extra_info = f"你刚刚给用户发了{len(selected)}张{game_name}的{search_keyword}COS图片"
            if character:
                extra_info += f"（角色：{character}）"
            extra_info += "，请生成一句话的回复"
            
            await reply_send(self, self.chat_stream, extra_info)
            return True, f"成功发送{len(selected)}张图片"
            
        except Exception as e:
            logger.error(f"发送COS图片失败: {e}")
            await self.store_action_info(
                action_build_into_prompt=True,
                action_prompt_display=f"发送COS图片失败：{str(e)}",
                action_done=False,
            )
            await reply_send(self, self.chat_stream, f"你想发COS图片但是出错了，请告诉用户发送失败")
            return False, str(e)
    
    async def _send_forward_images(self, image_urls: list, title: str):
        """发送合并转发图片（仅发送图片，无文字）"""
        messages = []
        for url in image_urls:
            # 仅添加图片节点（使用imageurl避免识图）
            messages.append((
                "10000",
                "米游社COS",
                [("imageurl", url)]
            ))
        
        if messages:
            await self.send_forward(messages)


