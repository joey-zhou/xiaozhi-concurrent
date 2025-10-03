"""
测试指标收集 - 收集和统计所有测试指标
"""
import threading
import statistics
from collections import defaultdict
from typing import Dict, List, Optional, Any


class TestMetrics:
    """测试指标收集"""

    def __init__(self):
        self.connection_times = []
        self.connection_success_count = 0
        self.connection_fail_count = 0
        self.connection_total_count = 0

        self.hello_response_times = []
        self.hello_success_count = 0
        self.hello_fail_count = 0
        self.hello_total_count = 0

        # 唤醒词相关指标
        self.detect_response_times = []  # 唤醒词到音频响应时间
        self.detect_success_count = 0    # 唤醒词成功数量
        self.detect_fail_count = 0       # 唤醒词失败数量
        self.detect_total_count = 0      # 唤醒词总数
        self.detect_timeout_count = 0    # 唤醒词超时数量
        self.detect_errors = []          # 唤醒词错误明细

        self.audio_send_times = []
        self.audio_send_success_count = 0
        self.audio_send_fail_count = 0
        self.audio_send_total_count = 0

        self.stt_times = []  # 语音识别时延
        self.stt_success_count = 0
        self.stt_fail_count = 0
        self.stt_total_count = 0
        self.stt_accuracy_scores = []  # 语音识别准确率

        self.stt_to_start_times = []
        self.stt_to_start_success_count = 0
        self.stt_to_start_fail_count = 0

        self.audio_receive_times = []  # 总音频时长
        self.audio_receive_success_count = 0
        self.audio_receive_fail_count = 0
        self.audio_frame_intervals = []  # 帧间隔
        self.audio_delayed_frames = 0  # 延迟帧数（>65ms）

        # 音频流量统计
        self.audio_traffic_received = []  # 每个客户端接收的音频流量
        self.audio_traffic_sent = []      # 每个客户端发送的音频流量
        self.total_received_traffic = 0   # 总接收流量
        self.total_sent_traffic = 0       # 总发送流量
        self.peak_received_rate = 0       # 峰值接收速率（字节/秒）
        self.peak_sent_rate = 0           # 峰值发送速率（字节/秒）
        self.current_audio_rates = []     # 当前音频速率（用于实时监控）

        # 音频测试指标
        self.real_audio_send_times = []  # 音频发送时间
        self.real_audio_send_success_count = 0
        self.real_audio_send_fail_count = 0
        self.stt_accuracy_results = []  # 语音识别准确率结果
        self.audio_response_times = []  # 用户感知时延：音频发送完到收到响应
        self.server_processing_times = []  # 服务器处理时延：语音识别完成到返回音频

        self.hello_timeout_count = 0
        self.audio_timeout_count = 0
        self.stt_timeout_count = 0

        self.connection_errors = defaultdict(int)
        self.protocol_errors = defaultdict(int)

        self.lock = threading.Lock()

    def get_distribution_series(self) -> Dict[str, list]:
        """返回用于分布图的时延序列"""
        with self.lock:
            return {
                'connection': list(self.connection_times),
                'hello': list(self.hello_response_times),
                'detect': list(self.detect_response_times),
                'user_perceived': list(self.audio_response_times),
            }

    def record_connection_time(self, duration: float, success: bool, error_type: str = None):
        with self.lock:
            self.connection_times.append(duration)
            self.connection_total_count += 1
            if success:
                self.connection_success_count += 1
            else:
                self.connection_fail_count += 1
                if error_type:
                    self.connection_errors[error_type] += 1

    def record_hello_response_time(self, duration: float, success: bool, timeout: bool = False):
        with self.lock:
            if success:
                self.hello_response_times.append(duration)
                self.hello_success_count += 1
            else:
                self.hello_fail_count += 1
                if timeout:
                    self.hello_timeout_count += 1
            self.hello_total_count += 1

    def record_detect_response_time(self, duration: float, success: bool, timeout: bool = False):
        """记录唤醒词到音频响应的时间"""
        with self.lock:
            if success:
                self.detect_response_times.append(duration)
                self.detect_success_count += 1
            else:
                self.detect_fail_count += 1
                if timeout:
                    self.detect_timeout_count += 1
            self.detect_total_count += 1

    def record_audio_send_time(self, duration: float, success: bool):
        with self.lock:
            self.audio_send_times.append(duration)
            self.audio_send_total_count += 1
            if success:
                self.audio_send_success_count += 1
            else:
                self.audio_send_fail_count += 1

    def record_stt_time(self, duration: float, success: bool, accuracy: float = None, timeout: bool = False):
        with self.lock:
            if success:
                self.stt_times.append(duration)
                self.stt_success_count += 1
                if accuracy is not None:
                    self.stt_accuracy_scores.append(accuracy)
            else:
                self.stt_fail_count += 1
                if timeout:
                    self.stt_timeout_count += 1
            self.stt_total_count += 1

    def record_stt_to_start_time(self, duration: float, success: bool = True):
        with self.lock:
            if success:
                self.stt_to_start_times.append(duration)
                self.stt_to_start_success_count += 1
            else:
                self.stt_to_start_fail_count += 1

    def record_audio_receive_time(self, duration: float, success: bool = True, timeout: bool = False):
        with self.lock:
            if success:
                self.audio_receive_times.append(duration)
                self.audio_receive_success_count += 1
            else:
                self.audio_receive_fail_count += 1
                if timeout:
                    self.audio_timeout_count += 1

    def record_frame_interval(self, interval: float):
        with self.lock:
            self.audio_frame_intervals.append(interval)
            if interval > 65:
                self.audio_delayed_frames += 1

    def record_audio_traffic_received(self, client_id: str, bytes_received: int, duration: float):
        """记录接收音频流量统计"""
        with self.lock:
            self.audio_traffic_received.append({
                'client_id': client_id,
                'bytes': bytes_received,
                'duration': duration,
                'rate_kbps': (bytes_received * 8) / (duration * 1000) if duration > 0 else 0
            })
            self.total_received_traffic += bytes_received
            if duration > 0:
                rate_kbps = (bytes_received * 8) / (duration * 1000)
                self.peak_received_rate = max(self.peak_received_rate, rate_kbps)
    
    def record_audio_traffic_sent(self, client_id: str, bytes_sent: int, duration: float):
        """记录发送音频流量统计"""
        with self.lock:
            self.audio_traffic_sent.append({
                'client_id': client_id,
                'bytes': bytes_sent,
                'duration': duration,
                'rate_kbps': (bytes_sent * 8) / (duration * 1000) if duration > 0 else 0
            })
            self.total_sent_traffic += bytes_sent
            if duration > 0:
                rate_kbps = (bytes_sent * 8) / (duration * 1000)
                self.peak_sent_rate = max(self.peak_sent_rate, rate_kbps)

    def update_current_audio_rate(self, rate_bps: float):
        """更新当前音频速率（用于实时监控）"""
        with self.lock:
            self.current_audio_rates.append(rate_bps)
            # 只保留最近的数据用于计算当前平均值
            if len(self.current_audio_rates) > 100:
                self.current_audio_rates = self.current_audio_rates[-50:]

    def record_real_audio_send_time(self, duration: float, success: bool):
        """记录音频发送时间"""
        with self.lock:
            self.real_audio_send_times.append(duration)
            if success:
                self.real_audio_send_success_count += 1
            else:
                self.real_audio_send_fail_count += 1

    def record_stt_accuracy(self, expected_text: str, actual_text: str):
        """记录语音识别准确率"""
        with self.lock:
            import re
            expected_clean = re.sub(r'[^\w]', '', expected_text)
            actual_clean = re.sub(r'[^\w]', '', actual_text)
            
            is_accurate = expected_clean in actual_clean
            self.stt_accuracy_results.append({
                'expected': expected_text,
                'actual': actual_text,
                'accurate': is_accurate
            })

    def record_audio_response_time(self, duration: float):
        """记录用户感知时延：音频发送完到收到响应"""
        with self.lock:
            self.audio_response_times.append(duration)
    
    def record_server_processing_time(self, duration: float):
        """记录服务器处理时延：语音识别完成到返回音频"""
        with self.lock:
            self.server_processing_times.append(duration)

    def record_detect_error(self, device_id: str, session_id: str, reason: str, duration: float = 0.0):
        with self.lock:
            self.detect_errors.append({
                'device_id': device_id,
                'session_id': session_id,
                'reason': reason,
                'duration': duration
            })

    def record_protocol_error(self, error_type: str):
        with self.lock:
            self.protocol_errors[error_type] += 1

    def get_stats(self) -> Dict[str, Any]:
        """计算并返回统计信息"""
        with self.lock:
            def safe_stats(data_list):
                if not data_list:
                    return {'count': 0, 'mean': 0, 'median': 0, 'min': 0, 'max': 0, 'p95': 0, 'p99': 0}
                sorted_data = sorted(data_list)
                count = len(sorted_data)
                return {
                    'count': count,
                    'mean': statistics.mean(sorted_data),
                    'median': statistics.median(sorted_data),
                    'min': min(sorted_data),
                    'max': max(sorted_data),
                    'p95': sorted_data[int(count * 0.95)] if count > 0 else 0,
                    'p99': sorted_data[int(count * 0.99)] if count > 0 else 0,
                }

            return {
                'connection': {
                    **safe_stats(self.connection_times),
                    'success': self.connection_success_count,
                    'fail': self.connection_fail_count,
                    'total': self.connection_total_count,
                },
                'hello': {
                    **safe_stats(self.hello_response_times),
                    'success': self.hello_success_count,
                    'fail': self.hello_fail_count,
                    'timeout': self.hello_timeout_count,
                    'total': self.hello_total_count,
                },
                'detect': {
                    **safe_stats(self.detect_response_times),
                    'success': self.detect_success_count,
                    'fail': self.detect_fail_count,
                    'timeout': self.detect_timeout_count,
                    'total': self.detect_total_count,
                },
                'audio_send': {
                    **safe_stats(self.audio_send_times),
                    'success': self.audio_send_success_count,
                    'fail': self.audio_send_fail_count,
                    'total': self.audio_send_total_count,
                },
                'stt': {
                    **safe_stats(self.stt_times),
                    'success': self.stt_success_count,
                    'fail': self.stt_fail_count,
                    'timeout': self.stt_timeout_count,
                    'total': self.stt_total_count,
                },
                'audio_response': safe_stats(self.audio_response_times),
                'server_processing': safe_stats(self.server_processing_times),
                'frame_intervals': {
                    **safe_stats(self.audio_frame_intervals),
                    'delayed_frames': self.audio_delayed_frames,
                },
            }

    def get_summary(self) -> Dict[str, Any]:
        """获取汇总统计信息"""
        with self.lock:
            summary = {
                "connection": {
                    "success_rate": self.connection_success_count / max(self.connection_total_count, 1),
                    "avg_time": statistics.mean(self.connection_times) if self.connection_times else 0,
                    "total_count": self.connection_total_count,
                    "success_count": self.connection_success_count,
                    "fail_count": self.connection_fail_count,
                    "errors": dict(self.connection_errors)
                },
                "hello_response": {
                    "success_rate": self.hello_success_count / max(self.hello_total_count, 1),
                    "avg_time": statistics.mean(self.hello_response_times) if self.hello_response_times else 0,
                    "total_count": self.hello_total_count,
                    "success_count": self.hello_success_count,
                    "fail_count": self.hello_fail_count,
                    "timeout_count": self.hello_timeout_count
                },
                "detect_response": {
                    "success_rate": self.detect_success_count / max(self.detect_total_count, 1),
                    "avg_time": statistics.mean(self.detect_response_times) if self.detect_response_times else 0,
                    "total_count": self.detect_total_count,
                    "success_count": self.detect_success_count,
                    "fail_count": self.detect_fail_count,
                    "timeout_count": self.detect_timeout_count,
                    "errors": list(self.detect_errors)
                },
                "audio_send": {
                    "success_rate": self.audio_send_success_count / max(self.audio_send_total_count, 1),
                    "avg_time": statistics.mean(self.audio_send_times) if self.audio_send_times else 0,
                    "total_count": self.audio_send_total_count,
                    "success_count": self.audio_send_success_count,
                    "fail_count": self.audio_send_fail_count
                },
                "stt": {
                    "success_rate": self.stt_success_count / max(self.stt_total_count, 1),
                    "avg_time": statistics.mean(self.stt_times) if self.stt_times else 0,
                    "avg_accuracy": statistics.mean(self.stt_accuracy_scores) if self.stt_accuracy_scores else 0,
                    "total_count": self.stt_total_count,
                    "success_count": self.stt_success_count,
                    "fail_count": self.stt_fail_count,
                    "timeout_count": self.stt_timeout_count,
                    "min_time": min(self.stt_times) if self.stt_times else 0,
                    "max_time": max(self.stt_times) if self.stt_times else 0
                },
                "stt_to_start": {
                    "avg_time": statistics.mean(self.stt_to_start_times) if self.stt_to_start_times else 0,
                    "success_count": self.stt_to_start_success_count,
                    "fail_count": self.stt_to_start_fail_count,
                    "total_count": self.stt_to_start_success_count + self.stt_to_start_fail_count
                },
                "audio_receive": {
                    "avg_time": statistics.mean(self.audio_receive_times) if self.audio_receive_times else 0,
                    "success_count": self.audio_receive_success_count,
                    "fail_count": self.audio_receive_fail_count,
                    "timeout_count": self.audio_timeout_count,
                    "total_count": self.audio_receive_success_count + self.audio_receive_fail_count
                },
                "frame_timing": {
                    "avg_interval": statistics.mean(self.audio_frame_intervals) if self.audio_frame_intervals else 0,
                    "max_interval": max(self.audio_frame_intervals) if self.audio_frame_intervals else 0,
                    "min_interval": min(self.audio_frame_intervals) if self.audio_frame_intervals else 0,
                    "delayed_frames": self.audio_delayed_frames,
                    "total_frames": len(self.audio_frame_intervals),
                    "delay_rate": self.audio_delayed_frames / max(len(self.audio_frame_intervals), 1),
                    "target_interval": 60.0,
                    "is_good_rate": (self.audio_delayed_frames / max(len(self.audio_frame_intervals), 1)) < 0.1
                },
                "audio_traffic": {
                    "received_bytes": self.total_received_traffic,
                    "sent_bytes": self.total_sent_traffic,
                    "total_bytes": self.total_received_traffic + self.total_sent_traffic,
                    "received_mb": self.total_received_traffic / (1024 * 1024),
                    "sent_mb": self.total_sent_traffic / (1024 * 1024),
                    "total_mb": (self.total_received_traffic + self.total_sent_traffic) / (1024 * 1024),
                    "peak_received_rate_kbps": self.peak_received_rate,
                    "peak_sent_rate_kbps": self.peak_sent_rate,
                    "avg_received_rate_kbps": statistics.mean([c['rate_kbps'] for c in self.audio_traffic_received]) if self.audio_traffic_received else 0,
                    "avg_sent_rate_kbps": statistics.mean([c['rate_kbps'] for c in self.audio_traffic_sent]) if self.audio_traffic_sent else 0,
                    "clients_count": max(len(self.audio_traffic_received), len(self.audio_traffic_sent)),
                    "avg_per_client_received_mb": (self.total_received_traffic / len(self.audio_traffic_received) / (1024 * 1024)) if self.audio_traffic_received else 0,
                    "avg_per_client_sent_mb": (self.total_sent_traffic / len(self.audio_traffic_sent) / (1024 * 1024)) if self.audio_traffic_sent else 0
                },
                "real_audio_test": {
                    "send_success_rate": self.real_audio_send_success_count / max(self.real_audio_send_success_count + self.real_audio_send_fail_count, 1),
                    "avg_send_time": statistics.mean(self.real_audio_send_times) if self.real_audio_send_times else 0,
                    "stt_accuracy_rate": sum(1 for r in self.stt_accuracy_results if r['accurate']) / max(len(self.stt_accuracy_results), 1),
                    "avg_response_time": statistics.mean(self.audio_response_times) if self.audio_response_times else 0,
                    "avg_server_processing_time": statistics.mean(self.server_processing_times) if self.server_processing_times else 0,
                    "response_time_min": min(self.audio_response_times) if self.audio_response_times else 0,
                    "response_time_max": max(self.audio_response_times) if self.audio_response_times else 0,
                    "server_processing_time_min": min(self.server_processing_times) if self.server_processing_times else 0,
                    "server_processing_time_max": max(self.server_processing_times) if self.server_processing_times else 0,
                    "total_tests": len(self.stt_accuracy_results),
                    "accurate_count": sum(1 for r in self.stt_accuracy_results if r['accurate'])
                }
            }
            return summary

