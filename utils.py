"""
工具函数模块 - 适配 maibot 插件系统
"""

import base64
from asyncio import sleep
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from httpx import TimeoutException

# 移除 NoneBot 依赖，改为从插件系统获取配置
# from .config import config


def check_cd(user_id: str, user_data: dict[str, datetime], cd: int) -> tuple[bool, int, dict]:
    """检查用户触发事件的cd

    Args:
        user_id (str): 用户的id
        user_data (dict): 用户数据
        cd (int): 冷却时间(秒)

    Returns:
        Tuple[bool, int, dict]: 返回一个元组，第一个元素为True表示可以触发，为False表示不可以触发，第二个元素为剩余时间，第三个元素为用户数据
    """
    data = user_data
    user_id_str = str(user_id)
    
    if user_id_str not in data:
        data[user_id_str] = datetime.now()
    
    if datetime.now() < data[user_id_str]:
        delta = (data[user_id_str] - datetime.now()).seconds
        return False, delta, data
    
    data[user_id_str] = datetime.now() + timedelta(seconds=cd)
    return True, 0, data


async def download_from_urls(urls: list[str], path: Path):
    """
    下载图片
    :param urls: 图片链接
    :param path: 保存路径
    :return: None
    """
    from src.common.logger import get_logger
    logger = get_logger("GenshinCos.utils")
    
    is_download_error = False
    error_cnt = 0
    success_cnt = 0
    
    if not path.exists():
        path.mkdir(parents=True)
    
    if not path.is_dir():
        raise WriteError("路径不是文件夹")
    
    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                filename = url.split("/")[-1]
                # 确保文件名有效
                filename = "".join(c for c in filename if c.isalnum() or c in "._-")
                if not filename:
                    filename = f"image_{success_cnt}.jpg"
                
                new_path = path / filename
                rsp = await client.get(url, timeout=30.0)
                content = rsp.content
                
                with Path.open(new_path, "wb") as f:
                    f.write(content)
                    
            except (
                httpx.ConnectError,
                httpx.RequestError,
                httpx.ReadTimeout,
                TimeoutException,
            ) as e:
                is_download_error = True
                error_cnt += 1
                logger.warning(f"下载图片失败: {url}, 错误: {e}")
                continue
            except Exception as e:
                is_download_error = True
                error_cnt += 1
                logger.error(f"保存图片失败: {url}, 错误: {e}")
                continue
            
            success_cnt += 1
            logger.success(f"下载成功: {filename}")
    
    if is_download_error:
        raise WriteError(f"有{error_cnt}张图片下载失败，成功{success_cnt}张")
    
    return success_cnt


class WriteError(Exception):
    """写入错误"""
    pass


async def url_to_base64(url: str) -> str:
    """将图片URL下载并转换为base64编码
    
    Args:
        url: 图片URL
        
    Returns:
        str: base64编码的图片数据
        
    Raises:
        Exception: 下载或转换失败时抛出异常
    """
    from src.common.logger import get_logger
    logger = get_logger("GenshinCos.utils")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            image_bytes = response.content
            base64_data = base64.b64encode(image_bytes).decode('utf-8')
            logger.debug(f"成功将图片URL转换为base64: {url[:50]}...")
            return base64_data
        except Exception as e:
            logger.error(f"图片URL转base64失败: {url[:50]}..., 错误: {e}")
            raise


# 以下函数在 maibot 版本中简化或移除，因为发送逻辑已在 Command/Action 中实现

# async def send_forward_msg(...) - 移至 Command/Action 类中
# async def send_regular_msg(...) - 移至 Command/Action 类中
# async def msglist2forward(...) - 移至 Command/Action 类中


def should_use_forward(send_mode: str, image_count: int, threshold: int) -> bool:
    """判断是否使用合并转发
    
    Args:
        send_mode: 发送模式 ("auto", "forward", "separate")
        image_count: 图片数量
        threshold: 合并转发阈值
    
    Returns:
        bool: True表示使用合并转发，False表示逐张发送
    """
    if send_mode == "forward":
        return True
    elif send_mode == "separate":
        return False
    else:  # auto 模式
        if image_count >= threshold:
            return True
        return False


def generate_offsets(pages: int) -> list:
    """生成offset列表，用于多页获取图片
    
    Args:
        pages: 页数，每页20张图片
        
    Returns:
        list: offset列表，如 [0, 20, 40]
    """
    # 限制页数范围
    pages = max(1, min(pages, 5))
    return [i * 20 for i in range(pages)]
