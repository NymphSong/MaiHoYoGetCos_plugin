import asyncio
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.common.logger import get_logger
from src.common.data_models.message_data_model import ReplyContentType
from src.plugin_system import BaseCommand

from .hoyospider import (
    ForumType,
    Hot,
    Rank,
    RankType,
    Search,
    dbycos_hot,
    dbycos_rank_daily,
    genshin_hot,
    genshin_rank_daily,
    honkai3rd_hot,
    starrail_hot,
    zzz_hot,
)
from .utils import check_cd, download_from_urls, should_use_forward, generate_offsets

logger = get_logger("GenshinCos.commands")


def check_command_permission(get_config_func, user_id: str) -> bool:
    """检查用户是否有权限使用命令
    
    Args:
        get_config_func: 获取配置的函数
        user_id: 用户QQ号
        
    Returns:
        bool: 是否有权限
    """
    permission_list = get_config_func("permission.permission_list", [])
    permission_type = get_config_func("permission.permission_type", "blacklist")
    logger.info(f'[CommandPermission] {permission_type}: {str(permission_list)}')
    
    if permission_type == 'whitelist':
        return user_id in permission_list
    elif permission_type == 'blacklist':
        return user_id not in permission_list
    else:
        logger.error('permission_type错误，可能为拼写错误')
        return False

# 游戏名称映射
GAME_NAME_MAP = {
    "原神": ["原神", "genshin", "ys", "op", "原"],
    "崩坏3": ["崩坏3", "崩坏三", "bh3", "蹦蹦蹦", "崩三"],
    "星穹铁道": ["星穹铁道", "崩铁", "星铁", "铁道", "sr", "starrail"],
    "绝区零": ["绝区零", "zzz", "绝区", "零"],
    "大别野": ["大别野", "dby", "米游社"],
}

# Forum类型映射
FORUM_MAP = {
    "原神": ForumType.GenshinCos,
    "崩坏3": ForumType.Honkai3rdPic,
    "星穹铁道": ForumType.StarRailCos,
    "绝区零": ForumType.ZZZ,
    "大别野": ForumType.DBYCOS,
}

# 热门爬虫实例映射
HOT_SPIDER_MAP = {
    "原神": genshin_hot,
    "崩坏3": honkai3rd_hot,
    "星穹铁道": starrail_hot,
    "绝区零": zzz_hot,
    "大别野": dbycos_hot,
}

# 日榜爬虫实例映射
RANK_SPIDER_MAP = {
    "原神": genshin_rank_daily,
    "大别野": dbycos_rank_daily,
}


class HotCosCommand(BaseCommand):
    """热门COS命令"""

    command_name = "hot_cos"
    command_description = "获取热门COS图片"
    # 支持: /热门cos 原神, /热门cos 原神 5, /热门cos 原神 4-6, /热门cos帖 原神 3
    command_pattern = r"^/热门cos(?P<post_mode>帖)?\s+(?P<game>[^\s]+)(?:\s+(?P<range>\d+(?:-\d+)?))?"
    command_help = """获取指定游戏的热门COS图片
普通模式: /热门cos 原神 [数量]
范围模式: /热门cos 原神 4-6 (获取第4到第6张)
帖子模式: /热门cos帖 原神 3 (获取第3个帖子的所有图片)"""
    command_examples = ["/热门cos 原神", "/热门cos 崩坏3 5", "/热门cos 原神 4-6", "/热门cos帖 原神 3"]
    intercept_message = True

    def _normalize_game_name(self, game_input: str) -> Optional[str]:
        """标准化游戏名称"""
        for game_name, aliases in GAME_NAME_MAP.items():
            if game_input.lower() in [a.lower() for a in aliases] or game_input == game_name:
                return game_name
        return None

    def _parse_range(self, range_str: str) -> tuple[int, int, bool]:
        """解析范围字符串，如 '4-6' -> (4, 6, True)，'5' -> (1, 5, False)
        
        Returns:
            tuple: (start, end, is_range_mode)
            is_range_mode: True表示是范围模式(如4-6)，False表示是数量模式(如5)
        """
        if not range_str:
            return 1, 0, False  # 使用默认值
        
        if '-' in range_str:
            parts = range_str.split('-')
            try:
                start = int(parts[0])
                end = int(parts[1])
                return start, end, True  # 范围模式
            except (ValueError, IndexError):
                return 1, 0, False
        else:
            try:
                num = int(range_str)
                return 1, num, False  # 单数字表示数量模式
            except ValueError:
                return 1, 0, False

    async def execute(self) -> tuple[bool, Optional[str], bool]:
        # 权限检查
        user_id = self.message.message_info.user_info.user_id
        if not check_command_permission(self.get_config, user_id):
            await self.send_text("你没有权限使用此命令")
            return False, f"用户 {user_id} 无权限", True
        
        # 判断是否帖子模式
        is_post_mode = self.matched_groups.get("post_mode") == "帖"
        game_input = self.matched_groups.get("game", "")
        range_str = self.matched_groups.get("range")
        
        game_name = self._normalize_game_name(game_input)
        if not game_name:
            await self.send_text(f"不支持的游戏类型：{game_input}\n支持的游戏：原神、崩坏3、星穹铁道、绝区零、大别野")
            return False, f"不支持的游戏类型：{game_input}", True
        
        # 获取配置
        default_num = self.get_config("get_image.default_num", 3)
        max_images = self.get_config("get_image.max", 5)
        cd = self.get_config("get_image.cd", 30)
        pool_pages = self.get_config("get_image.image_pool_pages", 3)
        
        # 解析范围
        start_idx, end_idx, is_range_mode = self._parse_range(range_str)
        
        # CD检查
        if not hasattr(HotCosCommand, '_user_data'):
            HotCosCommand._user_data = {}
        
        out_cd, delta, HotCosCommand._user_data = check_cd(user_id, HotCosCommand._user_data, cd)
        if not out_cd:
            await self.send_text(f"冷却中，还剩{delta}秒")
            return False, f"冷却中，还剩{delta}秒", True
        
        # 帖子模式
        if is_post_mode:
            post_index = end_idx if end_idx > 0 else 1
            await self.send_text(f"正在获取{game_name}的热门COS帖图片...")
            
            try:
                spider = HOT_SPIDER_MAP.get(game_name)
                if not spider:
                    await self.send_text(f"{game_name}暂不支持热门COS获取")
                    return False, f"{game_name}暂不支持", True
                
                # 获取帖子列表（只取第一页）
                from .hoyospider import HoyoBasicSpider
                params = spider.get_params(page_size=20, offset=0)
                response = await spider.async_get_raw(params)
                
                posts = HoyoBasicSpider.handle_response_with_posts(response)
                
                if not posts or post_index > len(posts):
                    await self.send_text(f"未找到第{post_index}个帖子，当前只有{len(posts)}个帖子")
                    return False, "帖子不存在", True
                
                target_post = posts[post_index - 1]  # 转换为0索引
                selected = target_post["images"]
                
                if not selected:
                    await self.send_text("该帖子没有图片")
                    return False, "帖子无图片", True
                
                post_info = f"【{target_post['subject']}】\n作者：{target_post['author']}\n"
                await self.send_text(f"获取到帖子{post_info}共{len(selected)}张图片")
                
            except Exception as e:
                logger.error(f"获取帖子失败: {e}")
                await self.send_text(f"获取帖子失败: {str(e)}")
                return False, str(e), True
        
        # 普通模式（范围选择）
        else:
            num = end_idx if end_idx > 0 else default_num
            num = min(num, max_images)
            
            await self.send_text(f"正在获取{game_name}的热门COS图片...")
            
            try:
                spider = HOT_SPIDER_MAP.get(game_name)
                if not spider:
                    await self.send_text(f"{game_name}暂不支持热门COS获取")
                    return False, f"{game_name}暂不支持", True
                
                # 使用多页获取
                offsets = generate_offsets(pool_pages)
                all_image_urls = []
                
                for offset in offsets:
                    urls = await spider.async_get_urls(page_size=20, offset=offset)
                    if urls:
                        all_image_urls.extend(urls)
                    target_count = end_idx * 2 if end_idx > 0 else num * 3
                    if len(all_image_urls) >= target_count:
                        break
                
                # 去重
                seen = set()
                unique_urls = []
                for url in all_image_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)
                
                image_urls = unique_urls
                
                if not image_urls:
                    await self.send_text("未找到COS图片")
                    return False, "未找到图片", True
                
                # 范围选择
                if is_range_mode:
                    # 用户指定了范围，如 4-6
                    start = max(0, start_idx - 1)  # 转换为0索引
                    end = min(len(image_urls), end_idx if end_idx > 0 else len(image_urls))
                    
                    if start >= len(image_urls):
                        await self.send_text(f"起始位置{start_idx}超出范围，当前只有{len(image_urls)}张图片")
                        return False, "范围超出", True
                    
                    selected = image_urls[start:end]
                    # await self.send_text(f"从{len(image_urls)}张图片中获取第{start_idx}-{end}张，共{len(selected)}张")
                else:
                    # 随机选择
                    if len(image_urls) > num:
                        selected = random.sample(image_urls, num)
                    else:
                        selected = image_urls
            except Exception as e:
                logger.error(f"获取COS图片失败: {e}")
                await self.send_text(f"获取图片失败: {str(e)}")
                return False, str(e), True
        
        # 发送图片（两种模式共用）
        try:
            send_mode = self.get_config("get_image.send_mode", "auto")
            threshold = self.get_config("get_image.forward_threshold", 2)
            use_forward = should_use_forward(send_mode, len(selected), threshold)
            
            if use_forward:
                # 合并转发（最快的方式，QQ只显示一个合并消息）
                await self._send_forward_images(selected, f"{game_name}热门COS")
            else:
                # 逐张发送（使用imageurl避免识图）
                delay = self.get_config("get_image.delay", 0.1)
                total = len(selected)
                for i, url in enumerate(selected, 1):
                    try:
                        await self.send_custom("imageurl", url)
                        if i < total:  # 最后一张不需要等待
                            await asyncio.sleep(delay)
                    except Exception as e:
                        logger.warning(f"发送图片失败: {url[:50]}..., 错误: {e}")
                        continue
            
            return True, f"成功发送{len(selected)}张{game_name}COS图片", True
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            await self.send_text(f"发送图片失败: {str(e)}")
            return False, str(e), True
    
    async def _send_forward_images(self, image_urls: list, title: str):
        """发送合并转发图片（仅发送图片，无文字）"""
        # 构建合并转发消息（仅图片）
        messages = []
        for url in image_urls:
            # 仅添加图片节点（使用imageurl避免识图）
            messages.append((
                "10000",
                "米游社COS",
                [("imageurl", url)]
            ))
        
        # 调用合并转发API
        if messages:
            await self.send_forward(messages)


class RankCosCommand(BaseCommand):
    """排行榜COS命令"""

    command_name = "rank_cos"
    command_description = "获取排行榜COS图片"
    # 支持: /日榜cos 原神, /日榜cos 原神 5, /日榜cos 原神 4-6, /日榜cos帖 原神 3
    command_pattern = r"^/(?P<rank_type>日榜|周榜|月榜)cos帖?\s+(?P<game>[^\s]+)(?:\s+(?P<range>\d+(?:-\d+)?))?"
    command_help = """获取指定游戏的排行榜COS图片
普通模式: /日榜cos 原神 [数量]
范围模式: /日榜cos 原神 4-6 (获取第4到第6名)
帖子模式: /日榜cos帖 原神 3 (获取第3名的所有图片)"""
    command_examples = ["/日榜cos 原神", "/周榜cos 原神 5", "/月榜cos 原神 4-6", "/日榜cos帖 原神 3"]
    intercept_message = True

    def _normalize_game_name(self, game_input: str) -> Optional[str]:
        """标准化游戏名称"""
        for game_name, aliases in GAME_NAME_MAP.items():
            if game_input.lower() in [a.lower() for a in aliases] or game_input == game_name:
                return game_name
        return None

    def _parse_range(self, range_str: str) -> tuple[int, int, bool]:
        """解析范围字符串"""
        if not range_str:
            return 1, 0, False
        
        if '-' in range_str:
            parts = range_str.split('-')
            try:
                return int(parts[0]), int(parts[1]), True
            except (ValueError, IndexError):
                return 1, 0, False
        else:
            try:
                return 1, int(range_str), False
            except ValueError:
                return 1, 0, False

    async def execute(self) -> tuple[bool, Optional[str], bool]:
        # 权限检查
        user_id = self.message.message_info.user_info.user_id
        if not check_command_permission(self.get_config, user_id):
            await self.send_text("你没有权限使用此命令")
            return False, f"用户 {user_id} 无权限", True
        
        rank_type_str = self.matched_groups.get("rank_type", "日榜")
        # 通过原始消息判断是否帖子模式（因为正则中用(?:帖)?不捕获）
        is_post_mode = "cos帖" in self.message.processed_plain_text
        game_input = self.matched_groups.get("game", "")
        range_str = self.matched_groups.get("range")
        
        game_name = self._normalize_game_name(game_input)
        if not game_name:
            await self.send_text(f"不支持的游戏类型：{game_input}")
            return False, f"不支持的游戏类型", True
        
        if game_name not in RANK_SPIDER_MAP:
            await self.send_text(f"{game_name}暂不支持排行榜功能")
            return False, f"不支持排行榜", True
        
        # 获取配置
        default_num = self.get_config("get_image.default_num", 3)
        max_images = self.get_config("get_image.max", 5)
        cd = self.get_config("get_image.cd", 30)
        
        start_idx, end_idx, is_range_mode = self._parse_range(range_str)
        
        # CD检查
        if not hasattr(RankCosCommand, '_user_data'):
            RankCosCommand._user_data = {}
        
        out_cd, delta, RankCosCommand._user_data = check_cd(user_id, RankCosCommand._user_data, cd)
        if not out_cd:
            await self.send_text(f"冷却中，还剩{delta}秒")
            return False, f"冷却中", True
        
        # 确定排行榜类型
        rank_type_map = {
            "日榜": RankType.Daily,
            "周榜": RankType.Weekly,
            "月榜": RankType.Monthly,
        }
        rank_type = rank_type_map.get(rank_type_str, RankType.Daily)
        
        # 帖子模式 - 获取指定排名的帖子
        if is_post_mode:
            post_rank = end_idx if end_idx > 0 else 1
            await self.send_text(f"正在获取{game_name}{rank_type_str}第{post_rank}名的图片...")
            
            try:
                # 获取足够多的帖子
                fetch_num = max(post_rank * 2, 20)
                spider = Rank(FORUM_MAP[game_name], rank_type)
                
                # 获取原始响应以获取帖子信息
                from .hoyospider import HoyoBasicSpider
                params = spider.get_params(page_size=fetch_num)
                response = await spider.async_get_raw(params)
                posts = HoyoBasicSpider.handle_response_with_posts(response)
                
                if not posts or post_rank > len(posts):
                    await self.send_text(f"未找到第{post_rank}名，当前只有{len(posts)}个排名")
                    return False, "排名不存在", True
                
                target_post = posts[post_rank - 1]
                selected = target_post["images"]
                
                if not selected:
                    await self.send_text("该排名没有图片")
                    return False, "排名无图片", True
                
                post_info = f"【{target_post['subject']}】\n作者：{target_post['author']}\n"
                await self.send_text(f"获取到第{post_rank}名{post_info}共{len(selected)}张图片")
                
            except Exception as e:
                logger.error(f"获取排行榜帖子失败: {e}")
                await self.send_text(f"获取失败: {str(e)}")
                return False, str(e), True
        
        # 普通模式
        else:
            num = end_idx if end_idx > 0 else default_num
            num = min(num, max_images)
            
            await self.send_text(f"正在获取{game_name}的{rank_type_str}COS图片...")
            
            try:
                spider = Rank(FORUM_MAP[game_name], rank_type)
                
                # 范围模式需要获取更多
                if is_range_mode:
                    fetch_num = min(end_idx, max_images * 2)
                else:
                    fetch_num = num
                
                image_urls = await spider.async_get_urls(page_size=fetch_num)
                
                if not image_urls:
                    await self.send_text("未找到COS图片")
                    return False, "未找到图片", True
                
                # 范围选择
                if is_range_mode:
                    start = max(0, start_idx - 1)
                    end = min(len(image_urls), end_idx if end_idx > 0 else len(image_urls))
                    
                    if start >= len(image_urls):
                        await self.send_text(f"起始位置{start_idx}超出范围，当前只有{len(image_urls)}个排名")
                        return False, "范围超出", True
                    
                    selected = image_urls[start:end]
                    # await self.send_text(f"从{len(image_urls)}个排名中获取第{start_idx}-{end}名，共{len(selected)}张")
                else:
                    # 取前N名
                    selected = image_urls[:num]
                    
            except Exception as e:
                logger.error(f"获取排行榜失败: {e}")
                await self.send_text(f"获取失败: {str(e)}")
                return False, str(e), True
        
        # 发送图片（两种模式共用）
        try:
            send_mode = self.get_config("get_image.send_mode", "auto")
            threshold = self.get_config("get_image.forward_threshold", 2)
            use_forward = should_use_forward(send_mode, len(selected), threshold)
            
            if use_forward:
                await self._send_forward_images(selected, f"{game_name}{rank_type_str}COS")
            else:
                delay = self.get_config("get_image.delay", 0.1)
                total = len(selected)
                for i, url in enumerate(selected, 1):
                    try:
                        await self.send_custom("imageurl", url)
                        if i < total:
                            await asyncio.sleep(delay)
                    except Exception as e:
                        logger.warning(f"发送图片失败: {url[:50]}..., 错误: {e}")
                        continue
            
            return True, f"成功发送{len(selected)}张图片", True
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            await self.send_text(f"发送图片失败: {str(e)}")
            return False, str(e), True
    
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


class SearchCosCommand(BaseCommand):
    """搜索COS命令"""

    command_name = "search_cos"
    command_description = "搜索指定角色的COS图片"
    # 支持: /搜索cos 原神 甘雨, /搜索cos 原神 甘雨 5, /搜索cos 原神 甘雨 4-6, /搜索cos帖 原神 甘雨 3
    command_pattern = r"^/搜索cos(?P<post_mode>帖)?\s+(?P<game>[^\s]+)\s+(?P<keyword>[^\s]+)(?:\s+(?P<range>\d+(?:-\d+)?))?"
    command_help = """搜索指定游戏的COS图片
普通模式: /搜索cos 原神 甘雨 [数量]
范围模式: /搜索cos 原神 甘雨 4-6
帖子模式: /搜索cos帖 原神 甘雨 3"""
    command_examples = ["/搜索cos 原神 甘雨", "/搜索cos 星穹铁道 银狼 5", "/搜索cos 原神 甘雨 4-6", "/搜索cos帖 原神 甘雨 3"]
    intercept_message = True

    def _normalize_game_name(self, game_input: str) -> Optional[str]:
        for game_name, aliases in GAME_NAME_MAP.items():
            if game_input.lower() in [a.lower() for a in aliases] or game_input == game_name:
                return game_name
        return None

    def _parse_range(self, range_str: str) -> tuple[int, int, bool]:
        """解析范围字符串，返回 (start, end, is_range_mode)"""
        if not range_str:
            return 1, 0, False
        if '-' in range_str:
            parts = range_str.split('-')
            try:
                return int(parts[0]), int(parts[1]), True
            except (ValueError, IndexError):
                return 1, 0, False
        else:
            try:
                return 1, int(range_str), False
            except ValueError:
                return 1, 0, False

    async def execute(self) -> tuple[bool, Optional[str], bool]:
        # 权限检查
        user_id = self.message.message_info.user_info.user_id
        if not check_command_permission(self.get_config, user_id):
            await self.send_text("你没有权限使用此命令")
            return False, f"用户 {user_id} 无权限", True
        
        is_post_mode = self.matched_groups.get("post_mode") == "帖"
        game_input = self.matched_groups.get("game", "")
        keyword = self.matched_groups.get("keyword", "").strip()
        range_str = self.matched_groups.get("range")
        
        game_name = self._normalize_game_name(game_input)
        if not game_name:
            await self.send_text(f"不支持的游戏类型：{game_input}")
            return False, f"不支持的游戏类型", True
        
        if not keyword:
            await self.send_text("请输入搜索关键词")
            return False, "缺少关键词", True
        
        # 获取配置
        default_num = self.get_config("get_image.default_num", 3)
        max_images = self.get_config("get_image.max", 5)
        cd = self.get_config("get_image.cd", 30)
        
        start_idx, end_idx, is_range_mode = self._parse_range(range_str)
        
        # CD检查
        if not hasattr(SearchCosCommand, '_user_data'):
            SearchCosCommand._user_data = {}
        
        out_cd, delta, SearchCosCommand._user_data = check_cd(user_id, SearchCosCommand._user_data, cd)
        if not out_cd:
            await self.send_text(f"冷却中，还剩{delta}秒")
            return False, f"冷却中", True
        
        # 帖子模式
        if is_post_mode:
            post_index = end_idx if end_idx > 0 else 1
            await self.send_text(f"正在搜索{keyword}的第{post_index}个帖子...")
            
            try:
                search = Search(FORUM_MAP[game_name], keyword)
                
                # 获取帖子列表
                from .hoyospider import HoyoBasicSpider
                params = search.get_params(page_size=20, offset=0)
                response = await search.async_get_raw(params)
                
                posts = HoyoBasicSpider.handle_response_with_posts(response)
                
                if not posts or post_index > len(posts):
                    await self.send_text(f"未找到第{post_index}个帖子，当前只有{len(posts)}个帖子")
                    return False, "帖子不存在", True
                
                target_post = posts[post_index - 1]
                selected = target_post["images"]
                
                if not selected:
                    await self.send_text("该帖子没有图片")
                    return False, "帖子无图片", True
                
                post_info = f"【{target_post['subject']}】\n作者：{target_post['author']}\n"
                await self.send_text(f"获取到帖子{post_info}共{len(selected)}张图片")
                
            except Exception as e:
                logger.error(f"获取帖子失败: {e}")
                await self.send_text(f"获取帖子失败: {str(e)}")
                return False, str(e), True
        
        # 普通模式（范围选择）
        else:
            num = end_idx if end_idx > 0 else default_num
            num = min(num, max_images)
            
            await self.send_text(f"正在搜索{game_name}的{keyword}COS图片...")
            
            try:
                search = Search(FORUM_MAP[game_name], keyword)
                
                # 使用随机offset分页获取
                import random
                pool_pages = self.get_config("get_image.image_pool_pages", 3)
                offsets = generate_offsets(pool_pages)
                all_image_urls = []
                
                for offset in offsets:
                    urls = await search.async_get_urls(page_size=20, offset=offset)
                    if urls:
                        all_image_urls.extend(urls)
                    target_count = end_idx * 2 if end_idx > 0 else num * 3
                    if len(all_image_urls) >= target_count:
                        break
                
                # 去重
                seen = set()
                unique_urls = []
                for url in all_image_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)
                
                image_urls = unique_urls
                
                if not image_urls:
                    await self.send_text(f"未找到{keyword}的相关COS图片")
                    return False, "未找到图片", True
                
                # 范围选择
                if is_range_mode:
                    start = max(0, start_idx - 1)
                    end = min(len(image_urls), end_idx if end_idx > 0 else len(image_urls))
                    
                    if start >= len(image_urls):
                        await self.send_text(f"起始位置{start_idx}超出范围，当前只有{len(image_urls)}张图片")
                        return False, "范围超出", True
                    
                    selected = image_urls[start:end]
                    # await self.send_text(f"从{len(image_urls)}张图片中获取第{start_idx}-{end}张，共{len(selected)}张")
                else:
                    # 随机选择
                    if len(image_urls) > num:
                        selected = random.sample(image_urls, num)
                    else:
                        selected = image_urls
            except Exception as e:
                logger.error(f"搜索COS失败: {e}")
                await self.send_text(f"搜索失败: {str(e)}")
                return False, str(e), True
        
        # 发送图片（两种模式共用）
        try:
            send_mode = self.get_config("get_image.send_mode", "auto")
            threshold = self.get_config("get_image.forward_threshold", 2)
            use_forward = should_use_forward(send_mode, len(selected), threshold)
            
            if use_forward:
                await self._send_forward_images(selected, f"{game_name}-{keyword}")
            else:
                delay = self.get_config("get_image.delay", 0.1)
                total = len(selected)
                for i, url in enumerate(selected, 1):
                    try:
                        await self.send_custom("imageurl", url)
                        if i < total:
                            await asyncio.sleep(delay)
                    except Exception as e:
                        logger.warning(f"发送图片失败: {url[:50]}..., 错误: {e}")
                        continue
            
            return True, f"成功发送{len(selected)}张图片", True
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            await self.send_text(f"发送图片失败: {str(e)}")
            return False, str(e), True
    
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


class HelpCommand(BaseCommand):
    """帮助命令 - 显示插件所有功能"""

    command_name = "MaiHoYo_help"
    command_description = "显示米游社COS插件帮助信息"
    command_pattern = r"^/MaiHoYo_help"
    command_help = "显示插件所有功能和使用方法"
    command_examples = ["/MaiHoYo_help"]
    intercept_message = True

    async def execute(self) -> tuple[bool, Optional[str], bool]:
        # 从配置获取数值
        default_num = self.get_config("get_image.default_num", 3)
        max_images = self.get_config("get_image.max", 5)
        cd = self.get_config("get_image.cd", 30)
        delay = self.get_config("get_image.delay", 0.1)
        pool_pages = self.get_config("get_image.image_pool_pages", 3)
        
        help_text = f"""🎮 米游社COS插件 - 使用指南

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 指令

1️⃣ 获取热门COS图片
   随机获取: /热门cos 原神 {default_num}
   范围获取: /热门cos 崩铁 4-6
   帖子获取: /热门cos帖 绝区零 3

2️⃣ 获取排行榜COS图片
   随机获取: /日榜cos 原神 {default_num}
   范围获取: /周榜cos 原神 4-6
   帖子获取: /月榜cos帖 原神 3

3️⃣ 搜索指定角色的COS
   随机获取: /搜索cos 原神 派蒙 {default_num}
   范围获取: /搜索cos 崩铁 三月七 4-6
   帖子获取: /搜索cos帖 绝区零 安比 3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎮 游戏

• 原神 - 别名: 原神, genshin, ys, op, 原
• 崩坏3 - 别名: 崩坏3, 崩坏三, bh3, 蹦蹦蹦, 崩三
• 星穹铁道 - 别名: 星穹铁道, 崩铁, 星铁, sr, starrail
• 绝区零 - 别名: 绝区零, zzz, 绝区, 零
• 大别野 - 别名: 大别野, dby, 米游社

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 语言

除命令外，也可以直接说:
• "想看原神cos"
• "发点崩铁cos图"
• "看看甘雨的cos"
• "米游社cos来{default_num}张"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ 配置

• 默认返回数量: {default_num}张（指令未指定数量时使用）
• 最大返回数量: {max_images}张
• 冷却时间: {cd}秒
• 发送间隔: {delay}秒（逐张发送时）
• 图片池页数: {pool_pages}页（每页20张，影响热门/搜索的随机性）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• 排行榜功能仅支持原神和大别野
"""
        await self.send_text(help_text)
        return True, "帮助信息已发送", True
