from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


def _datetime_to_iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _iso_to_datetime(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@dataclass
class FileInfo:
    """与文档中 FileInfo 模型对应的数据结构。"""

    path: str
    name: str
    size: int
    create_time: datetime
    modify_time: datetime
    access_time: datetime
    file_type: str
    is_directory: bool
    permissions: str
    owner: str
    hash: Optional[str] = None
    risk_level: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "create_time": _datetime_to_iso(self.create_time),
            "modify_time": _datetime_to_iso(self.modify_time),
            "access_time": _datetime_to_iso(self.access_time),
            "file_type": self.file_type,
            "is_directory": self.is_directory,
            "permissions": self.permissions,
            "owner": self.owner,
            "hash": self.hash,
            "risk_level": self.risk_level,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileInfo":
        return cls(
            path=d.get("path", ""),
            name=d.get("name", ""),
            size=int(d.get("size", 0)),
            create_time=_iso_to_datetime(d.get("create_time")) or datetime.min,
            modify_time=_iso_to_datetime(d.get("modify_time")) or datetime.min,
            access_time=_iso_to_datetime(d.get("access_time")) or datetime.min,
            file_type=d.get("file_type", ""),
            is_directory=bool(d.get("is_directory", False)),
            permissions=d.get("permissions", ""),
            owner=d.get("owner", ""),
            hash=d.get("hash"),
            risk_level=int(d.get("risk_level", 0)),
        )


@dataclass
class DiskStats:
    """与文档中 DiskStats 模型对应的数据结构。"""

    disk_path: str
    total_size: int
    used_size: int
    free_size: int
    file_count: int
    folder_count: int
    largest_file: Optional[FileInfo]
    file_type_stats: Dict[str, Dict[str, int]]
    scan_time: datetime
    last_modified: datetime

    def to_dict(self) -> dict:
        return {
            "disk_path": self.disk_path,
            "total_size": self.total_size,
            "used_size": self.used_size,
            "free_size": self.free_size,
            "file_count": self.file_count,
            "folder_count": self.folder_count,
            "largest_file": self.largest_file.to_dict() if self.largest_file else None,
            "file_type_stats": self.file_type_stats,
            "scan_time": _datetime_to_iso(self.scan_time),
            "last_modified": _datetime_to_iso(self.last_modified),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DiskStats":
        lf = d.get("largest_file")
        return cls(
            disk_path=d.get("disk_path", ""),
            total_size=int(d.get("total_size", 0)),
            used_size=int(d.get("used_size", 0)),
            free_size=int(d.get("free_size", 0)),
            file_count=int(d.get("file_count", 0)),
            folder_count=int(d.get("folder_count", 0)),
            largest_file=FileInfo.from_dict(lf) if lf else None,
            file_type_stats=d.get("file_type_stats") or {},
            scan_time=_iso_to_datetime(d.get("scan_time")) or datetime.min,
            last_modified=_iso_to_datetime(d.get("last_modified")) or datetime.min,
        )


@dataclass
class ScanOptions:
    """与文档 ScanOptions 对应的本地扫描选项。"""

    path: str
    recursive: bool = True
    follow_symlinks: bool = False
    calculate_hash: bool = False
    exclude_patterns: List[str] = field(default_factory=list)
    max_depth: Optional[int] = None
    collect_file_details: bool = True


@dataclass
class ScanResult:
    """与文档 ScanResult 对应的扫描结果。"""

    files: List[FileInfo]
    stats: DiskStats
    scan_duration_ms: int
    error_count: int
    hierarchy: Dict[str, Dict] = field(default_factory=dict)
    scan_method: str = "scandir"

    def to_gfav_dict(self) -> dict:
        """用于 .gfav 导出的可序列化字典（仅 hierarchy、stats、scan_method）。"""
        return {
            "hierarchy": self.hierarchy,
            "stats": self.stats.to_dict(),
            "scan_method": self.scan_method,
        }

    @classmethod
    def from_gfav_dict(cls, d: dict) -> "ScanResult":
        """从 .gfav 解析的字典恢复（仅用于展示，files/scan_duration_ms/error_count 为占位）。"""
        return cls(
            files=[],
            stats=DiskStats.from_dict(d.get("stats") or {}),
            scan_duration_ms=0,
            error_count=0,
            hierarchy=d.get("hierarchy") or {},
            scan_method=d.get("scan_method", "scandir"),
        )

