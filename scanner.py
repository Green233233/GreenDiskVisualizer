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
    为兼容 Windows 7，仅使用标准库，不做 MFT 级优化。
    """
    start_ts = time.time()
    files: List[FileInfo] = []
    error_count = 0

    # 统计用
    file_type_stats = {}
    file_count = 0
    folder_count = 0
    largest_file: FileInfo | None = None
    scanned_size = 0

    # 磁盘容量信息（使用标准库）
    try:
        total_size, used_size, free_size = shutil.disk_usage(options.path)
        total_size = int(total_size)
        used_size = int(used_size)
        free_size = int(free_size)
    except Exception:
        # 回退：如果无法获取，使用 0
        total_size = used_size = free_size = 0

    root_depth = options.path.rstrip("\\/").count(os.sep)

    for dirpath, dirnames, filenames in os.walk(options.path, followlinks=options.follow_symlinks):
        # 深度限制
        if options.max_depth is not None:
            current_depth = dirpath.rstrip("\\/").count(os.sep) - root_depth
            if current_depth > options.max_depth:
                dirnames[:] = []
                continue

        # 目录排除
        dirnames[:] = [d for d in dirnames if not _match_exclude(os.path.join(dirpath, d), options.exclude_patterns)]

        # 统计目录
        for d in dirnames:
            folder_count += 1

        # 处理文件
        for name in filenames:
            full_path = os.path.join(dirpath, name)
            if _match_exclude(full_path, options.exclude_patterns):
                continue
            try:
                st = os.stat(full_path, follow_symlinks=options.follow_symlinks)
            except Exception:
                error_count += 1
                continue

            is_dir = stat.S_ISDIR(st.st_mode)
            size = int(st.st_size)
            create_time = datetime.fromtimestamp(st.st_ctime)
            modify_time = datetime.fromtimestamp(st.st_mtime)
            access_time = datetime.fromtimestamp(st.st_atime)

            ext = os.path.splitext(name)[1].lower() or "unknown"
            permissions = stat.filemode(st.st_mode)
            owner = str(st.st_uid) if hasattr(st, "st_uid") else "unknown"

            fi = FileInfo(
                path=full_path,
                name=name,
                size=size,
                create_time=create_time,
                modify_time=modify_time,
                access_time=access_time,
                file_type=ext,
                is_directory=is_dir,
                permissions=permissions,
                owner=owner,
            )
            files.append(fi)
            file_count += 1
            scanned_size += size

            # 最大文件
            if not is_dir and (largest_file is None or fi.size > largest_file.size):
                largest_file = fi

            # 文件类型统计
            stat_entry = file_type_stats.setdefault(
                ext,
                {"total_size": 0, "file_count": 0},
            )
            stat_entry["total_size"] += size
            stat_entry["file_count"] += 1

        # 每处理完一个目录，更新一次进度
        if progress_callback is not None:
            ratio = 0.0
            if total_size > 0 and scanned_size > 0:
                ratio = min(0.999, scanned_size / total_size)
            progress_callback(file_count, folder_count, dirpath, ratio)

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

    # 结束时再推送一次 100% 进度
    if progress_callback is not None:
        progress_callback(file_count, folder_count, options.path, 1.0)

    return result

