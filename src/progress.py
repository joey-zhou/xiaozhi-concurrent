"""
进度跟踪器 - 显示测试进度条和状态
"""
import time
import threading


class ProgressTracker:
    """进度跟踪器 - 显示测试进度条"""
    
    def __init__(self, total_clients: int, concurrency: int):
        self.total_clients = total_clients
        self.concurrency = concurrency
        self.completed = 0
        self.active = 0
        self.failed = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        
        # 测试阶段统计
        self.stage_stats = {
            'connecting': 0,
            'hello': 0,
            'detect': 0,  # 唤醒词阶段
            'audio_sending': 0,
            'waiting_response': 0,
            'audio_receiving': 0,  # 音频接收中的数量
            'completed': 0,
            'failed': 0
        }
    
    def update_stage(self, stage: str, delta: int = 1):
        """更新阶段统计"""
        with self.lock:
            if stage in self.stage_stats:
                self.stage_stats[stage] += delta
    
    def increment_active(self):
        """活跃会话+1（WebSocket连接建立时）"""
        with self.lock:
            self.active += 1

    def decrement_active(self):
        """活跃会话-1（WebSocket关闭时）"""
        with self.lock:
            if self.active > 0:
                self.active -= 1

    def set_active(self, count: int):
        """设置活跃客户端数量"""
        with self.lock:
            self.active = count
    
    def increment_completed(self):
        """增加完成计数"""
        with self.lock:
            self.completed += 1
    
    def increment_failed(self):
        """增加失败计数"""
        with self.lock:
            self.failed += 1
    
    def get_progress_bar(self, width: int = 50) -> str:
        """生成进度条字符串"""
        with self.lock:
            # 确保进度不超过100%
            progress = min(self.completed / max(self.total_clients, 1), 1.0)
            filled = int(width * progress)
            bar = '█' * filled + '░' * (width - filled)
            
            elapsed = time.time() - self.start_time
            remaining = max(self.total_clients - self.completed, 0)
            
            if self.completed > 0 and remaining > 0:
                eta = (elapsed / self.completed) * remaining
                eta_str = f"{eta:.0f}s"
            elif remaining == 0:
                eta_str = "完成"
            else:
                eta_str = "unknown"
            
            display_completed = min(self.completed, self.total_clients)
            return f"[{bar}] {progress*100:.1f}% ({display_completed}/{self.total_clients}) ETA:{eta_str}"
    
    def get_status_line(self) -> str:
        """获取状态行"""
        with self.lock:
            return (f"活跃:{self.active} | 完成:{self.completed} | 失败:{self.failed} | "
                   f"连接中:{self.stage_stats['connecting']} | "
                   f"Hello:{self.stage_stats['hello']} | "
                   f"Detect:{self.stage_stats['detect']} | "
                   f"音频发送:{self.stage_stats['audio_sending']} | "
                   f"音频接收:{self.stage_stats['audio_receiving']}")

