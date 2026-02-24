import os
import shutil
import stat
import time
from datetime import datetime
from typing import List, Tuple, Callable, Optional

from models import FileInfo, DiskStats, ScanOptions, ScanResult


def list_disks() -> List[Tuple[str, str]]:
    """
    列出系统中可用磁盘。

    返回 (device, mountpoint) 列表，例如 ('C:', 'C:\\').
    使用标准库按盘符枚举，避免依赖第三方库。
    """
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


def scan_path(
    options: ScanOptions,
    progress_callback: Optional[Callable[[int, int, str, float], None]] = None,
) -> ScanResult:
    """
    基于 ScanOptions 扫描磁盘路径，返回 ScanResult。

    使用 os.scandir() 进行迭代遍历。在 Windows 上 entry.stat() 利用
    FindFirstFile/FindNextFile 缓存的元数据，无需额外 I/O，显著快于
    os.walk() + os.stat() 的组合。

    当 options.collect_file_details 为 False 时（快速扫描），不为每个文件
    创建 FileInfo，而是按一级目录聚合大小，大幅降低内存占用，同时保留
    准确的总量统计。
    """
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

    collect_details = options.collect_file_details
    files: List[FileInfo] = []
    size_by_component: dict[str, int] = {}

    # 迭代式目录遍历（栈），避免递归深度限制
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

                size = int(st.st_size)
                name = entry.name
                ext = os.path.splitext(name)[1].lower() or "unknown"

                file_count += 1
                scanned_size += size

                type_entry = file_type_stats.setdefault(
                    ext, {"total_size": 0, "file_count": 0})
                type_entry["total_size"] += size
                type_entry["file_count"] += 1

                if collect_details:
                    fi = FileInfo(
                        path=entry.path,
                        name=name,
                        size=size,
                        create_time=datetime.fromtimestamp(st.st_ctime),
                        modify_time=datetime.fromtimestamp(st.st_mtime),
                        access_time=datetime.fromtimestamp(st.st_atime),
                        file_type=ext,
                        is_directory=False,
                        permissions=stat.filemode(st.st_mode),
                        owner=str(st.st_uid) if hasattr(st, "st_uid") else "unknown",
                    )
                    files.append(fi)
                    if largest_file is None or size > largest_file.size:
                        largest_file = fi
                else:
                    rel = entry.path[root_len:].lstrip("\\/")
                    sep_pos = rel.find("\\")
                    if sep_pos < 0:
                        sep_pos = rel.find("/")
                    component = rel[:sep_pos] if sep_pos >= 0 else rel
                    size_by_component[component] = (
                        size_by_component.get(component, 0) + size)

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

    # 聚合模式：将每个一级目录的总大小封装为合成 FileInfo
    if not collect_details:
        now = datetime.now()
        for component, comp_size in sorted(
            size_by_component.items(), key=lambda x: x[1], reverse=True
        ):
            files.append(FileInfo(
                path=root_path + "\\" + component,
                name=component,
                size=comp_size,
                create_time=now, modify_time=now, access_time=now,
                file_type="directory", is_directory=True,
                permissions="", owner="",
            ))

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
        files=files,
        stats=stats,
        scan_duration_ms=int((end_ts - start_ts) * 1000),
        error_count=error_count,
    )

    if progress_callback is not None:
        progress_callback(file_count, folder_count, options.path, 1.0)

    return result
