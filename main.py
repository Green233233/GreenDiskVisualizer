import sys
import threading
import platform
import ctypes
import time
from typing import List

import tkinter as tk
from tkinter import ttk, messagebox

from models import ScanOptions, ScanResult
from scanner import list_disks, scan_path
from treemap import build_treemap, TreemapNode


def _init_dpi_awareness() -> None:
    """在 Windows 上开启 DPI 感知，提高清晰度。"""
    if platform.system() != "Windows":
        return
    try:
        # Windows 7
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        try:
            # Windows 8.1+
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Green 磁盘空间可视化工具 alpha v0.0.1")
        self.geometry("1000x700")

        # 提升 Tkinter 自身缩放比例，在高分屏下更清晰
        try:
            current_scaling = float(self.tk.call("tk", "scaling"))
            if current_scaling < 1.5:
                self.tk.call("tk", "scaling", 1.5)
        except Exception:
            pass

        self._current_thread: threading.Thread | None = None
        self._scan_result: ScanResult | None = None
        self._resize_after_id: str | None = None

        # 扫描进度相关状态（由后台线程更新，UI 轮询显示）
        self._progress_files: int = 0
        self._progress_folders: int = 0
        self._progress_ratio: float = 0.0  # 0.0~1.0
        self._progress_last_path: str = ""
        self._scan_start_time: float = 0.0
        self._progress_updater_running: bool = False

        # 顶部工具栏区域
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        ttk.Label(top_frame, text="选择磁盘: ").pack(side=tk.LEFT)
        self.disk_var = tk.StringVar()
        self.disk_combo = ttk.Combobox(top_frame, textvariable=self.disk_var, state="readonly", width=25)
        self.disk_combo.pack(side=tk.LEFT, padx=(0, 8))

        self.scan_button = ttk.Button(top_frame, text="扫描", command=self.on_scan_clicked)
        self.scan_button.pack(side=tk.LEFT)

        # 扫描模式：快速 / 完整
        self.mode_var = tk.StringVar(value="fast")
        fast_btn = ttk.Radiobutton(top_frame, text="快速扫描", variable=self.mode_var, value="fast")
        full_btn = ttk.Radiobutton(top_frame, text="完整扫描", variable=self.mode_var, value="full")
        fast_btn.pack(side=tk.LEFT, padx=(16, 4))
        full_btn.pack(side=tk.LEFT)

        # 信息标签
        self.info_var = tk.StringVar(value="请选择磁盘并点击“扫描”。")
        info_label = ttk.Label(self, textvariable=self.info_var, anchor="w")
        info_label.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 2))

        # 明显的进度条（放在信息标签下方，带比例）
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=1000)
        self.progress.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))

        # 画布区域展示 treemap
        self.canvas = tk.Canvas(self, bg="#202020", highlightthickness=0, width=800, height=500)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 底部状态栏
        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)

        self.status_var = tk.StringVar(value="")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="e")
        status_label.pack(side=tk.RIGHT)

        self.load_disks()

    def load_disks(self) -> None:
        disks = list_disks()
        display_items = [f"{device} ({mount})" for device, mount in disks]
        self._disk_mounts = [mount for _, mount in disks]

        self.disk_combo["values"] = display_items
        if display_items:
            self.disk_combo.current(0)
            self.info_var.set("请选择磁盘并点击“扫描”。")
        else:
            self.info_var.set("未发现可扫描的磁盘。")

    def on_scan_clicked(self) -> None:
        if self._current_thread and self._current_thread.is_alive():
            messagebox.showinfo("扫描进行中", "当前已有扫描任务在执行，请稍候。")
            return

        idx = self.disk_combo.current()
        if idx < 0 or idx >= len(getattr(self, "_disk_mounts", [])):
            messagebox.showwarning("请选择磁盘", "请先选择一个磁盘。")
            return

        mount = self._disk_mounts[idx]
        mode = self.mode_var.get()

        if mode == "fast":
            # 快速扫描：限制深度并排除典型系统/临时目录
            exclude = [
                "$Recycle.Bin",
                "System Volume Information",
                "\\Windows\\WinSxS",
                "\\Windows\\Temp",
                "\\Windows\\Installer",
                "\\Program Files\\WindowsApps",
                "\\AppData\\Local\\Temp",
                ".git",
                "node_modules",
                "__pycache__",
            ]
            options = ScanOptions(
                path=mount,
                recursive=True,
                follow_symlinks=False,
                calculate_hash=False,
                exclude_patterns=exclude,
                max_depth=4,
            )
            self.info_var.set(f"正在快速扫描：{mount}（深度≤4，排除系统/临时目录）...")
        else:
            # 完整扫描：不限制深度，尽量少排除目录（仅跳过回收站等）
            exclude = [
                "$Recycle.Bin",
                "System Volume Information",
            ]
            options = ScanOptions(
                path=mount,
                recursive=True,
                follow_symlinks=False,
                calculate_hash=False,
                exclude_patterns=exclude,
                max_depth=None,
            )
            self.info_var.set(f"正在完整扫描：{mount}（可能耗时较长，请耐心等待）...")

        # 初始化进度状态
        self._scan_start_time = time.time()
        self._progress_files = 0
        self._progress_folders = 0
        self._progress_ratio = 0.0
        self._progress_last_path = ""
        self._progress_updater_running = True
        self.progress["value"] = 0
        self.status_var.set("进度：0.0%  预计剩余时间：估算中...")
        self.after(200, self._update_progress_ui)

        def worker():
            try:
                result = scan_path(options, progress_callback=self._on_scan_progress)
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda: self.on_scan_failed(str(e)))
                return
            self.after(0, lambda: self.on_scan_finished(result))

        t = threading.Thread(target=worker, daemon=True)
        self._current_thread = t
        t.start()

    def on_scan_finished(self, result: ScanResult) -> None:
        self._progress_updater_running = False
        self.progress["value"] = self.progress["maximum"]
        self._scan_result = result
        self.info_var.set(
            f"扫描完成：文件 {result.stats.file_count} 个，"
            f"文件夹 {result.stats.folder_count} 个，"
            f"用时 {result.scan_duration_ms} ms。"
        )
        self.status_var.set(
            f"总容量: {self._format_size(result.stats.total_size)}  "
            f"已用: {self._format_size(result.stats.used_size)}  "
            f"可用: {self._format_size(result.stats.free_size)}"
        )
        self._draw_treemap(result)

    def on_scan_failed(self, message: str) -> None:
        self._progress_updater_running = False
        messagebox.showerror("扫描失败", f"扫描过程中出现错误：\n{message}")

    def _on_scan_progress(self, files: int, folders: int, current_path: str, ratio: float) -> None:
        """由后台扫描线程调用，仅更新内部数值，不直接触碰 Tk。"""
        self._progress_files = files
        self._progress_folders = folders
        self._progress_last_path = current_path
        # 限制比例在 0~1 之间
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 1.0:
            ratio = 1.0
        self._progress_ratio = ratio

    def _update_progress_ui(self) -> None:
        """在主线程中定期调用，根据内部进度状态刷新进度条和预计剩余时间。"""
        if not self._progress_updater_running:
            return

        ratio = self._progress_ratio
        value = int(ratio * self.progress["maximum"])
        self.progress["value"] = value

        elapsed = max(0.0, time.time() - self._scan_start_time)
        if ratio > 0.01 and elapsed > 1.0:
            remaining = elapsed * (1.0 - ratio) / ratio
            if remaining < 0:
                remaining = 0
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            if mins > 0:
                eta_text = f"{mins}分{secs}秒"
            else:
                eta_text = f"{secs}秒"
        else:
            eta_text = "估算中..."

        self.status_var.set(
            f"进度：{ratio * 100:.1f}%  已扫描文件 {self._progress_files} 个 / 目录 {self._progress_folders} 个  "
            f"预计剩余时间：{eta_text}"
        )

        # 继续轮询
        self.after(500, self._update_progress_ui)

    def _draw_treemap(self, result: ScanResult) -> None:
        self.canvas.delete("all")
        if not result.files:
            return

        size_by_root: dict[str, int] = {}
        root_path = result.stats.disk_path.rstrip("\\/")
        root_len = len(root_path)
        for fi in result.files:
            rel = fi.path[root_len:].lstrip("\\/")
            root_component = rel.split("\\", 1)[0] if rel else fi.name
            size_by_root.setdefault(root_component, 0)
            size_by_root[root_component] += fi.size

        sorted_items = sorted(size_by_root.items(), key=lambda x: x[1], reverse=True)[:50]
        if not sorted_items:
            return

        total_size = sum(s for _, s in sorted_items)
        if total_size <= 0:
            return

        MIN_RATIO = 0.015
        main_items: list[tuple[str, int]] = []
        other_size = 0
        other_count = 0
        for component, size in sorted_items:
            if size / total_size >= MIN_RATIO:
                full_path = root_path + "\\" + component
                main_items.append((full_path, size))
            else:
                other_size += size
                other_count += 1
        if other_count > 0 and other_size > 0:
            main_items.append((f"其他 ({other_count} 个文件夹)", other_size))

        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 500)

        nodes: List[TreemapNode] = build_treemap(
            [(label, size, None) for label, size in main_items],
            width=width,
            height=height,
        )

        colors = [
            "#4e79a7",
            "#a0cbe8",
            "#f28e2b",
            "#ffbe7d",
            "#59a14f",
            "#8cd17d",
            "#76b7b2",
            "#b07aa1",
            "#edc949",
            "#9c755f",
        ]

        for i, node in enumerate(nodes):
            color = colors[i % len(colors)]
            x0, y0 = node.x, node.y
            x1, y1 = node.x + node.width, node.y + node.height
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="#404040")

            bw = node.width
            bh = node.height
            size_text = self._format_size(int(node.size))
            pad = 5
            if bw > 100 and bh > 48:
                max_chars = max(4, int((bw - pad * 2) / 8))
                display_label = node.label if len(node.label) <= max_chars else node.label[:max_chars - 2] + ".."
                self.canvas.create_text(
                    x0 + pad, y0 + pad, anchor="nw",
                    text=display_label, fill="#ffffff", font=("Segoe UI", 9, "bold"),
                )
                self.canvas.create_text(
                    x0 + pad, y0 + pad + 22, anchor="nw",
                    text=size_text, fill="#dddddd", font=("Segoe UI", 8),
                )
            elif bw > 50 and bh > 22:
                max_chars = max(3, int((bw - 8) / 7))
                display_label = node.label if len(node.label) <= max_chars else node.label[:max_chars - 2] + ".."
                self.canvas.create_text(
                    x0 + 4, y0 + 4, anchor="nw",
                    text=display_label, fill="#ffffff", font=("Segoe UI", 7),
                )
            elif bw > 24 and bh > 14:
                max_chars = max(2, int((bw - 4) / 6))
                short = node.label if len(node.label) <= max_chars else node.label[:max_chars - 2] + ".."
                self.canvas.create_text(
                    x0 + 2, y0 + 2, anchor="nw",
                    text=short, fill="#cccccc", font=("Segoe UI", 6),
                )

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """窗口或画布尺寸变化时，防抖后重新绘制 treemap，避免拖动时密集重绘导致卡顿。"""
        if self._scan_result is None:
            return
        if event.width < 100 or event.height < 100:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(150, self._deferred_redraw)

    def _deferred_redraw(self) -> None:
        self._resize_after_id = None
        if self._scan_result is not None:
            self._draw_treemap(self._scan_result)

    @staticmethod
    def _format_size(size: int) -> str:
        if size <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        value = float(size)
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        return f"{value:.2f} {units[idx]}"


def main() -> None:
    _init_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

