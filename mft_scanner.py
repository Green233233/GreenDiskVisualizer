"""MFT-accelerated scanner for NTFS volumes.

Uses FSCTL_ENUM_USN_DATA to enumerate all file system entries from the
Master File Table in batched reads, then resolves file sizes via a
BFS-ordered os.scandir pass on each known directory.

Requires administrator privileges and only works on NTFS volumes.
Falls back gracefully when unavailable.
"""

import ctypes
import ctypes.wintypes as wt
import gc
import os
import stat
import struct
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Callable, Tuple

from models import FileInfo

# ── Windows API constants ────────────────────────────────────────

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400

FSCTL_ENUM_USN_DATA = 0x000900B3
FSCTL_GET_NTFS_VOLUME_DATA = 0x00090064

_kernel32 = ctypes.windll.kernel32
_INVALID_HANDLE = ctypes.c_void_p(-1).value


# ── ctypes structures ────────────────────────────────────────────

class _NTFS_VOLUME_DATA(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_int64),
        ("NumberSectors", ctypes.c_int64),
        ("TotalClusters", ctypes.c_int64),
        ("FreeClusters", ctypes.c_int64),
        ("TotalReserved", ctypes.c_int64),
        ("BytesPerSector", ctypes.c_ulong),
        ("BytesPerCluster", ctypes.c_ulong),
        ("BytesPerFileRecordSegment", ctypes.c_ulong),
        ("ClustersPerFileRecordSegment", ctypes.c_ulong),
        ("MftValidDataLength", ctypes.c_int64),
        ("MftStartLcn", ctypes.c_int64),
        ("Mft2StartLcn", ctypes.c_int64),
        ("MftZoneStart", ctypes.c_int64),
        ("MftZoneEnd", ctypes.c_int64),
    ]


class _MFT_ENUM_DATA_V0(ctypes.Structure):
    _fields_ = [
        ("StartFileReferenceNumber", ctypes.c_uint64),
        ("LowUsn", ctypes.c_int64),
        ("HighUsn", ctypes.c_int64),
    ]


# ── Low-level helpers ────────────────────────────────────────────

def _open_volume(drive_letter: str):
    """Open a volume handle for the given drive letter (e.g. 'C')."""
    volume = f"\\\\.\\{drive_letter}:"
    handle = _kernel32.CreateFileW(
        volume, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None,
    )
    if handle == _INVALID_HANDLE:
        return None
    return handle


def _close_handle(handle) -> None:
    if handle is not None and handle != _INVALID_HANDLE:
        _kernel32.CloseHandle(handle)


def _is_ntfs_volume(handle) -> bool:
    """Check if the volume is NTFS by querying NTFS volume data."""
    vol_data = _NTFS_VOLUME_DATA()
    br = ctypes.c_ulong(0)
    ok = _kernel32.DeviceIoControl(
        handle, FSCTL_GET_NTFS_VOLUME_DATA,
        None, 0,
        ctypes.byref(vol_data), ctypes.sizeof(vol_data),
        ctypes.byref(br), None,
    )
    return bool(ok)


# ── Public API ───────────────────────────────────────────────────

def can_use_mft(path: str) -> bool:
    """Return True if MFT scanning is available for *path*."""
    if os.name != "nt":
        return False
    drive = os.path.splitdrive(path)[0].rstrip(":")
    if not drive:
        return False
    handle = _open_volume(drive)
    if handle is None:
        return False
    ok = _is_ntfs_volume(handle)
    _close_handle(handle)
    return ok


_REF_MASK = 0x0000FFFFFFFFFFFF
_NTFS_ROOT_REF = 5


def _enumerate_mft_entries(
    handle,
    progress_callback: Optional[Callable] = None,
) -> Dict[int, Tuple[int, str]]:
    """Enumerate directory entries from MFT via FSCTL_ENUM_USN_DATA.

    Returns {dir_ref: (parent_ref, name)} for directories only (saves memory).
    Calls *progress_callback* periodically during enumeration so the UI
    stays responsive and can display status updates.
    """
    enum_data = _MFT_ENUM_DATA_V0()
    enum_data.StartFileReferenceNumber = 0
    enum_data.LowUsn = 0
    enum_data.HighUsn = 0x7FFFFFFFFFFFFFFF

    buf_size = 65536
    buf = ctypes.create_string_buffer(buf_size)
    br = ctypes.c_ulong(0)

    entries: Dict[int, Tuple[int, str]] = {}
    batch_count = 0

    while True:
        ok = _kernel32.DeviceIoControl(
            handle, FSCTL_ENUM_USN_DATA,
            ctypes.byref(enum_data), ctypes.sizeof(enum_data),
            buf, buf_size,
            ctypes.byref(br), None,
        )
        if not ok:
            break

        returned = br.value
        if returned <= 8:
            break

        next_ref = struct.unpack_from("<Q", buf.raw, 0)[0]
        offset = 8

        while offset + 60 <= returned:
            rec_len = struct.unpack_from("<I", buf.raw, offset)[0]
            if rec_len == 0 or offset + rec_len > returned:
                break

            file_ref = struct.unpack_from("<Q", buf.raw, offset + 8)[0] & _REF_MASK
            parent_ref = struct.unpack_from("<Q", buf.raw, offset + 16)[0] & _REF_MASK
            file_attrs = struct.unpack_from("<I", buf.raw, offset + 52)[0]
            name_len = struct.unpack_from("<H", buf.raw, offset + 56)[0]
            name_off = struct.unpack_from("<H", buf.raw, offset + 58)[0]

            name_start = offset + name_off
            name_end = name_start + name_len
            if name_end <= returned and name_len > 0:
                name = buf.raw[name_start:name_end].decode(
                    "utf-16-le", errors="replace")
                is_dir = bool(file_attrs & FILE_ATTRIBUTE_DIRECTORY)
                is_reparse = bool(file_attrs & FILE_ATTRIBUTE_REPARSE_POINT)
                if not is_reparse and is_dir:
                    entries[file_ref] = (parent_ref, sys.intern(name))

            offset += rec_len

        enum_data.StartFileReferenceNumber = next_ref

        batch_count += 1
        if progress_callback and batch_count % 8 == 0:
            progress_callback(
                0, 0,
                f"正在读取MFT文件表... ({len(entries)} 个目录)",
                0.01)

    return entries


def _build_dir_paths_compact(
    entries: Dict[int, Tuple[int, str]],
    root_path: str,
) -> Tuple[Dict[int, Tuple[int, str]], str]:
    """BFS from NTFS root, return compact (parent_ref, name) per dir, no full paths."""
    children_of: Dict[int, List[Tuple[int, str]]] = defaultdict(list)
    for ref, (parent_ref, name) in entries.items():
        children_of[parent_ref].append((ref, name))

    root_path = root_path.rstrip("\\/")
    compact: Dict[int, Tuple[int, str]] = {}
    queue: List[Tuple[int, int, str]] = [(_NTFS_ROOT_REF, _NTFS_ROOT_REF, "")]

    while queue:
        ref, parent_ref, name = queue.pop(0)
        if ref != _NTFS_ROOT_REF:
            compact[ref] = (parent_ref, sys.intern(name))
        for child_ref, child_name in children_of.get(ref, []):
            if child_name.startswith("$"):
                continue
            queue.append((child_ref, ref, sys.intern(child_name)))

    return compact, root_path


def _get_dir_full_path(
    ref: int,
    compact: Dict[int, Tuple[int, str]],
    root_path: str,
) -> str:
    """Resolve full path from compact (parent_ref, name) map. O(depth) per call."""
    if ref == _NTFS_ROOT_REF:
        return root_path
    parts: List[str] = []
    r = ref
    while r in compact:
        parent_ref, name = compact[r]
        parts.append(name)
        r = parent_ref
    parts.reverse()
    return root_path + "\\" + "\\".join(parts)


def _match_exclude(path: str, patterns: List[str]) -> bool:
    lower = path.lower()
    for p in patterns:
        p = p.strip()
        if p and p.lower() in lower:
            return True
    return False


def _add_size_to_hierarchy(
    hierarchy: dict, rel_path: str, size: int,
) -> None:
    """Insert a file's size into the N-level recursive hierarchy."""
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


def scan_mft(
    path: str,
    exclude_patterns: List[str],
    progress_callback: Optional[Callable] = None,
    shared_hierarchy: Optional[dict] = None,
) -> Tuple[dict, int, int, int, dict, int, Optional[FileInfo]]:
    """Scan a volume using MFT enumeration + BFS scandir.

    Returns (hierarchy, file_count, folder_count, error_count,
             file_type_stats, scanned_size, largest_file).
    """
    drive = os.path.splitdrive(path)[0].rstrip(":")
    handle = _open_volume(drive)
    if handle is None:
        raise OSError(f"Cannot open volume {drive}:")

    hierarchy = shared_hierarchy if shared_hierarchy is not None else {}
    file_count = 0
    folder_count = 0
    error_count = 0
    file_type_stats: dict = {}
    scanned_size = 0
    largest_file: Optional[FileInfo] = None

    try:
        if progress_callback:
            progress_callback(0, 0, "正在读取MFT文件表...", 0.0)

        entries = _enumerate_mft_entries(handle, progress_callback)

        if progress_callback:
            progress_callback(
                0, 0,
                f"正在构建目录结构... ({len(entries)} 个目录)",
                0.02)

        dir_compact, root_path = _build_dir_paths_compact(entries, path)
        del entries
        gc.collect()
        folder_count = len(dir_compact)
        total_dirs = max(folder_count + 1, 1)
        processed_dirs = 0
        root_len = len(root_path)

        if progress_callback:
            progress_callback(
                0, folder_count,
                f"开始扫描文件大小... ({folder_count} 个目录)",
                0.03)

        all_dir_refs = [_NTFS_ROOT_REF] + list(dir_compact.keys())
        for dir_ref in all_dir_refs:
            dir_path = _get_dir_full_path(dir_ref, dir_compact, root_path)
            if _match_exclude(dir_path, exclude_patterns):
                processed_dirs += 1
                continue

            try:
                with os.scandir(dir_path) as it:
                    for entry in it:
                        try:
                            st = entry.stat(follow_symlinks=False)
                        except OSError:
                            error_count += 1
                            continue
                        if not stat.S_ISREG(st.st_mode):
                            continue

                        size = int(st.st_size)
                        name = entry.name
                        ext = os.path.splitext(name)[1].lower() or "unknown"

                        file_count += 1
                        scanned_size += size

                        te = file_type_stats.setdefault(
                            ext, {"total_size": 0, "file_count": 0})
                        te["total_size"] += size
                        te["file_count"] += 1

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
            except (PermissionError, OSError):
                error_count += 1

            processed_dirs += 1
            if progress_callback and processed_dirs % 15 == 0:
                ratio = 0.03 + 0.969 * (processed_dirs / total_dirs)
                progress_callback(
                    file_count, folder_count, dir_path, min(0.999, ratio))

    finally:
        _close_handle(handle)

    return (hierarchy, file_count, folder_count, error_count,
            file_type_stats, scanned_size, largest_file)
