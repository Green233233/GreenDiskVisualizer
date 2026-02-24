# Green Disk Visualizer
一款使用Python构建的磁盘空间可视化软件，旨在将磁盘内各文件夹所占空间以直观的方式展示出来，帮助使用者更好地了解磁盘空间的使用情况。
<img width="1643" height="1345" alt="image" src="https://github.com/user-attachments/assets/bde269f8-9c48-4efd-b4b6-877827bd24a6" />


## 一、目录结构
`main.py`：程序入口  
`scanner.py`：磁盘扫描主文件  
`treemap.py`：treemap 文件大小可视化算法文件  
`models.py`：数据模型定义文件  
`requirements.txt`：依赖说明  
`run_visualizer.bat`：一键运行批处理文件  


## 二、运行环境

**操作系统**：实测Win端支持Windows7及以上平台，未针对Linux和macOS适配。  

**Python**：要求Python3.7或以上版本  


## 三、运行方式

在Release页面中下载最新版本并解压压缩包，运行其中的批处理文件

- `run_visualizer.bat`

即可启动工具。

也可以使用命令行手动启动：

```bash
cd 文件所在目录
python main.py
```
或者：
```bash
cd 文件所在目录
py main.py
```

## 四、主要功能

**磁盘扫描**  
提供 **快速扫描** 和 **完整扫描** 两种模式：  
     - 快速扫描：限制扫描深度为 4 层，排除典型系统/临时目录。  
     - 完整扫描：不限制深度，仅跳过极少数系统目录，尽可能覆盖整个磁盘。  
显示扫描进度百分比、已扫描文件/目录数量，并估算剩余时间。  


## 五、注意事项

1.软件目前处于a测阶段，功能简陋，运行不稳定，不建议用于工作用途。  
2.目前仅采用 Python + 标准库扫描，**完整扫描大容量磁盘可能耗时较长**。  
3.本软件**无删除文件功能**，如需清理文件请自行清理。  
