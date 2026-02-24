import sys
import threading
import platform
import ctypes
import colorsys
import time
from typing import List

import tkinter as tk
from tkinter import ttk, messagebox

from models import ScanOptions, ScanResult
from scanner import list_disks, scan_path
from treemap import build_treemap, TreemapNode

_BASE_HUES = [210, 155, 30, 275, 345, 185, 75, 120, 240, 50]


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    """HSL 转十六进制颜色。h: 0-360, s: 0-1, l: 0-1"""
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _init_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _hide_console() -> None:
    if platform.system() != "Windows":
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        try:
            current_scaling = float(self.tk.call("tk", "scaling"))
            if current_scaling < 1.5:
                self.tk.call("tk", "scaling", 1.5)
        except Exception:
            pass

        self.withdraw()
        self._create_splash()
        self._update_splash_progress(0.05, "\u6b63\u5728\u521d\u59cb\u5316...")
        self.after(50, self._init_main_ui)

    # ── 启动画面 ──────────────────────────────────────────────

    def _create_splash(self) -> None:
        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)
        splash.configure(bg="#1a1a2e")

        sw, sh = 520, 340
        scr_w = splash.winfo_screenwidth()
        scr_h = splash.winfo_screenheight()
        splash.geometry(f"{sw}x{sh}+{(scr_w - sw) // 2}+{(scr_h - sh) // 2}")

        c = tk.Canvas(splash, width=sw, height=sh, bg="#1a1a2e", highlightthickness=0)
        c.pack(fill=tk.BOTH, expand=True)

        c.create_rectangle(0, 0, sw, sh, outline="#4ecca3", width=2)
        c.create_text(sw // 2, 60, text="Green", fill="#4ecca3",
                       font=("Segoe UI", 24, "bold"))
        c.create_text(sw // 2, 125,
                       text="\u78c1\u76d8\u7a7a\u95f4\u53ef\u89c6\u5316\u5de5\u5177",
                       fill="#e0e0e0", font=("Segoe UI", 12))
        c.create_text(sw // 2, 170, text="alpha v0.0.1",
                       fill="#7f8c8d", font=("Segoe UI", 8))

        bar_x, bar_w = 60, sw - 120
        bar_y, bar_h = 220, 18
        c.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                            fill="#2c2c4a", outline="#3a3a5c")
        self._splash_bar_fill = c.create_rectangle(
            bar_x + 1, bar_y + 1, bar_x + 1, bar_y + bar_h - 1,
            fill="#4ecca3", outline="")
        self._splash_bar_info = (bar_x, bar_y, bar_w, bar_h)

        self._splash_pct_id = c.create_text(
            sw // 2, bar_y + bar_h + 25, text="0%",
            fill="#7f8c8d", font=("Segoe UI", 8))

        self._splash_status_id = c.create_text(
            sw // 2, bar_y + bar_h + 55, text="",
            fill="#bdc3c7", font=("Segoe UI", 8))

        self._splash = splash
        self._splash_canvas = c
        splash.update()

    def _update_splash_progress(self, ratio: float, text: str) -> None:
        try:
            if not self._splash.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return
        ratio = max(0.0, min(ratio, 1.0))
        bar_x, bar_y, bar_w, bar_h = self._splash_bar_info
        fill_w = int(bar_w * ratio)
        self._splash_canvas.coords(
            self._splash_bar_fill,
            bar_x + 1, bar_y + 1,
            bar_x + 1 + fill_w, bar_y + bar_h - 1,
        )
        self._splash_canvas.itemconfig(
            self._splash_pct_id, text=f"{int(ratio * 100)}%")
        self._splash_canvas.itemconfig(
            self._splash_status_id, text=text)
        self._splash.update()

    # ── 主界面初始化 ─────────────────────────────────────────

    def _init_main_ui(self) -> None:
        self._update_splash_progress(0.10, "\u6b63\u5728\u521b\u5efa\u7a97\u53e3...")

        self.title("Green \u78c1\u76d8\u7a7a\u95f4\u53ef\u89c6\u5316\u5de5\u5177 alpha v0.0.1")
        self.geometry("1000x700")

        self._current_thread: threading.Thread | None = None
        self._scan_result: ScanResult | None = None
        self._resize_after_id: str | None = None

        self._progress_files: int = 0
        self._progress_folders: int = 0
        self._progress_ratio: float = 0.0
        self._progress_last_path: str = ""
        self._scan_start_time: float = 0.0
        self._progress_updater_running: bool = False

        self._update_splash_progress(0.25, "\u6b63\u5728\u521b\u5efa\u754c\u9762\u7ec4\u4ef6...")

        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        ttk.Label(top_frame, text="\u9009\u62e9\u78c1\u76d8: ").pack(side=tk.LEFT)
        self.disk_var = tk.StringVar()
        self.disk_combo = ttk.Combobox(
            top_frame, textvariable=self.disk_var, state="readonly", width=25)
        self.disk_combo.pack(side=tk.LEFT, padx=(0, 8))

        self.scan_button = ttk.Button(
            top_frame, text="\u626b\u63cf", command=self.on_scan_clicked)
        self.scan_button.pack(side=tk.LEFT)

        self.mode_var = tk.StringVar(value="fast")
        fast_btn = ttk.Radiobutton(
            top_frame, text="\u5feb\u901f\u626b\u63cf",
            variable=self.mode_var, value="fast")
        full_btn = ttk.Radiobutton(
            top_frame, text="\u5b8c\u6574\u626b\u63cf",
            variable=self.mode_var, value="full")
        fast_btn.pack(side=tk.LEFT, padx=(16, 4))
        full_btn.pack(side=tk.LEFT)

        self._update_splash_progress(0.45, "\u6b63\u5728\u521b\u5efa\u754c\u9762\u7ec4\u4ef6...")

        self.info_var = tk.StringVar(
            value="\u8bf7\u9009\u62e9\u78c1\u76d8\u5e76\u70b9\u51fb\u201c\u626b\u63cf\u201d\u3002")
        info_label = ttk.Label(self, textvariable=self.info_var, anchor="w")
        info_label.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 2))

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=1000)
        self.progress.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))

        self.canvas = tk.Canvas(
            self, bg="#1a1a2a", highlightthickness=0, width=800, height=500)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)

        self.status_var = tk.StringVar(value="")
        status_label = ttk.Label(
            status_frame, textvariable=self.status_var, anchor="e")
        status_label.pack(side=tk.RIGHT)

        self._update_splash_progress(0.65, "\u6b63\u5728\u68c0\u6d4b\u78c1\u76d8\u4fe1\u606f...")
        self.load_disks()

        self._update_splash_progress(1.0, "\u542f\u52a8\u5b8c\u6210")
        self.after(350, self._close_splash)

    def _close_splash(self) -> None:
        try:
            self._splash.destroy()
        except Exception:
            pass
        self.deiconify()

    # ── 磁盘列表 / 扫描逻辑 ──────────────────────────────────

    def load_disks(self) -> None:
        disks = list_disks()
        display_items = [f"{device} ({mount})" for device, mount in disks]
        self._disk_mounts = [mount for _, mount in disks]

        self.disk_combo["values"] = display_items
        if display_items:
            self.disk_combo.current(0)
            self.info_var.set(
                "\u8bf7\u9009\u62e9\u78c1\u76d8\u5e76\u70b9\u51fb\u201c\u626b\u63cf\u201d\u3002")
        else:
            self.info_var.set("\u672a\u53d1\u73b0\u53ef\u626b\u63cf\u7684\u78c1\u76d8\u3002")

    def on_scan_clicked(self) -> None:
        if self._current_thread and self._current_thread.is_alive():
            messagebox.showinfo(
                "\u626b\u63cf\u8fdb\u884c\u4e2d",
                "\u5f53\u524d\u5df2\u6709\u626b\u63cf\u4efb\u52a1\u5728\u6267\u884c\uff0c\u8bf7\u7a0d\u5019\u3002")
            return

        idx = self.disk_combo.current()
        if idx < 0 or idx >= len(getattr(self, "_disk_mounts", [])):
            messagebox.showwarning(
                "\u8bf7\u9009\u62e9\u78c1\u76d8",
                "\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u78c1\u76d8\u3002")
            return

        mount = self._disk_mounts[idx]
        mode = self.mode_var.get()

        if mode == "fast":
            exclude = [
                "$Recycle.Bin", "System Volume Information",
                "\\Windows\\WinSxS", "\\Windows\\Temp",
                "\\Windows\\Installer", "\\Program Files\\WindowsApps",
                "\\AppData\\Local\\Temp",
                ".git", "node_modules", "__pycache__",
            ]
            options = ScanOptions(
                path=mount, recursive=True, follow_symlinks=False,
                calculate_hash=False, exclude_patterns=exclude,
                max_depth=None, collect_file_details=False,
            )
            self.info_var.set(
                f"\u6b63\u5728\u5feb\u901f\u626b\u63cf\uff1a{mount}"
                f"\uff08\u667a\u80fd\u805a\u5408\u6a21\u5f0f\uff0c"
                f"\u6392\u9664\u7cfb\u7edf/\u4e34\u65f6\u76ee\u5f55\uff09...")
        else:
            exclude = ["$Recycle.Bin", "System Volume Information"]
            options = ScanOptions(
                path=mount, recursive=True, follow_symlinks=False,
                calculate_hash=False, exclude_patterns=exclude,
                max_depth=None,
            )
            self.info_var.set(
                f"\u6b63\u5728\u5b8c\u6574\u626b\u63cf\uff1a{mount}"
                f"\uff08\u53ef\u80fd\u8017\u65f6\u8f83\u957f\uff0c"
                f"\u8bf7\u8010\u5fc3\u7b49\u5f85\uff09...")

        self._scan_start_time = time.time()
        self._progress_files = 0
        self._progress_folders = 0
        self._progress_ratio = 0.0
        self._progress_last_path = ""
        self._progress_updater_running = True
        self.progress["value"] = 0
        self.status_var.set(
            "\u8fdb\u5ea6\uff1a0.0%  "
            "\u9884\u8ba1\u5269\u4f59\u65f6\u95f4\uff1a\u4f30\u7b97\u4e2d...")
        self.after(200, self._update_progress_ui)

        def worker():
            try:
                result = scan_path(
                    options, progress_callback=self._on_scan_progress)
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
            f"\u626b\u63cf\u5b8c\u6210\uff1a\u6587\u4ef6 {result.stats.file_count} \u4e2a\uff0c"
            f"\u6587\u4ef6\u5939 {result.stats.folder_count} \u4e2a\uff0c"
            f"\u7528\u65f6 {result.scan_duration_ms} ms\u3002")
        self.status_var.set(
            f"\u603b\u5bb9\u91cf: {self._format_size(result.stats.total_size)}  "
            f"\u5df2\u7528: {self._format_size(result.stats.used_size)}  "
            f"\u53ef\u7528: {self._format_size(result.stats.free_size)}")
        self._draw_treemap(result)

    def on_scan_failed(self, message: str) -> None:
        self._progress_updater_running = False
        messagebox.showerror(
            "\u626b\u63cf\u5931\u8d25",
            f"\u626b\u63cf\u8fc7\u7a0b\u4e2d\u51fa\u73b0\u9519\u8bef\uff1a\n{message}")

    def _on_scan_progress(self, files: int, folders: int,
                          current_path: str, ratio: float) -> None:
        self._progress_files = files
        self._progress_folders = folders
        self._progress_last_path = current_path
        self._progress_ratio = max(0.0, min(ratio, 1.0))

    def _update_progress_ui(self) -> None:
        if not self._progress_updater_running:
            return

        ratio = self._progress_ratio
        self.progress["value"] = int(ratio * self.progress["maximum"])

        elapsed = max(0.0, time.time() - self._scan_start_time)
        if ratio > 0.01 and elapsed > 1.0:
            remaining = max(0.0, elapsed * (1.0 - ratio) / ratio)
            mins, secs = int(remaining // 60), int(remaining % 60)
            eta_text = f"{mins}\u5206{secs}\u79d2" if mins > 0 else f"{secs}\u79d2"
        else:
            eta_text = "\u4f30\u7b97\u4e2d..."

        self.status_var.set(
            f"\u8fdb\u5ea6\uff1a{ratio * 100:.1f}%  "
            f"\u5df2\u626b\u63cf\u6587\u4ef6 {self._progress_files} \u4e2a / "
            f"\u76ee\u5f55 {self._progress_folders} \u4e2a  "
            f"\u9884\u8ba1\u5269\u4f59\u65f6\u95f4\uff1a{eta_text}")
        self.after(500, self._update_progress_ui)

    # ── Treemap 可视化（两级嵌套） ────────────────────────────

    def _build_hierarchy(self, result: ScanResult
                         ) -> tuple[dict[str, dict], int]:
        """从 ScanResult 构建两级层级：
        {name: {"total": int, "children": {child_name: int}}}
        """
        root_path = result.stats.disk_path.rstrip("\\/")
        root_len = len(root_path)
        hierarchy: dict[str, dict] = {}

        for fi in result.files:
            rel = fi.path[root_len:].lstrip("\\/")
            parts = rel.replace("/", "\\").split("\\")
            if not parts or not parts[0]:
                continue
            level1 = parts[0]
            level2 = parts[1] if len(parts) >= 2 else None

            entry = hierarchy.setdefault(
                level1, {"total": 0, "children": {}})
            entry["total"] += fi.size
            if level2:
                entry["children"][level2] = (
                    entry["children"].get(level2, 0) + fi.size)

        grand_total = sum(v["total"] for v in hierarchy.values())
        return hierarchy, grand_total

    def _draw_treemap(self, result: ScanResult) -> None:
        self.canvas.delete("all")
        if not result.files:
            return

        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 500)

        hierarchy, grand_total = self._build_hierarchy(result)
        if grand_total <= 0:
            return

        sorted_top = sorted(
            hierarchy.items(), key=lambda kv: kv[1]["total"], reverse=True)

        MIN_RATIO = 0.008
        main_items: list[tuple[str, dict]] = []
        other_size = 0
        other_count = 0
        for name, data in sorted_top:
            if data["total"] / grand_total >= MIN_RATIO:
                main_items.append((name, data))
            else:
                other_size += data["total"]
                other_count += 1
        if other_count > 0 and other_size > 0:
            main_items.append(
                (f"\u5176\u4ed6 ({other_count} \u9879)",
                 {"total": other_size, "children": {}}))

        top_nodes = build_treemap(
            [(name, data["total"], data) for name, data in main_items],
            width=width, height=height,
        )

        GAP = 2
        for i, node in enumerate(top_nodes):
            hue = _BASE_HUES[i % len(_BASE_HUES)]
            data = node.data if isinstance(node.data, dict) else {}
            children = data.get("children", {})
            has_children = bool(children) and sum(children.values()) > 0

            bx = node.x + GAP
            by = node.y + GAP
            bw = node.width - GAP * 2
            bh = node.height - GAP * 2
            if bw < 4 or bh < 4:
                continue

            pct = node.size / grand_total * 100
            size_text = self._format_size(int(node.size))

            if has_children and bw > 80 and bh > 70:
                self._draw_nested_block(
                    node.label, size_text, pct, children,
                    bx, by, bw, bh, hue, node.size)
            else:
                self._draw_simple_block(
                    node.label, size_text, pct,
                    bx, by, bw, bh, hue)

    def _draw_nested_block(self, label: str, size_text: str, pct: float,
                           children: dict, x: float, y: float,
                           w: float, h: float, hue: int,
                           parent_size: float) -> None:
        bg = _hsl_to_hex(hue, 0.25, 0.16)
        border = _hsl_to_hex(hue, 0.30, 0.35)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill=bg, outline=border, width=1)

        header_h = 26
        hdr_color = _hsl_to_hex(hue, 0.50, 0.30)
        self.canvas.create_rectangle(
            x, y, x + w, y + header_h, fill=hdr_color, outline="")

        if w > 200:
            header_text = f"{label}   {size_text} ({pct:.1f}%)"
        elif w > 120:
            header_text = f"{label}  {size_text}"
        else:
            header_text = label

        max_chars = max(3, int(w / 8))
        if len(header_text) > max_chars:
            header_text = header_text[:max_chars - 1] + "\u2026"

        self.canvas.create_text(
            x + 6, y + header_h / 2, anchor="w",
            text=header_text, fill="#f0f0f0",
            font=("Segoe UI", 8, "bold"))

        child_x = x + 1
        child_y = y + header_h + 1
        child_w = w - 2
        child_h = h - header_h - 2
        if child_w > 10 and child_h > 10:
            self._draw_child_blocks(
                children, child_x, child_y, child_w, child_h,
                hue, parent_size)

    def _draw_child_blocks(self, children: dict,
                           x: float, y: float, w: float, h: float,
                           parent_hue: int, parent_size: float) -> None:
        sorted_ch = sorted(children.items(), key=lambda kv: kv[1],
                           reverse=True)

        MAX_CHILDREN = 25
        if len(sorted_ch) > MAX_CHILDREN:
            main = sorted_ch[:MAX_CHILDREN]
            rest_size = sum(s for _, s in sorted_ch[MAX_CHILDREN:])
            rest_count = len(sorted_ch) - MAX_CHILDREN
            if rest_size > 0:
                main.append((f"\u5176\u4ed6 ({rest_count} \u9879)", rest_size))
            sorted_ch = main

        total_ch = sum(s for _, s in sorted_ch)
        if total_ch <= 0:
            return

        filtered: list[tuple[str, int]] = []
        other_size = 0
        other_count = 0
        for name, size in sorted_ch:
            if size / total_ch >= 0.005:
                filtered.append((name, size))
            else:
                other_size += size
                other_count += 1
        if other_count > 0 and other_size > 0:
            filtered.append((f"\u5176\u4ed6 ({other_count} \u9879)", other_size))
        if not filtered:
            return

        child_nodes = build_treemap(
            [(name, size, None) for name, size in filtered],
            width=int(w), height=int(h))

        CHILD_GAP = 1
        for j, cn in enumerate(child_nodes):
            cx = cn.x + x + CHILD_GAP
            cy = cn.y + y + CHILD_GAP
            cw = cn.width - CHILD_GAP * 2
            ch = cn.height - CHILD_GAP * 2
            if cw < 3 or ch < 3:
                continue

            lightness = 0.27 + (j % 5) * 0.045
            fill = _hsl_to_hex(parent_hue, 0.38, lightness)
            outline = _hsl_to_hex(parent_hue, 0.20, 0.42)
            self.canvas.create_rectangle(
                cx, cy, cx + cw, cy + ch,
                fill=fill, outline=outline, width=1)

            child_pct = cn.size / parent_size * 100 if parent_size > 0 else 0
            child_size = self._format_size(int(cn.size))

            if cw > 90 and ch > 40:
                max_c = max(4, int((cw - 8) / 7))
                disp = (cn.label if len(cn.label) <= max_c
                        else cn.label[:max_c - 1] + "\u2026")
                self.canvas.create_text(
                    cx + 4, cy + 4, anchor="nw", text=disp,
                    fill="#e8e8e8", font=("Segoe UI", 7, "bold"))
                self.canvas.create_text(
                    cx + 4, cy + 21, anchor="nw",
                    text=f"{child_size} ({child_pct:.0f}%)",
                    fill="#bbbbbb", font=("Segoe UI", 6))
            elif cw > 40 and ch > 20:
                max_c = max(3, int((cw - 6) / 6))
                disp = (cn.label if len(cn.label) <= max_c
                        else cn.label[:max_c - 1] + "\u2026")
                self.canvas.create_text(
                    cx + 3, cy + 3, anchor="nw", text=disp,
                    fill="#d0d0d0", font=("Segoe UI", 6))
            elif cw > 20 and ch > 12:
                max_c = max(2, int((cw - 4) / 5))
                disp = (cn.label if len(cn.label) <= max_c
                        else cn.label[:max_c] + "\u2026")
                self.canvas.create_text(
                    cx + 2, cy + 2, anchor="nw", text=disp,
                    fill="#b0b0b0", font=("Segoe UI", 5))

    def _draw_simple_block(self, label: str, size_text: str, pct: float,
                           x: float, y: float, w: float, h: float,
                           hue: int) -> None:
        fill = _hsl_to_hex(hue, 0.45, 0.32)
        outline = _hsl_to_hex(hue, 0.30, 0.42)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill=fill, outline=outline, width=1)

        pad = 5
        if w > 100 and h > 50:
            max_c = max(4, int((w - pad * 2) / 8))
            disp = (label if len(label) <= max_c
                    else label[:max_c - 1] + "\u2026")
            self.canvas.create_text(
                x + pad, y + pad, anchor="nw", text=disp,
                fill="#f0f0f0", font=("Segoe UI", 8, "bold"))
            self.canvas.create_text(
                x + pad, y + pad + 22, anchor="nw",
                text=f"{size_text} ({pct:.1f}%)",
                fill="#d0d0d0", font=("Segoe UI", 7))
        elif w > 50 and h > 22:
            max_c = max(3, int((w - 6) / 7))
            disp = (label if len(label) <= max_c
                    else label[:max_c - 1] + "\u2026")
            self.canvas.create_text(
                x + 4, y + 4, anchor="nw", text=disp,
                fill="#e0e0e0", font=("Segoe UI", 7))
        elif w > 24 and h > 14:
            max_c = max(2, int((w - 4) / 6))
            disp = (label if len(label) <= max_c
                    else label[:max_c - 1] + "\u2026")
            self.canvas.create_text(
                x + 2, y + 2, anchor="nw", text=disp,
                fill="#cccccc", font=("Segoe UI", 6))

    # ── 窗口缩放 / 工具方法 ──────────────────────────────────

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
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
    _hide_console()
    _init_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
