#!/usr/bin/env python3
"""
Xiaozhi WebSocket 并发测试工具 - 主入口

命令行入口，用于启动测试
"""
import argparse
import os
import sys

from src import XiaozhiConcurrentTester
from src.config import (
    DEFAULT_SERVER_URL,
    DEFAULT_CLIENTS,
    DEFAULT_CONCURRENCY
)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Xiaozhi WebSocket 并发测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认参数运行测试
  python run_test.py
  
  # 自定义参数
  python run_test.py --server ws://localhost:8091/ws/xiaozhi/v1/ --clients 200 --concurrency 40
  
  # 使用自定义音频文件
  python run_test.py --audio test_audio.wav --clients 50
        """
    )
    
    parser.add_argument(
        "--server", 
        default=DEFAULT_SERVER_URL,
        help=f"WebSocket服务器地址 (默认: {DEFAULT_SERVER_URL})"
    )
    parser.add_argument(
        "--clients", 
        type=int, 
        default=DEFAULT_CLIENTS,
        help=f"总客户端数量 (默认: {DEFAULT_CLIENTS})"
    )
    parser.add_argument(
        "--concurrency", 
        type=int, 
        default=DEFAULT_CONCURRENCY,
        help=f"并发数量 (默认: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "--audio", 
        help="测试音频文件路径 (可选，不指定则自动生成)"
    )

    args = parser.parse_args()

    # 检查conda环境
    if 'CONDA_DEFAULT_ENV' in os.environ:
        print(f"✓ 检测到conda环境: {os.environ['CONDA_DEFAULT_ENV']}")
    else:
        print("⚠ 未检测到conda环境，使用系统Python")

    # 如果指定了音频文件，检查是否存在
    if args.audio and not os.path.exists(args.audio):
        print(f"❌ 错误: 音频文件不存在: {args.audio}")
        sys.exit(1)

    # 创建测试器并运行
    tester = XiaozhiConcurrentTester(
        server_url=args.server,
        concurrency=args.concurrency,
        test_audio_path=args.audio
    )
    
    tester.run_full_test(args.clients)


if __name__ == "__main__":
    main()

