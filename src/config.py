"""
配置和常量
"""
import os
from datetime import datetime

# 时间戳
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# 日志目录
LOG_DIR = os.path.join(os.getcwd(), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 检查可选依赖
try:
    import opuslib
    HAS_OPUS = True
except ImportError:
    HAS_OPUS = False
    print("警告: opuslib未安装，将使用模拟音频数据")

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("警告: matplotlib未安装，将跳过可视化功能")

# WebSocket 配置
DEFAULT_SERVER_URL = "ws://localhost:8091/ws/xiaozhi/v1/"
DEFAULT_CLIENTS = 20
DEFAULT_CONCURRENCY = 20

# 音频配置
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FRAME_DURATION_MS = 60  # 60ms per frame
AUDIO_FRAME_SIZE = int(AUDIO_SAMPLE_RATE * AUDIO_FRAME_DURATION_MS / 1000)

