from image_handler import download_image, get_image_info, prepare_image_downloads
from utils import format_duration, parse_selection_input, want_download
from video_handler import download_video, get_video_info

cookie_file = "/Users/yanshoulong/Downloads/douyin_cookies.txt"
default_path = "/Users/yanshoulong/Downloads"


def read_share_text():
    print("粘贴你的分享链接,确认后回车：")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def choose_images(image_candidates):
    if not image_candidates:
        return []

    print("找到以下图片（已尽量过滤缩略图）：")
    for index, item in enumerate(image_candidates, start=1):
        size_text = "未知尺寸"
        if item.get("width") and item.get("height"):
            size_text = f'{item["width"]}x{item["height"]}'
        print(f"{index}. [{size_text}] {item['url']}")

    text = input("输入要下载的序号，例如 1,3,5；直接回车表示全选：").strip()
    if not text:
        return [item["url"] for item in image_candidates]

    indices = parse_selection_input(text, len(image_candidates))
    return [image_candidates[index]["url"] for index in indices]


while True:
    choice = input("请选择你要获取的内容（1.图片，2.视频）：")
    raw_text = read_share_text()

    match choice:
        case "1":
            result = get_image_info(raw_text)
            if result:
                info, _ = result
                image_candidates = prepare_image_downloads(info)

                if not image_candidates:
                    print("未找到图片")
                else:
                    image_urls = choose_images(image_candidates)
                    if not image_urls:
                        print("没有有效选择，已取消下载。")
                    else:
                        answer = want_download()
                        if answer:
                            print("正在保存在默认路径（下载）")
                            download_image(image_urls, default_path)
                        else:
                            print("已取消下载")
            else:
                print("下载错误")

        case "2":
            result = get_video_info(raw_text, cookie_file=cookie_file)
            if result:
                info, url = result
                print("标题：", info.get("title"))
                print(f'时长：{format_duration(info.get("duration"))}')
                print("cookies 来源：", info.get("_cookie_source", "未知"))
                answer = want_download()
                if answer:
                    success = download_video(url, default_path, cookie_file=cookie_file)
                    if not success:
                        print("下载失败，请检查 cookies 是否可用。")
                else:
                    print("已取消下载")
            else:
                print("下载错误")

    flag = input("是否继续下载？（Y/N）").strip()
    if flag.upper() == "N":
        break
