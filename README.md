# Video Downloading Tool

一个支持视频、图片下载的 Python 工具。

目前重点支持：

* 通用视频下载
* 小红书图片提取与下载
* GUI 图片预览、多选下载
* 默认路径、循环运行、日志输出

---

# 功能

## 视频功能

* 支持通过分享文本提取真实 URL
* 支持通过 yt-dlp 获取视频标题、时长等信息
* 支持下载常规视频链接
* 支持自动尝试浏览器 cookies
* 支持手动指定 cookies 文件

注意：

* 抖音视频目前受平台限制较大
* 某些视频即使提供 cookies 仍可能无法稳定下载
* 如果遇到 `Fresh cookies are needed`，通常不是代码问题，而是平台风控或 cookies 失效

## 图片功能

* 支持提取网页中的图片资源
* 支持筛选高清图、过滤缩略图
* 支持小红书图文笔记解析
* 支持多图下载
* 支持选择部分图片下载
* 支持根据 URL 自动判断图片后缀

---

# 项目结构

```text
video_downloading/
│
├── main.py
├── GUI_V1.py
├── video_handler.py
├── iamge_handler.py
├── utils.py
├── README.md
└── xhs_debug/
```

## main.py

命令行版本入口。

负责：

* 接收用户输入
* 选择图片或视频模式
* 调用对应模块
* 控制下载流程

## GUI_V1.py

图形界面版本入口。

当前支持：

* 输入分享文本
* 选择图片 / 视频模式
* 选择保存路径
* 图片缩略图预览
* 多选图片下载
* 日志输出

## video_handler.py

负责视频处理。

主要功能：

* 提取真实 URL
* 调用 yt-dlp 获取视频信息
* 自动尝试 cookies
* 下载视频

## iamge_handler.py

负责图片处理。

主要功能：

* 获取网页 HTML
* 提取页面中的状态对象
* 找到图片列表
* 过滤缩略图
* 下载图片

## utils.py

公共工具函数。

例如：

* extract_url()
* format_duration()
* want_download()
* parse_selection_input()

---

# 安装

建议使用 Python 3.12。

## 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 安装依赖

```bash
python -m pip install -U pip
python -m pip install yt-dlp requests json5 pillow
```

如果你要运行 GUI，建议安装 Pillow：

```bash
python -m pip install pillow
```

---

# 运行

## 运行命令行版本

```bash
python main.py
```

## 运行 GUI 版本

```bash
python GUI_V1.py
```

---

# 图片提取运行逻辑

图片下载的大致流程如下：

```text
raw_text
↓
extract_url()
↓
get_image_info()
↓
prepare_image_downloads()
↓
download_image()
```

如果是小红书链接，还会额外走一条专用解析逻辑：

```text
get_xiaohongshu_precise_info()
↓
_fetch_page_html()
↓
_parse_state_data()
↓
_extract_xhs_precise_images_from_state()
↓
prepare_image_downloads()
```

---

# 关键函数说明

## extract_url(text)

从分享文本中提取第一个真实 URL。

例如：

```text
复制此链接，打开小红书查看内容：https://xxxxxx
```

最终只保留：

```text
https://xxxxxx
```

## _extract_js_object(html, marker)

从 HTML 中截取完整的 JavaScript 对象文本。

例如：

```js
window.__INITIAL_STATE__ = {...}
```

这个函数负责找到 `{ ... }` 整体内容。

## _parse_state_data(html)

把网页中的 JavaScript 对象转换成 Python 字典。

这里会先处理：

* undefined
* null
* 嵌套对象

最后通过 `json5.loads()` 转成 Python 数据。

## _find_note_nodes(data)

在小红书页面状态对象中，寻找真正的笔记节点。

因为页面数据很复杂，所以不能写死路径，只能递归搜索：

* noteInfo
* noteCard
* noteDetail
* noteData

这些可能出现的位置。

## prepare_image_downloads(info)

对所有候选图片进行过滤和排序。

主要目标是：

* 尽量过滤缩略图
* 优先保留高清原图
* 去掉重复图片

---

# 已知问题

## 抖音视频

抖音网页端限制较强，可能需要：

* 最新 cookies
* 浏览器访问记录
* 登录状态

即使这样，也不一定能稳定下载。

## 小红书图片

小红书经常修改页面结构。

如果后续解析失效，通常需要：

* 查看新的页面 HTML
* 找新的 imageList / noteInfo 字段
* 调整图片筛选逻辑

---

# 后续计划

* 保存默认路径到配置文件
* 自动记住 cookies 路径
* GUI 支持视频封面预览
* GUI 支持下载进度条
* GUI 支持下载完成后自动打开目录
* 支持更多平台
* 修复 iamge_handler.py 拼写问题

---

# 当前项目阶段

这个项目目前已经不是简单的“练习脚本”，而是一个具备：

* 多模块拆分
* GUI
* 图片筛选
* 平台专用解析
* cookies 处理
* 调试日志

的完整工具项目。
