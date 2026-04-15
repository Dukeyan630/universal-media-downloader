# Video Downloading Tool

一个支持视频、图片下载的 Python 工具。

## 功能
- 支持抖音链接解析
- 支持小红书图片提取
- 支持自定义保存路径
- 支持 yt-dlp 下载视频

## 安装

```bash
pip install -r requirements.txt

## 模块说明

- main.py
  - 负责接收用户输入
  - 调用视频或图片模块

- video_handler.py
  - 获取视频信息
  - 调用 yt-dlp
  - 解析 json

- image_handler.py
  - 获取网页 HTML
  - 提取图片链接
  - 下载图片

视频获取模块运行机制：
get_image_info(raw_text)
    url = extract_url(raw_text)
    #判断是否为小红书url
    is_xiaohongshu_url(url)
    -> True get_xiaohongshu_precise_info(url)#小红书专用提取线路
                _fetch_page_html(url)#获取原始网页和json数据
                #如果原始网页获取成功就抓取网页内容
                    _parse_state_data(html)
                        (方法写的很好，还不是很了解这个算法逻辑)_extract_js_object(html,marker)#找json相关数据，搭建python字典
                        #如果找到就返回 images, title, note_nodes # 
                             _extract_xhs_precise_images_from_state(data)
                                _find_note_nodes(data)#从搭建的python字典里，找到关键字
                                    _find_all_values()#根据目标键找到对应值
                                    walk()#不是很懂这个方法
                                _find_all_lists
                                _extract_orignal_only_from_item
                                    _extract_dimensions
                                ...这后面就是具体的打分算法机制了，我不太清楚，我需要了解吗