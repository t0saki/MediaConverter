# 媒体转换器

[English README](README.md)

一个全面的Python工具，用于将图像和视频转换为现代格式并进行压缩，同时保留元数据。

## 功能特性

- **图像转换**: 将图像转换为AVIF格式，支持WebP回退
- **视频转换**: 将视频转换为AV1/Opus格式（MP4容器）
- **元数据保留**: 复制EXIF数据和文件时间戳
- **Apple HDR支持**: 将Apple HDR HEIC文件转换为PQ格式
- **智能调整大小**: 自动调整超过最大分辨率的媒体文件
- **并行处理**: 多线程转换，提高处理速度
- **错误处理**: 强大的错误处理机制和回退策略

## 支持格式

### 输入格式
- **图像**: PNG, JPG, JPEG, WebP, HEIC, HEIF, GIF, TIFF
- **视频**: MP4, AVI, MKV, MOV, MPG, MPEG, M4V, WebM, TS

### 输出格式
- **图像**: AVIF（主要）, WebP（回退）
- **视频**: MP4（AV1视频编码 + Opus音频编码）

## 安装

### 系统依赖

1. **安装系统依赖**:
   
   **Windows (Chocolatey)**:
   ```bash
   choco install ffmpeg exiftool imagemagick.app
   ```
   
   **macOS (Homebrew)**:
   ```bash
   brew install ffmpeg exiftool imagemagick
   ```
   
   **Debian/Ubuntu**:
   ```bash
   sudo apt update && sudo apt install ffmpeg exiftool imagemagick
   ```

2. **安装Python依赖**:
   ```bash
   pip install tqdm
   ```

## 使用方法

### 基本用法
```bash
python main.py "/源文件路径" "/目标文件路径"
```

### 高级选项
```bash
python main.py "D:\我的图片" "D:\转换后媒体" \
  --quality 60 \
  --max-resolution 1920*1080 \
  --max-workers 8 \
  --delete-original \
  --log-file 转换日志.log
```

### 命令行选项

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `source_dir` | 包含媒体文件的源目录 | 必填 |
| `target_dir` | 转换后文件的目标目录 | 必填 |
| `-q, --quality` | 图像质量 (0-100, 值越小文件越小) | 75 |
| `-r, --max-resolution` | 调整大小前的最大像素数 (宽*高) | 4032*3024 |
| `--video-args` | 视频转换的自定义FFmpeg参数 | AV1/Opus预设 |
| `--image-speed` | 图像转换速度预设 (0-10, 值越小速度越慢但质量越好) | 6 |
| `--video-speed` | 视频转换速度预设 (0-13, 值越小速度越慢但质量越好) | 4 |
| `-w, --max-workers` | 并行线程数 | 4 |
| `--delete-original` | 转换成功后删除原文件 | False |
| `--skip-existing` | 跳过目标目录中已存在的文件 | True |
| `--keep-apple-hdr` | 转换带有增益图的HEIC文件时转换为PQ格式 | False |
| `--log-file` | 日志文件路径 | conversion.log |

## 项目结构

```
media_converter/
├── main.py              # 主入口文件
├── config.py            # 配置常量
├── utils.py             # 工具函数
├── metadata_handler.py  # 元数据处理
├── image_processor.py   # 图像转换逻辑
├── video_processor.py   # 视频转换逻辑
├── processor.py         # 主协调器
└── README.md           # 说明文档
```

## 示例

### 高质量转换照片
```bash
python main.py "~/照片" "~/转换后照片" --quality 85
```

### 转换并调整大视频尺寸
```bash
python main.py "~/视频" "~/转换后视频" --max-resolution 1280*720
```

### 批量转换并使用最大并行度
```bash
python main.py "/mnt/照片" "/mnt/转换后" --max-workers 16 --delete-original
```

## 注意事项

- 工具会保持源目录到目标目录的目录结构
- 如果文件已存在于目标目录中，则会被跳过
- 元数据（EXIF、时间戳）会被复制到转换后的文件中
- 转换进度会显示进度条
- 详细日志会写入指定的日志文件
- Apple HDR支持需要启用`--keep-apple-hdr`标志

## 致谢

- Apple HDR转换功能基于Jackchou的[hdr-conversion](https://github.com/Jackchou00/hdr-conversion)

## 许可证

MIT许可证