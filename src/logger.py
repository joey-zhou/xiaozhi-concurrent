"""
日志配置和工具函数
"""
import logging
import os
from datetime import datetime
from .config import LOG_DIR, timestamp

# 根日志不落盘，防止生成冗余日志文件
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s', 
    handlers=[]
)

# 创建专门的调试日志记录器
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False  # 不传播到父logger，避免重复输出
debug_handler = logging.FileHandler(
    os.path.join(LOG_DIR, f'xiaozhi_debug_{timestamp}.log'), 
    mode='w', 
    encoding='utf-8'
)
debug_handler.setFormatter(logging.Formatter('%(asctime)s - DEBUG - %(message)s'))
debug_logger.addHandler(debug_handler)

# 客户端流程日志记录器
client_flow_logger = logging.getLogger('client_flow')
client_flow_logger.setLevel(logging.INFO)
client_flow_logger.propagate = False  # 不传播到父logger
client_flow_handler = logging.FileHandler(
    os.path.join(LOG_DIR, f'xiaozhi_client_flow_{timestamp}.log'), 
    mode='w', 
    encoding='utf-8'
)
client_flow_handler.setFormatter(logging.Formatter('%(message)s'))
client_flow_logger.addHandler(client_flow_handler)

# 主日志记录器
logger = logging.getLogger(__name__)


def log_debug(message: str, client_id: str = ""):
    """记录调试信息到日志文件（不在控制台显示）"""
    if client_id:
        full_message = f"[{client_id}] {message}"
    else:
        full_message = message

    # 只记录到调试日志文件，不输出到控制台
    # 清理表情符号前缀
    clean_message = (full_message
        .replace('🎵 DEBUG:', '')
        .replace('🔇 DEBUG:', '')
        .replace('🎯 DEBUG:', '')
        .replace('🚀 DEBUG:', '')
        .replace('🔴 DEBUG:', '')
        .replace('📨 DEBUG:', '')
        .replace('📊 DEBUG:', '')
        .strip()
    )
    debug_logger.debug(clean_message)


def log_client_flow(message: str, client_id: str, stage: str = ""):
    """记录客户端流程日志，按设备ID分组"""
    timestamp_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # 精确到毫秒
    if stage:
        full_message = f"[{timestamp_str}] [{client_id}] [{stage}] {message}"
    else:
        full_message = f"[{timestamp_str}] [{client_id}] {message}"
    
    # 记录到客户端流程日志文件
    client_flow_logger.info(full_message)

