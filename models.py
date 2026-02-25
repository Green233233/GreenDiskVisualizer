from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


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

