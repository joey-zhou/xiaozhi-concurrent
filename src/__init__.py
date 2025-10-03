"""
Xiaozhi WebSocket 并发测试工具

用于测试 Xiaozhi WebSocket 服务的并发测试工具，支持：
- WebSocket 并发测试（连接、握手响应、音频发送、语音识别、响应时延、帧率）
- 进度条显示和实时状态
- 性能报告和可视化图表
"""

from .client import XiaozhiTestClient
from .tester import XiaozhiConcurrentTester
from .metrics import TestMetrics
from .progress import ProgressTracker

__version__ = '2.0.0'
__all__ = [
    'XiaozhiTestClient',
    'XiaozhiConcurrentTester',
    'TestMetrics',
    'ProgressTracker',
]

