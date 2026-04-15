import io
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import requests

from image_handler import download_image, get_image_info, prepare_image_downloads
from utils import format_duration
from video_handler import download_video, get_video_info

try:
    from PIL import Image, ImageTk
except ImportError:  # Pillow 未安装时退回文本模式
    Image = None
    ImageTk = None


THUMBNAIL_SIZE = (180, 180)


class DownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Video / Image Downloader v1")
        self.root.geometry("980x760")

        self.default_path = tk.StringVar(value="/Users/yanshoulong/Downloads")
        self.mode = tk.StringVar(value="image")
        self.image_candidates = []
        self.image_vars = []
        self.thumbnail_refs = []

        self.build_ui()

    def build_ui(self):
        title_label = tk.Label(self.root, text="分享链接下载工具", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)

        mode_frame = tk.Frame(self.root)
        mode_frame.pack(pady=5)

        tk.Label(mode_frame, text="选择模式：").pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="图片", variable=self.mode, value="image").pack(side=tk.LEFT, padx=8)
        tk.Radiobutton(mode_frame, text="视频", variable=self.mode, value="video").pack(side=tk.LEFT, padx=8)

        input_frame = tk.Frame(self.root)
        input_frame.pack(fill=tk.BOTH, expand=False, padx=12, pady=8)

        tk.Label(input_frame, text="粘贴分享文本或链接：").pack(anchor="w")
        self.input_text = scrolledtext.ScrolledText(input_frame, height=10, wrap=tk.WORD)
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=6)

        path_frame = tk.Frame(self.root)
        path_frame.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(path_frame, text="保存路径：").pack(side=tk.LEFT)
        self.path_entry = tk.Entry(path_frame, textvariable=self.default_path, width=65)
        self.path_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        tk.Button(path_frame, text="选择路径", command=self.choose_path).pack(side=tk.LEFT)

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="获取信息", width=14, command=self.preview).pack(side=tk.LEFT, padx=8)
        tk.Button(button_frame, text="开始下载", width=14, command=self.download).pack(side=tk.LEFT, padx=8)
        tk.Button(button_frame, text="清空输入", width=14, command=self.clear_input).pack(side=tk.LEFT, padx=8)

        select_frame = tk.LabelFrame(self.root, text="图片选择（预览后可多选）")
        select_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        tools_frame = tk.Frame(select_frame)
        tools_frame.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(tools_frame, text="全选", width=10, command=self.select_all_images).pack(side=tk.LEFT, padx=4)
        tk.Button(tools_frame, text="清空选择", width=10, command=self.clear_image_selection).pack(side=tk.LEFT, padx=4)

        self.preview_hint = tk.Label(
            tools_frame,
            text="当前为可视化选择模式" if Image else "未安装 Pillow，暂时只能显示文本信息",
        )
        self.preview_hint.pack(side=tk.LEFT, padx=12)

        self.preview_canvas = tk.Canvas(select_frame, height=280)
        self.preview_scrollbar = tk.Scrollbar(select_frame, orient=tk.VERTICAL, command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=self.preview_scrollbar.set)
        self.preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.preview_inner = tk.Frame(self.preview_canvas)
        self.preview_canvas.create_window((0, 0), window=self.preview_inner, anchor="nw")
        self.preview_inner.bind("<Configure>", self.on_preview_configure)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        tk.Label(log_frame, text="输出日志：").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=6)

    def on_preview_configure(self, _event):
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

    def log(self, message: str):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def choose_path(self):
        folder = filedialog.askdirectory(initialdir=self.default_path.get())
        if folder:
            self.default_path.set(folder)
            self.log(f"已切换保存路径：{folder}")

    def clear_preview_grid(self):
        for widget in self.preview_inner.winfo_children():
            widget.destroy()
        self.image_vars = []
        self.thumbnail_refs = []

    def clear_input(self):
        self.input_text.delete("1.0", tk.END)
        self.image_candidates = []
        self.clear_preview_grid()
        self.log("已清空输入框。")

    def get_raw_text(self) -> str:
        return self.input_text.get("1.0", tk.END).strip()

    def fetch_thumbnail(self, url):
        if not Image:
            return None

        try:
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image.thumbnail(THUMBNAIL_SIZE)
            return ImageTk.PhotoImage(image)
        except Exception as error:
            self.log(f"缩略图加载失败：{url}，原因：{error}")
            return None

    def render_image_candidates(self):
        self.clear_preview_grid()

        columns = 4
        for index, item in enumerate(self.image_candidates):
            row = index // columns
            column = index % columns
            checked = tk.BooleanVar(value=True)
            self.image_vars.append(checked)

            card = tk.Frame(self.preview_inner, bd=1, relief=tk.GROOVE, padx=6, pady=6)
            card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)

            thumb = self.fetch_thumbnail(item["url"])
            if thumb:
                self.thumbnail_refs.append(thumb)
                image_label = tk.Label(card, image=thumb, width=THUMBNAIL_SIZE[0], height=THUMBNAIL_SIZE[1])
                image_label.pack()
            else:
                placeholder = tk.Label(
                    card,
                    text="无法预览\n可直接下载原图",
                    width=24,
                    height=10,
                    bg="#efefef",
                    justify=tk.CENTER,
                )
                placeholder.pack(fill=tk.BOTH, expand=True)

            size_text = "未知尺寸"
            if item.get("width") and item.get("height"):
                size_text = f'{item["width"]}x{item["height"]}'

            checkbox = tk.Checkbutton(card, text=f"选择第 {index + 1} 张", variable=checked)
            checkbox.pack(anchor="w", pady=(6, 0))
            tk.Label(card, text=size_text).pack(anchor="w")
            tk.Label(card, text=item["url"], wraplength=180, justify=tk.LEFT).pack(anchor="w")

        for column in range(columns):
            self.preview_inner.grid_columnconfigure(column, weight=1)

    def select_all_images(self):
        for var in self.image_vars:
            var.set(True)

    def clear_image_selection(self):
        for var in self.image_vars:
            var.set(False)

    def get_selected_image_urls(self):
        selected = []
        for index, var in enumerate(self.image_vars):
            if var.get():
                selected.append(self.image_candidates[index]["url"])
        return selected

    def preview(self):
        raw_text = self.get_raw_text()
        if not raw_text:
            messagebox.showwarning("提示", "请先粘贴分享文本或链接。")
            return

        if self.mode.get() == "image":
            self.preview_image(raw_text)
        else:
            self.preview_video(raw_text)

    def preview_image(self, raw_text: str):
        self.log("开始解析图片信息...")
        result = get_image_info(raw_text)

        if not result:
            self.image_candidates = []
            self.clear_preview_grid()
            self.log("未能提取到图片资源。")
            messagebox.showerror("解析失败", "未能从该链接提取图片资源。")
            return

        info, _ = result
        self.image_candidates = prepare_image_downloads(info)
        self.log(f"标题：{info.get('title', '未知')}")

        if not self.image_candidates:
            self.clear_preview_grid()
            self.log("没有找到可用图片。")
            messagebox.showinfo("提示", "没有找到可下载的图片。")
            return

        self.render_image_candidates()
        self.log(f"筛选后可下载图片数量：{len(self.image_candidates)}")
        for index, item in enumerate(self.image_candidates[:10], start=1):
            size_text = "未知尺寸"
            if item.get("width") and item.get("height"):
                size_text = f'{item["width"]}x{item["height"]}'
            self.log(f"{index}. [{size_text}] {item['url']}")

    def preview_video(self, raw_text: str):
        self.log("开始解析视频信息...")
        result = get_video_info(raw_text)

        if not result:
            self.log("未能提取到视频资源。")
            messagebox.showerror("解析失败", "未能从该链接提取视频资源。")
            return

        info, _ = result
        title = info.get("title", "未知")
        duration = format_duration(info.get("duration"))
        cookie_source = info.get("_cookie_source", "未知")

        self.log(f"标题：{title}")
        self.log(f"时长：{duration}")
        self.log(f"cookies 来源：{cookie_source}")

    def download(self):
        raw_text = self.get_raw_text()
        save_path = self.default_path.get().strip()

        if not raw_text:
            messagebox.showwarning("提示", "请先粘贴分享文本或链接。")
            return

        if not save_path:
            messagebox.showwarning("提示", "请先设置保存路径。")
            return

        if self.mode.get() == "image":
            self.download_image_mode(raw_text, save_path)
        else:
            self.download_video_mode(raw_text, save_path)

    def download_image_mode(self, raw_text: str, save_path: str):
        if not self.image_candidates:
            self.preview_image(raw_text)
            if not self.image_candidates:
                return

        image_urls = self.get_selected_image_urls()
        if not image_urls:
            messagebox.showwarning("提示", "请先选择至少一张图片。")
            return

        self.log(f"开始下载，共 {len(image_urls)} 张图片...")
        downloaded_files = download_image(image_urls, save_path)

        if downloaded_files:
            self.log(f"成功下载 {len(downloaded_files)} 张图片。")
            messagebox.showinfo("完成", f"图片下载完成，共 {len(downloaded_files)} 张。")
        else:
            self.log("图片下载失败。")
            messagebox.showerror("失败", "图片下载失败，请查看日志。")

    def download_video_mode(self, raw_text: str, save_path: str):
        self.log("开始准备下载视频...")
        result = get_video_info(raw_text)

        if not result:
            self.log("视频解析失败，无法下载。")
            messagebox.showerror("下载失败", "视频解析失败，无法下载。")
            return

        _, url = result
        self.log(f"保存路径：{save_path}")
        success = download_video(url, save_path)

        if success:
            self.log("视频下载流程结束。")
            messagebox.showinfo("完成", "视频下载流程已完成，请查看保存目录。")
        else:
            self.log("视频下载失败，请检查 cookies 或链接是否有效。")
            messagebox.showerror("失败", "视频下载失败，请查看日志。")


if __name__ == "__main__":
    root = tk.Tk()
    app = DownloaderGUI(root)
    root.mainloop()
