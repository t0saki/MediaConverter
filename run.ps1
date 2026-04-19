# 推荐：使用数组传递参数，避免引号和空格解析的深坑
$uvArgs = @(
    "run",                          # 核心修正：使用 run 而不是 python
    "main.py",
    "E:\Temp\Xiaxin",
    "E:\Temp\Xiain-out",
    "--quality", "25",
    "--max-image-resolution", "4032*3024",
    "--max-video-resolution", "1920*1080",
    "--max-framerate", "60",
    "--max-workers", "2",
    "--log-file", "conversion.log"
)

# 启动进程
Start-Process uv -ArgumentList $uvArgs -NoNewWindow -PassThru | 
    ForEach-Object { $_.PriorityClass = "BelowNormal" }