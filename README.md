# Green 磁盘空间可视化工具 alpha v0.0.1（Windows 7+）

本目录是 Green 磁盘空间可视化工具（alpha v0.0.1）的**完整打包目录**，所有运行所需文件都集中在此处：

- `main.py`：程序入口（Tkinter 图形界面）
- `scanner.py`：磁盘扫描逻辑
- `treemap.py`：treemap 可视化布局算法
- `models.py`：数据模型定义（`FileInfo`、`DiskStats`、`ScanOptions`、`ScanResult` 等）
- `requirements.txt`：依赖说明（当前版本仅使用 Python 标准库）

## 一、运行环境

- **操作系统**：Windows 7 及以上
- **Python**：推荐 3.8 或 3.9（兼容 Windows 7）

## 二、一键运行方式（推荐）

在资源管理器中打开本目录（`C:\Users\QQZZG\GreenDisk_alpha_v0.0.1`），双击：

- `run_green_disk.bat`

即可启动 Green 磁盘空间可视化工具。

## 三、命令行运行方式

也可以使用命令行手动启动：

```bash
cd C:\Users\QQZZG\GreenDisk_alpha_v0.0.1
python main.py
```

如果你的系统使用 `py` 启动器：

```bash
cd C:\Users\QQZZG\GreenDisk_alpha_v0.0.1
py main.py
```

## 四、主要功能概览

- **磁盘扫描**
  - 支持列出本机所有可用盘符（如 `C:`、`D:`）。
  - 提供 **快速扫描** 和 **完整扫描** 两种模式：
    - 快速扫描：限制扫描深度为 4 层，并自动排除典型系统/临时目录（`$Recycle.Bin`、`System Volume Information`、`Windows\\Temp` 等），兼顾速度与效果。
    - 完整扫描：不限制深度，仅跳过极少数系统目录，尽可能覆盖整个磁盘。
  - 显示扫描进度百分比、已扫描文件/目录数量，并估算剩余时间。

- **可视化展示**
  - 使用 treemap 将顶级目录（或根级子目录）按占用空间大小渲染为矩形色块。
  - 颜色使用柔和配色方案，避免过于刺眼。
  - 提示文本展示扫描耗时、文件/目录数量以及磁盘总容量、已用、可用空间。
  - 调整窗口大小时，可视化区域会自动重绘，适配新尺寸。

## 五、注意事项

- 本版本为 **alpha v0.0.1**，功能以演示和验证为主。
- 由于采用 Python + 标准库扫描，**完整扫描大容量磁盘可能耗时较长**，建议优先使用“快速扫描”了解整体空间分布。
- 本工具**不会自动删除文件**，所有清理操作请使用系统资源管理器手动完成，以避免误删重要数据。

