import re


def extract_url(text):
    match = re.search(r"https?://[^\s]+", text)
    if match:
        return match.group()
    return None


def format_duration(seconds):
    if not seconds:
        return "未知"

    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}分{seconds}秒"


def want_download():
    text = input("你确定要下载吗?（Y/N）").strip()
    return text.upper() == "Y"


def parse_selection_input(text, max_count):
    selected = set()

    for part in text.split(","):
        item = part.strip()
        if not item:
            continue

        if "-" in item:
            start_text, end_text = item.split("-", maxsplit=1)
            if start_text.strip().isdigit() and end_text.strip().isdigit():
                start = int(start_text.strip())
                end = int(end_text.strip())
                for index in range(min(start, end), max(start, end) + 1):
                    if 1 <= index <= max_count:
                        selected.add(index - 1)
            continue

        if item.isdigit():
            index = int(item)
            if 1 <= index <= max_count:
                selected.add(index - 1)

    return sorted(selected)
