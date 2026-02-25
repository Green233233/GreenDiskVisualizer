import ctypes
import os
import platform
import shutil
import stat
import time
from datetime import datetime
from typing import List, Tuple, Callable, Optional, Dict

from models import FileInfo, DiskStats, ScanOptions, ScanResult


def list_disks() -> List[Tuple[str, str]]:
    """
    列出系统中可用磁盘。

    返回 (device, mountpoint) 列表，例如 ('C:', 'C:\\').
    Windows 上使用 GetLogicalDrives() 位掩码 API，无需逐一探测，
    避免网络盘/光驱等慢设备导致 UI 阻塞。
    """
    if platform.system() == "Windows":
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            result: List[Tuple[str, str]] = []
            for i in range(26):
                if bitmask & (1 << i):
                    drive = chr(ord("A") + i) + ":"
                    result.append((drive, drive + "\\"))
            if result:
                return result
        except Exception:
            pass
    disks: List[Tuple[str, str]] = []
    for code in range(ord("A"), ord("Z") + 1):
        drive = chr(code) + ":"
        mount = drive + "\\"
        if os.path.exists(mount):
            disks.append((drive, mount))
    return disks


def _match_exclude(path: str, patterns: List[str]) -> bool:
    """简单的排除规则匹配：只按子串/文件夹名匹配，避免引入额外依赖。"""
    lower = path.lower()
    for p in patterns:
        p = p.strip()
        if not p:
            continue
        if p.lower() in lower:
            return True
    return False


_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT


def _is_junction_or_symlink(entry) -> bool:
    """判断 scandir 条目是否为 NTFS 联接点或目录符号链接。

    先检查 FILE_ATTRIBUTE_REPARSE_POINT（scandir 缓存，零开销），
    再用 os.readlink 确认是联接/符号链接而非 OneDrive 云占位符等。
    """
    try:
        attrs = getattr(entry.stat(follow_symlinks=False),
                        'st_file_attributes', 0)
        if not (attrs & _REPARSE_POINT):
            return False
    except OSError:
        return False
    try:
        os.readlink(entry.path)
        return True
    except (OSError, ValueError):
        return False


# ── on-disk size helper (Windows) ─────────────────────────────────

def _get_on_disk_size(path: str, logical_size: int) -> int:
    """Return the approximate size occupied on disk.

    On Windows/NTFS this uses GetCompressedFileSizeW to read the
    allocated (possibly compressed/sparse) size; on other platforms
    it falls back to the logical file size.
    """
    if platform.system() != "Windows":
        return logical_size
    try:
        GetCompressedFileSizeW = ctypes.windll.kernel32.GetCompressedFileSizeW
        GetCompressedFileSizeW.restype = ctypes.c_ulong
        GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p,
                                           ctypes.POINTER(ctypes.c_ulong)]
        high = ctypes.c_ulong(0)
        low = GetCompressedFileSizeW(path, ctypes.byref(high))
        size = (high.value << 32) | low
        # If the call fails, fall back to logical size.
        if low == 0xFFFFFFFF and high.value == 0xFFFFFFFF:
            return logical_size
        return int(size)
    except Exception:
        return logical_size


# ── N-level hierarchy helpers ────────────────────────────────────

def _add_size_to_hierarchy(
    hierarchy: dict, rel_path: str, size: int,
) -> None:
    """Insert a file's size into the N-level recursive hierarchy.

    Each node is ``{"total": int, "children": {name: node, ...}}``.
    Directory components along *rel_path* get *size* added to their
    ``total``; the filename itself (last component) is NOT inserted
    as a node.
    """
    parts = rel_path.replace("/", "\\").split("\\")
    if len(parts) <= 1:
        entry = hierarchy.setdefault(parts[0], {"total": 0, "children": {}})
        entry["total"] += size
    else:
        node = hierarchy
        for part in parts[:-1]:
            child = node.setdefault(part, {"total": 0, "children": {}})
            child["total"] += size
            node = child["children"]


# ── MFT detection ────────────────────────────────────────────────

def _can_use_mft(path: str) -> bool:
    """Return True if MFT-accelerated scanning is available."""
    if platform.system() != "Windows":
        return False
    try:
        from mft_scanner import can_use_mft
        return can_use_mft(path)
    except Exception:
        return False


# ── scandir-based scanner (fallback) ─────────────────────────────

def _scan_via_scandir(
    options: ScanOptions,
    progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
    shared_hierarchy: Optional[dict] = None,
) -> ScanResult:
    """Scan using os.scandir with N-level hierarchy aggregation."""
    start_ts = time.time()
    error_count = 0
    file_type_stats: dict = {}
    file_count = 0
    folder_count = 0
    largest_file: FileInfo | None = None
    scanned_size = 0

    try:
        disk_usage = shutil.disk_usage(options.path)
        total_size = int(disk_usage[0])
        used_size = int(disk_usage[1])
        free_size = int(disk_usage[2])
    except Exception:
        total_size = used_size = free_size = 0

    root_path = options.path.rstrip("\\/")
    root_len = len(root_path)
    root_sep_count = root_path.count(os.sep)

    hierarchy = shared_hierarchy if shared_hierarchy is not None else {}

    stack = [options.path]

    while stack:
        current_dir = stack.pop()

        if options.max_depth is not None:
            depth = current_dir.rstrip("\\/").count(os.sep) - root_sep_count
            if depth > options.max_depth:
                continue

        try:
            it = os.scandir(current_dir)
        except (PermissionError, OSError):
            error_count += 1
            continue

        subdirs: List[str] = []

        with it:
            for entry in it:
                try:
                    is_dir = entry.is_dir(follow_symlinks=options.follow_symlinks)
                except OSError:
                    error_count += 1
                    continue

                if is_dir:
                    if not _match_exclude(entry.path, options.exclude_patterns):
                        if (not options.follow_symlinks
                                and _is_junction_or_symlink(entry)):
                            continue
                        folder_count += 1
                        subdirs.append(entry.path)
                    continue

                if _match_exclude(entry.path, options.exclude_patterns):
                    continue

                try:
                    st = entry.stat(follow_symlinks=options.follow_symlinks)
                except (PermissionError, OSError):
                    error_count += 1
                    continue

                if stat.S_ISDIR(st.st_mode):
                    continue

                logical_size = int(st.st_size)
                # 非 MFT 模式下使用逻辑大小，保证与资源管理器“大小”一致、避免失准
                size = logical_size
                name = entry.name
                ext = os.path.splitext(name)[1].lower() or "unknown"

                file_count += 1
                scanned_size += size

                type_entry = file_type_stats.setdefault(
                    ext, {"total_size": 0, "file_count": 0})
                type_entry["total_size"] += size
                type_entry["file_count"] += 1

                rel = entry.path[root_len:].lstrip("\\/")
                if rel:
                    _add_size_to_hierarchy(hierarchy, rel, size)

                if largest_file is None or size > largest_file.size:
                    largest_file = FileInfo(
                        path=entry.path, name=name, size=size,
                        create_time=datetime.fromtimestamp(st.st_ctime),
                        modify_time=datetime.fromtimestamp(st.st_mtime),
                        access_time=datetime.fromtimestamp(st.st_atime),
                        file_type=ext, is_directory=False,
                        permissions="", owner="",
                    )

        stack.extend(subdirs)

        if progress_callback is not None:
            ratio = 0.0
            if total_size > 0 and scanned_size > 0:
                ratio = min(0.999, scanned_size / total_size)
            progress_callback(file_count, folder_count, current_dir, ratio)

    end_ts = time.time()
    scan_time = datetime.now()

    stats = DiskStats(
        disk_path=options.path,
        total_size=total_size,
        used_size=used_size,
        free_size=free_size,
        file_count=file_count,
        folder_count=folder_count,
        largest_file=largest_file,
        file_type_stats=file_type_stats,
        scan_time=scan_time,
        last_modified=scan_time,
    )

    result = ScanResult(
        files=[],
        stats=stats,
        scan_duration_ms=int((end_ts - start_ts) * 1000),
        error_count=error_count,
        hierarchy=hierarchy,
        scan_method="scandir",
    )

    if progress_callback is not None:
        progress_callback(file_count, folder_count, options.path, 1.0)

    return result


# ── MFT-based scanner ────────────────────────────────────────────

def _scan_via_mft(
    options: ScanOptions,
    progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
    shared_hierarchy: Optional[dict] = None,
) -> ScanResult:
    """Scan using MFT enumeration (NTFS, admin required)."""
    from mft_scanner import scan_mft

    start_ts = time.time()

    try:
        disk_usage = shutil.disk_usage(options.path)
        total_size = int(disk_usage[0])
        used_size = int(disk_usage[1])
        free_size = int(disk_usage[2])
    except Exception:
        total_size = used_size = free_size = 0

    hierarchy = shared_hierarchy if shared_hierarchy is not None else {}

    (hierarchy, file_count, folder_count, error_count,
     file_type_stats, scanned_size, largest_file) = scan_mft(
        options.path,
        options.exclude_patterns,
        progress_callback=progress_callback,
        shared_hierarchy=hierarchy,
    )

    end_ts = time.time()
    scan_time = datetime.now()

    stats = DiskStats(
        disk_path=options.path,
        total_size=total_size,
        used_size=used_size,
        free_size=free_size,
        file_count=file_count,
        folder_count=folder_count,
        largest_file=largest_file,
        file_type_stats=file_type_stats,
        scan_time=scan_time,
        last_modified=scan_time,
    )

    result = ScanResult(
        files=[],
        stats=stats,
        scan_duration_ms=int((end_ts - start_ts) * 1000),
        error_count=error_count,
        hierarchy=hierarchy,
        scan_method="mft",
    )

    if progress_callback is not None:
        progress_callback(file_count, folder_count, options.path, 1.0)

    return result


# ── Public dispatcher ────────────────────────────────────────────

def scan_path(
    options: ScanOptions,
    progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
    shared_hierarchy: Optional[dict] = None,
) -> ScanResult:
    """Scan *options.path*, auto-selecting MFT or scandir backend.

    If *shared_hierarchy* is provided the scanner writes into it
    in-place so that the UI thread can read partial results for
    progressive rendering.
    """
    if _can_use_mft(options.path):
        try:
            return _scan_via_mft(
                options, progress_callback, shared_hierarchy)
        except Exception:
            pass
    return _scan_via_scandir(
        options, progress_callback, shared_hierarchy)
