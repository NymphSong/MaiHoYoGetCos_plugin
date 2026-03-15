# MaiHoYoGetCos_plugin
基于Maibot项目的插件，支持发送米游社cos图片。
基于[nonebot-plugin-genshin-cos](https://github.com/Cvandia/nonebot_plugin_genshin_cos)改造。

## 功能特性

- 🎮 **多游戏支持**: 原神、崩坏3、星穹铁道、绝区零、大别野
- 🔥 **热门COS**: 获取社区热门COS图片
- 📊 **排行榜**: 日榜、周榜、月榜COS图片
- 🔍 **搜索功能**: 按角色名搜索特定COS
- 🤖 **自然语言触发**: 通过 Action 组件响应自然语言请求

## 手动安装

1. 将文件夹复制到 Maibot 的 `plugins` 目录下

2. 安装依赖:
```bash
pip install httpx
```

3. 重启 Maibot，插件将自动加载

## 配置说明

首次启动将自动生成默认配置，在 Maibot 的 Webui 界面修改配置内容：

```toml
# MaiHoYoGetCos_plugin - 自动生成的配置文件
# 支持发送米游社cos图片，也许以后会整合cookie相关功能

# 插件基础配置
[plugin]
enable = true # 是否启用插件

# 图片获取配置
[get_image]
default_num = 3 # 默认返回图片数量
max = 5 # 单次最大返回图片数量
image_pool_pages = 3 # 图片池页数（每页20张）随机获取时从当次获取的图片池中挑选
cd = 10 # 单个用户触发冷却时间(秒)
delay = 0.5 # 逐张发送时每张图片的发送间隔(秒)建议>=0.1，否则可能触发风控
send_mode = "auto" # 发送模式: auto(自动) / forward(合并转发) / separate(逐张发送)
forward_threshold = 3 # 自动模式下，图片数量≥此值时使用合并转发

# 权限配置
[permission]
permission_type = "blacklist" # 权限类型: whitelist(白名单，仅列表内允许) / blacklist(黑名单，列表内不允许)
permission_list = [] # QQ号权限列表（根据 permission_type 决定是白名单还是黑名单）

```

## 使用方式

### 命令方式

| 命令 | 说明 | 示例 |
|------|------|------|
| `/热门cos <游戏> <数量>` | 获取热门COS随机x张图片 | `/热门cos 原神 x` |
| `/热门cos <游戏> <范围>` | 获取热门cos第x-第y张图片 | `/热门cos 原神 x-y` |
| `/热门cos帖 <游戏> <序号>` | 获取热门cos第x个帖子所有图片 | `/热门cos帖 原神 x` |
| `/日榜cos <游戏> <数量>` | 获取日榜COS前x张图片 | `/日榜cos 原神 x` |
| `/周榜cos <游戏> <范围>` | 获取日榜cos第x-第y张图片 | `/日榜cos 原神 x-y` |
| `/月榜cos帖 <游戏> <序号>` | 获取日榜cos第x名所有图片 | `/日榜cos帖 原神 x` |
| `/搜索cos <游戏> <角色> <数量>` | 搜索角色COS随机x张图片 | `/搜索cos 原神 甘雨 x` |
| `/搜索cos <游戏> <角色> <范围>` | 搜索角色COS第x-第y张图片 | `/搜索cos 原神 甘雨 x-y` |
| `/搜索cos帖 <游戏> <角色> <序号>` | 搜索角色COS第x个帖子所有图片 | `/搜索cos帖 原神 甘雨 x` |

### 自然语言方式

直接发送以下类似的消息，AI 会自动识别并发送COS图片:
（可在文件actions.py自行查询或修改对应关键词）

- "想看原神cos"
- "发点崩铁cos图"
- "看看甘雨的cos"
- "米游社cos来几张"
- "cos图 3张"

## 支持的别名

### 游戏别名
- **原神**: 原神、genshin、ys、op、原
- **崩坏3**: 崩坏3、崩坏三、bh3、蹦蹦蹦、崩三
- **星穹铁道**: 星穹铁道、崩铁、星铁、铁道、sr、starrail
- **绝区零**: 绝区零、zzz、绝区、零
- **大别野**: 大别野、dby、米游社

## 项目结构

```
MaiHoYoGetCos_plugin/
├── _manifest.json      # 插件清单文件
├── plugin.py           # 主插件类
├── commands.py         # 命令组件（/命令）
├── actions.py          # 动作组件（自然语言触发）
├── hoyospider.py       # 米游社爬虫核心
├── utils.py            # 工具函数
├── __init__.py         # 包初始化
└── README_MAIBOT.md    # 本说明文件
```

## 注意事项

1. **风控风险**: 频繁发送图片可能导致QQ账号被风控
2. **图片版权**: 图片版权归米游社原作者所有，请尊重COSER的创作权

## 许可证

MIT License
