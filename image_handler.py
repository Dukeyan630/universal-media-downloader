import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from urllib.parse import parse_qs, urlsplit, urlunsplit

import json5
import requests

from utils import extract_url


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

XHS_HOST_HINTS = ("xhscdn.com", "xiaohongshu.com", "xhslink.com")
ORIGINAL_HINTS = ("original", "origin", "master", "raw", "large", "mw2000", "w_2160", "w_1440")
THUMBNAIL_HINTS = (
    "thumbnail",
    "thumb",
    "small",
    "avatar",
    "mini",
    "preview",
    "imageview2",
    "x-oss-process",
    "quality=low",
)
XHS_DEBUG_DIR = os.path.join(os.path.dirname(__file__), "xhs_debug")


def _clean_url(url):
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _extract_dimensions(item):
    width = item.get("width")
    height = item.get("height")

    if isinstance(width, str) and width.isdigit():
        width = int(width)
    if isinstance(height, str) and height.isdigit():
        height = int(height)

    return width, height

#识别平台，如果包含小红书相关字段，则为小红书链接
def _detect_platform(url):
    host = urlsplit(url).netloc.lower()
    if any(hint in host for hint in XHS_HOST_HINTS):
        return "xiaohongshu"
    return "generic"

#判断是否为小红书字段，返回布尔值
def _is_xiaohongshu_url(url):
    return _detect_platform(url) == "xiaohongshu"


def _build_candidate(url, width=None, height=None, source="unknown"):
    clean_url = _clean_url(url)
    if not clean_url:
        return None

    return {
        "url": clean_url,
        "width": width if isinstance(width, int) and width > 0 else None,
        "height": height if isinstance(height, int) and height > 0 else None,
        "source": source,
        "platform": _detect_platform(clean_url),
    }


def _collect_candidate(candidates, url, width=None, height=None, source="unknown"):
    candidate = _build_candidate(url, width, height, source)
    if candidate:
        candidates.append(candidate)


def _append_nested_urls(candidates, value, source):
    if isinstance(value, dict):
        width, height = _extract_dimensions(value)
        for sub_value in value.values():
            if isinstance(sub_value, str):
                _collect_candidate(candidates, sub_value, width, height, source)
            elif isinstance(sub_value, (list, dict)):
                _append_nested_urls(candidates, sub_value, source)
    elif isinstance(value, list):
        for sub_value in value:
            if isinstance(sub_value, str):
                _collect_candidate(candidates, sub_value, source=source)
            elif isinstance(sub_value, dict):
                width, height = _extract_dimensions(sub_value)
                for nested_value in sub_value.values():
                    if isinstance(nested_value, str):
                        _collect_candidate(candidates, nested_value, width, height, source)
                    elif isinstance(nested_value, (list, dict)):
                        _append_nested_urls(candidates, nested_value, source)


def extract_image_candidates(info):
    candidates = []

    if not isinstance(info, dict):
        return candidates

    thumbnails = info.get("thumbnails") or []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue

        width, height = _extract_dimensions(item)
        for key in ["url", "src", "original", "origin", "masterUrl", "previewUrl"]:
            _collect_candidate(candidates, item.get(key), width, height, key)

        for key in ["infoList", "urlDefaultInfo", "urlPre", "formats"]:
            _append_nested_urls(candidates, item.get(key), key)

    _collect_candidate(candidates, info.get("thumbnail"), source="thumbnail")
    return candidates


def _xhs_query_size_bonus(url):
    query = parse_qs(urlsplit(url).query)
    query_text = urlsplit(url).query.lower()
    score = 0

    for key in ["w", "width"]:
        for value in query.get(key, []):
            if value.isdigit():
                score += int(value) * 100

    for key in ["h", "height"]:
        for value in query.get(key, []):
            if value.isdigit():
                score += int(value) * 80

    match = re.search(r"/w/(\d+)", query_text)
    if match:
        score += int(match.group(1)) * 100

    match = re.search(r"/h/(\d+)", query_text)
    if match:
        score += int(match.group(1)) * 80

    return score


def _candidate_score(candidate):
    url = candidate["url"].lower()
    score = 0

    width = candidate.get("width")
    height = candidate.get("height")
    if width and height:
        score += width * height

    score += _xhs_query_size_bonus(url)

    if any(keyword in url for keyword in ORIGINAL_HINTS):
        score += 5_000_000

    if candidate.get("source") in {"original", "origin", "masterUrl"}:
        score += 4_000_000

    if any(keyword in url for keyword in THUMBNAIL_HINTS):
        score -= 4_500_000

    if candidate.get("source") in {"previewUrl", "thumbnail"}:
        score -= 4_000_000

    if width and height and (width < 500 or height < 500):
        score -= 2_500_000

    if candidate.get("platform") == "xiaohongshu" and "imageview2" not in url and "x-oss-process" not in url:
        score += 1_500_000

    return score


def _normalize_path(path):
    path = re.sub(r"([_-])\d{2,4}x\d{2,4}(?=\.)", "", path, flags=re.IGNORECASE)
    path = re.sub(r"([_-])(thumb|thumbnail|small|mini|preview)(?=\.)", "", path, flags=re.IGNORECASE)
    path = re.sub(r"/orj\d+/", "/", path, flags=re.IGNORECASE)
    path = re.sub(r"/prv\d+/", "/", path, flags=re.IGNORECASE)
    return path


def _extract_asset_id(url):
    parts = urlsplit(url)
    for pattern in [r"([0-9a-f]{24,64})", r"([A-Za-z0-9_-]{20,})"]:
        for text in [parts.path, parts.query]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).lower()
    return None


def _group_key(candidate):
    parts = urlsplit(candidate["url"])
    asset_id = _extract_asset_id(candidate["url"])
    path = _normalize_path(parts.path)
    if asset_id:
        return f"{parts.netloc}:{asset_id}"
    return f"{parts.netloc}:{path}"


def _is_thumbnail_like(candidate):
    url = candidate["url"].lower()
    width = candidate.get("width")
    height = candidate.get("height")

    if candidate.get("source") in {"previewUrl", "thumbnail"}:
        return True
    if any(keyword in url for keyword in THUMBNAIL_HINTS):
        return True
    if width and height and width < 500 and height < 500:
        return True
    return False


def filter_preferred_images(candidates):
    grouped = {}
    for candidate in candidates:
        grouped.setdefault(_group_key(candidate), []).append(candidate)

    filtered = []
    for group in grouped.values():
        group.sort(key=_candidate_score, reverse=True)
        filtered.append(group[0])

    filtered = [item for item in filtered if not (_is_thumbnail_like(item) and len(grouped[_group_key(item)]) > 1)]
    filtered.sort(key=lambda item: (_candidate_score(item), item["url"]), reverse=True)

    unique_urls = []
    seen = set()
    for item in filtered:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique_urls.append(item)

    return unique_urls


def prepare_image_downloads(info):
    candidates = extract_image_candidates(info)
    return filter_preferred_images(candidates)

#用来获取页面出镜html和json
def _fetch_page_html(url):
    response = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text, response.url


def _ensure_debug_dir():
    os.makedirs(XHS_DEBUG_DIR, exist_ok=True)
    return XHS_DEBUG_DIR


def _safe_debug_name(url):
    parts = urlsplit(url)
    raw = f"{parts.netloc}_{parts.path}".strip("/").replace("/", "_")
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    return raw[:80] or "xhs_note"


def _write_json_debug(name, payload):
    debug_dir = _ensure_debug_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(debug_dir, f"{timestamp}_{name}.json")
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return path


def _write_text_debug(name, text):
    debug_dir = _ensure_debug_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(debug_dir, f"{timestamp}_{name}.html")
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    return path


def _extract_js_object(html, marker):
    start = html.find(marker)
    if start == -1:
        return None

    start += len(marker)
    brace_start = html.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    end = -1

    for i in range(brace_start, len(html)):
        ch = html[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        return None

    return html[brace_start:end]

#在html里找网页原始数据
def _parse_state_data(html):
    markers = [
        "window.__INITIAL_STATE__=",
        "window.__INITIAL_SSR_STATE__=",
    ]
    #html里面抓取json字段
    for marker in markers:
        json_text = _extract_js_object(html, marker)
        if not json_text:
            continue
        #替换json里面的undefined字段，转换为python字典null，避免读取失败
        json_text = re.sub(r":\s*undefined", ": null", json_text)
        json_text = re.sub(r",\s*undefined", ", null", json_text)
        json_text = re.sub(r"\[\s*undefined", "[null", json_text)

        try:
            return json5.loads(json_text)
        except Exception:
            continue

    return None


def _pick_best_url_from_value(value, preferred_keys=None, width=None, height=None, source_prefix="xhs"):
    preferred_keys = preferred_keys or []
    candidates = []

    def walk(obj, current_key=""):
        if isinstance(obj, str):
            _collect_candidate(candidates, obj, width, height, f"{source_prefix}:{current_key or 'str'}")
            return

        if isinstance(obj, dict):
            local_width, local_height = _extract_dimensions(obj)
            use_width = local_width or width
            use_height = local_height or height

            for key in preferred_keys:
                if key in obj:
                    walk(obj.get(key), key)

            for key, nested in obj.items():
                if key in preferred_keys:
                    continue
                walk(nested, key)
            return

        if isinstance(obj, list):
            for nested in obj:
                walk(nested, current_key)

    walk(value)

    if not candidates:
        return None

    candidates = [item for item in candidates if not _is_thumbnail_like(item)] or candidates
    candidates.sort(key=_candidate_score, reverse=True)
    return candidates[0]


def _extract_xhs_image_from_item(item):
    if not isinstance(item, dict):
        return None

    width, height = _extract_dimensions(item)

    for key in ["masterUrl", "origin", "original"]:
        if key in item:
            candidate = _pick_best_url_from_value(item[key], preferred_keys=["url", "masterUrl", "original", "origin"], width=width, height=height, source_prefix=key)
            if candidate:
                return candidate

    container_priority = [
        ("urlDefaultInfo", ["url", "masterUrl", "original", "origin"]),
        ("infoList", ["url", "masterUrl", "original", "origin"]),
        ("stream", ["masterUrl", "original", "origin", "url"]),
    ]
    for key, preferred_keys in container_priority:
        if key in item:
            candidate = _pick_best_url_from_value(item[key], preferred_keys=preferred_keys, width=width, height=height, source_prefix=key)
            if candidate:
                return candidate

    return None


def _find_first_value(obj, target_keys):
    target_keys = {key.lower() for key in target_keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in target_keys:
                return value
            result = _find_first_value(value, target_keys)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_first_value(item, target_keys)
            if result is not None:
                return result

    return None


def _find_first_string(obj, target_keys):
    value = _find_first_value(obj, target_keys)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _find_all_lists(obj, target_keys, found=None):
    if found is None:
        found = []

    target_keys = {key.lower() for key in target_keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in target_keys and isinstance(value, list):
                found.append(value)
            _find_all_lists(value, target_keys, found)
    elif isinstance(obj, list):
        for item in obj:
            _find_all_lists(item, target_keys, found)

    return found


def _find_all_values(obj, target_keys, found=None):
    if found is None:
        found = []

    target_keys = {key.lower() for key in target_keys}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in target_keys:
                found.append(value)
            _find_all_values(value, target_keys, found)
    elif isinstance(obj, list):
        for item in obj:
            _find_all_values(item, target_keys, found)

    return found


def _find_note_nodes(data):
    direct_nodes = _find_all_values(
        data,
        {
            "noteDetail",
            "noteInfo",
            "noteinfo",
            "noteCard",
            "notecard",
            "note_data",
            "noteData",
        },
    )

    structured_nodes = []
    for node in direct_nodes:
        if isinstance(node, dict):
            structured_nodes.append(node)
            for key in ["noteDetailMap", "noteMap", "data"]:
                nested = node.get(key)
                if isinstance(nested, dict):
                    structured_nodes.append(nested)
                    for value in nested.values():
                        if isinstance(value, dict):
                            structured_nodes.append(value)

    if structured_nodes:
        return structured_nodes

    fallback_nodes = []

    def walk(obj):
        if isinstance(obj, dict):
            lowered_keys = {key.lower() for key in obj.keys()}
            if (
                {"imagelist", "title"} <= lowered_keys
                or {"imageslist", "title"} <= lowered_keys
                or {"imagelist", "desc"} <= lowered_keys
                or {"imageslist", "desc"} <= lowered_keys
            ):
                fallback_nodes.append(obj)

            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return fallback_nodes


def _summarize_item_keys(item):
    if not isinstance(item, dict):
        return {"type": type(item).__name__}

    summary = {"keys": sorted(item.keys())}
    for key in ["masterUrl", "origin", "original", "previewUrl", "url", "stream", "infoList", "urlDefaultInfo"]:
        if key not in item:
            continue
        value = item[key]
        if isinstance(value, dict):
            summary[key] = {"type": "dict", "keys": sorted(value.keys())}
        elif isinstance(value, list):
            summary[key] = {
                "type": "list",
                "length": len(value),
                "first_keys": sorted(value[0].keys()) if value and isinstance(value[0], dict) else None,
            }
        else:
            summary[key] = {"type": type(value).__name__, "preview": str(value)[:180]}
    return summary


def _dump_xhs_debug(url, final_url, html, data, note_nodes, extracted_images):
    safe_name = _safe_debug_name(final_url or url)

    state_path = _write_json_debug(
        f"{safe_name}_state",
        {
            "source_url": url,
            "final_url": final_url,
            "note_node_count": len(note_nodes),
            "extracted_count": len(extracted_images),
            "state": data,
        },
    )

    note_summaries = []
    for index, node in enumerate(note_nodes, start=1):
        image_lists = _find_all_lists(node, {"imageList", "image_list", "imagesList"})
        image_list_summaries = []
        for image_list in image_lists:
            image_list_summaries.append(
                {
                    "count": len(image_list),
                    "items": [_summarize_item_keys(item) for item in image_list[:10]],
                }
            )
        note_summaries.append(
            {
                "index": index,
                "title": _find_first_string(node, {"title", "noteTitle"}),
                "keys": sorted(node.keys()) if isinstance(node, dict) else [],
                "image_lists": image_list_summaries,
            }
        )

    summary_path = _write_json_debug(
        f"{safe_name}_summary",
        {
            "source_url": url,
            "final_url": final_url,
            "extracted_images": extracted_images,
            "note_summaries": note_summaries,
        },
    )

    html_path = _write_text_debug(f"{safe_name}_page", html)
    print(f"小红书调试文件已写入：{summary_path}")
    print(f"小红书状态快照已写入：{state_path}")
    print(f"小红书页面快照已写入：{html_path}")
    return summary_path, state_path, html_path


def _extract_original_only_from_item(item):
    if not isinstance(item, dict):
        return None

    width, height = _extract_dimensions(item)

    strict_sources = [
        ("masterUrl", ["masterUrl", "url"]),
        ("origin", ["origin", "url"]),
        ("original", ["original", "url"]),
    ]

    for key, preferred_keys in strict_sources:
        value = item.get(key)
        if value is None:
            continue
        candidate = _pick_best_url_from_value(
            value,
            preferred_keys=preferred_keys,
            width=width,
            height=height,
            source_prefix=f"strict:{key}",
        )
        if candidate and not _is_thumbnail_like(candidate):
            return candidate

    nested_sources = [
        ("urlDefaultInfo", {"masterUrl", "origin", "original"}),
        ("infoList", {"masterUrl", "origin", "original"}),
        ("stream", {"masterUrl", "origin", "original"}),
    ]

    for container_key, allowed_keys in nested_sources:
        container = item.get(container_key)
        if container is None:
            continue

        def walk_strict(obj):
            if isinstance(obj, dict):
                local_width, local_height = _extract_dimensions(obj)
                use_width = local_width or width
                use_height = local_height or height

                for strict_key in ["masterUrl", "origin", "original"]:
                    if strict_key in obj:
                        candidate = _pick_best_url_from_value(
                            obj[strict_key],
                            preferred_keys=[strict_key, "url"],
                            width=use_width,
                            height=use_height,
                            source_prefix=f"{container_key}:{strict_key}",
                        )
                        if candidate and not _is_thumbnail_like(candidate):
                            return candidate

                for key, value in obj.items():
                    if key in allowed_keys or isinstance(value, (dict, list)):
                        nested = walk_strict(value)
                        if nested:
                            return nested
            elif isinstance(obj, list):
                for value in obj:
                    nested = walk_strict(value)
                    if nested:
                        return nested
            return None

        candidate = walk_strict(container)
        if candidate:
            return candidate

    return None


def _extract_xhs_precise_images_from_state(data):
    note_nodes = _find_note_nodes(data)
    ordered = []
    seen = set()

    for node in note_nodes:
        image_lists = _find_all_lists(node, {"imageList", "image_list", "imagesList"})
        for image_list in image_lists:
            extracted = []
            local_seen = set()
            for item in image_list:
                candidate = _extract_original_only_from_item(item)
                if candidate and candidate["url"] not in seen and candidate["url"] not in local_seen:
                    local_seen.add(candidate["url"])
                    extracted.append(candidate)

            if extracted:
                seen.update(local_seen)
                ordered = extracted
                title = _find_first_string(node, {"title", "noteTitle"}) or _find_first_string(data, {"title", "noteTitle"})
                return ordered, title, note_nodes

    title = _find_first_string(data, {"title", "noteTitle"})
    return ordered, title, note_nodes


def get_xiaohongshu_precise_info(url):
    try:
        html, final_url = _fetch_page_html(url)
    except Exception as error:
        print("小红书页面请求失败：", repr(error))
        return None

    data = _parse_state_data(html)
    if not data:
        print("没有从小红书页面中提取到状态对象。")
        return None

    images, title, note_nodes = _extract_xhs_precise_images_from_state(data)
    _dump_xhs_debug(url, final_url, html, data, note_nodes, images)
    if not images:
        print("没有从小红书正文图片列表中提取到原图。")
        return None

    info = {
        "title": title or "未知",
        "thumbnails": images,
        "_source": "xiaohongshu_precise",
    }
    return info, final_url


def fallback_get_images(url):
    print("使用备用方案解析图片...")

    try:
        html, _ = _fetch_page_html(url)
    except Exception as error:
        print("请求失败：", repr(error))
        return []

    data = _parse_state_data(html)
    if not data:
        print("没有找到页面状态对象")
        return []

    image_urls = []

    def collect_from_image_list(image_list):
        if not isinstance(image_list, list):
            return

        for item in image_list:
            if not isinstance(item, dict):
                continue

            for key in ["url", "src", "origin", "masterUrl", "previewUrl"]:
                value = item.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    image_urls.append(value)

            for key in ["infoList", "urlDefaultInfo", "urlPre"]:
                value = item.get(key)
                if isinstance(value, (list, dict)):
                    nested_candidates = []
                    _append_nested_urls(nested_candidates, value, key)
                    image_urls.extend(candidate["url"] for candidate in nested_candidates)

    def search_note(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_lower = key.lower()

                if key_lower in ["imagelist", "imageslist", "images", "image_list"]:
                    collect_from_image_list(value)

                if key_lower == "cover":
                    if isinstance(value, str) and value.startswith("http"):
                        image_urls.append(value)
                    elif isinstance(value, dict):
                        for inner_value in value.values():
                            if isinstance(inner_value, str) and inner_value.startswith("http"):
                                image_urls.append(inner_value)

                search_note(value)
        elif isinstance(obj, list):
            for item in obj:
                search_note(item)

    search_note(data)

    info = {"thumbnails": [{"url": item} for item in image_urls]}
    return [item["url"] for item in prepare_image_downloads(info)]

#程序主入口，接收原始数据
def get_image_info(raw_text):
    url = extract_url(raw_text)#提取可用的url
    if not url:
        print("没有识别到有效链接！")
        return None

    if _is_xiaohongshu_url(url):#判断为小红书字段，用小红书专用提取方法
        precise_result = get_xiaohongshu_precise_info(url)
        if precise_result:
            return precise_result
        print("小红书专用提取失败，回退到通用解析。")

    result = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-check-certificate", url],
        capture_output=True,
        text=True,
    )

    if not result.stdout:
        print("常规解析失败，正在尝试网页解析方案")
        print("【DEBUG】yt-dlp错误信息:", result.stderr)

        image_urls = fallback_get_images(url)
        if image_urls:
            return {"thumbnails": [{"url": item} for item in image_urls]}, url

        print("未能从该链接中提取到图片资源。这个页面可能暂不支持，或者资源结构发生了变化。")
        return None

    info = json.loads(result.stdout)
    return info, url


def _detect_extension(url):
    low = url.lower()
    if ".png" in low:
        return ".png"
    if ".webp" in low:
        return ".webp"
    if ".jpeg" in low:
        return ".jpeg"
    if ".avif" in low:
        return ".avif"
    return ".jpg"


def build_image_filename(index, url):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{timestamp}_{index:02d}{_detect_extension(url)}"


def download_image(image_urls, save_path):
    if not image_urls:
        print("没有可下载的图片")
        return []

    if not os.path.exists(save_path):
        print(f"保存路径不存在{save_path}")
        return []

    downloaded_files = []

    for i, url in enumerate(image_urls, start=1):
        filename = os.path.join(save_path, build_image_filename(i, url))
        try:
            urllib.request.urlretrieve(url, filename)
            downloaded_files.append(filename)
            print(f"已下载：{filename}")
        except Exception as error:
            print(f"下载失败：{url}")
            print("[DEBUG]错误信息：", repr(error))

    return downloaded_files
