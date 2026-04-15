import json
import subprocess
import sys

from utils import extract_url


BROWSER_COOKIE_CANDIDATES = ["chrome", "safari", "firefox", "edge"]


def _run_yt_dlp_json(url, cookie_file=None, browser_cookie=None):
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-json",
        "--no-check-certificate",
    ]

    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
    elif browser_cookie:
        cmd.extend(["--cookies-from-browser", browser_cookie])

    cmd.append(url)

    return subprocess.run(cmd, capture_output=True, text=True)


def get_video_info(raw_text, cookie_file=None, auto_browser_cookies=True):
    url = extract_url(raw_text)
    if not url:
        print("没有识别到有效链接！")
        return None

    result = _run_yt_dlp_json(url, cookie_file=cookie_file)
    cookie_source = f"cookie 文件: {cookie_file}" if cookie_file else "无 cookies"

    if not result.stdout and auto_browser_cookies:
        for browser in BROWSER_COOKIE_CANDIDATES:
            retry = _run_yt_dlp_json(url, browser_cookie=browser)
            if retry.stdout:
                result = retry
                cookie_source = f"浏览器 cookies: {browser}"
                break

    if not result.stdout:
        print("获取视频信息失败")
        print("STDERR:", result.stderr)

        if "Fresh cookies" in result.stderr:
            print("抖音当前需要有效 cookies，建议导出最新浏览器登录态，或直接使用浏览器 cookies。")

        return None

    info = json.loads(result.stdout)
    info["_cookie_source"] = cookie_source
    return info, url


def download_video(url, path, cookie_file=None, auto_browser_cookies=True):
    base_cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-check-certificate",
        "-P",
        path,
        "-o",
        "%(title)s.%(ext)s",
    ]

    attempts = []
    if cookie_file:
        attempts.append(base_cmd + ["--cookies", cookie_file, url])
    else:
        attempts.append(base_cmd + [url])

    if auto_browser_cookies:
        for browser in BROWSER_COOKIE_CANDIDATES:
            attempts.append(base_cmd + ["--cookies-from-browser", browser, url])

    last_result = None
    for cmd in attempts:
        result = subprocess.run(cmd, capture_output=True, text=True)
        last_result = result
        if result.returncode == 0:
            return True

    if last_result:
        print("视频下载失败")
        print("STDERR:", last_result.stderr)
    return False
