"""
并发测试器 - 管理多个客户端的并发测试
"""
import asyncio
import os
import sys
import time
import threading
import statistics
import unicodedata
from typing import Dict, Any, List
from datetime import datetime

from .client import XiaozhiTestClient
from .metrics import TestMetrics
from .progress import ProgressTracker
from .logger import logger, log_debug, log_client_flow, debug_logger, client_flow_logger
from .config import timestamp, LOG_DIR, HAS_MATPLOTLIB, FIGURES_DIR

if HAS_MATPLOTLIB:
    import matplotlib.pyplot as plt
    import numpy as np


class XiaozhiConcurrentTester:
    """Xiaozhi 并发测试器"""

    def __init__(self, server_url: str, test_audio_path: str = None):
        self.server_url = server_url
        self.test_audio_path = test_audio_path
        self.metrics = TestMetrics()
        self.progress = None
        
        # 状态监控
        self.active_clients = 0
        self.completed_clients = 0
        self.running = True
        self.display_thread = None

    def _render_table(self, headers, rows, title: str = None) -> str:
        """渲染Unicode宽度对齐的ASCII表格。headers: [str], rows: List[List[str|number]]."""
        import unicodedata
        def ulen(s: str) -> int:
            w = 0
            for ch in s:
                ea = unicodedata.east_asian_width(ch)
                w += 2 if ea in ('W', 'F') else 1
            return w
        str_headers = [str(h) for h in headers]
        str_rows = [[str(c) for c in r] for r in rows]
        col_count = len(str_headers)
        col_widths = [ulen(str_headers[i]) for i in range(col_count)]
        for row in str_rows:
            for i in range(col_count):
                if i < len(row):
                    col_widths[i] = max(col_widths[i], ulen(row[i]))
        def sep(char='-'):
            return '+'.join([''] + [char * (w + 2) for w in col_widths] + [''])
        def pad_to_width(text: str, width: int) -> str:
            cur = ulen(text)
            if cur >= width:
                return text
            return text + ' ' * (width - cur)
        def render_row(cells):
            padded = []
            for i in range(col_count):
                text = cells[i] if i < len(cells) else ''
                padded.append(' ' + pad_to_width(text, col_widths[i]) + ' ')
            return '|' + '|'.join(padded) + '|'
        lines = []
        if title:
            lines.append(title)
        lines.append(sep('='))
        lines.append(render_row(str_headers))
        lines.append(sep('='))
        for r in str_rows:
            lines.append(render_row(r))
        lines.append(sep('-'))
        return '\n'.join(lines)

    def _generate_summary_chart(self, summary: Dict[str, Any]):
        """生成简洁的结果总览图（成功率+时延）。需要matplotlib。"""
        if not HAS_MATPLOTLIB:
            return None
        try:
            import matplotlib.pyplot as plt
            from datetime import datetime as _dt
            
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'DejaVu Sans', 'Liberation Sans', 'Arial Unicode MS', 'SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            success_labels = ['连接', 'Hello', 'Detect', 'STT准确率']
            success_values = [
                summary['connection']['success_rate'] * 100,
                summary['hello_response']['success_rate'] * 100,
                summary['detect_response']['success_rate'] * 100,
                summary['real_audio_test']['stt_accuracy_rate'] * 100,
            ]
            time_labels = ['Detect', '音频播放', 'STT', '用户感知']
            time_values = [
                summary['detect_response']['avg_time'],
                summary['audio_receive']['avg_time'],
                summary['stt']['avg_time'],
                summary['real_audio_test']['avg_response_time'],
            ]
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            fig.suptitle('Xiaozhi 并发测试 - 结果总览', fontsize=14, fontweight='bold')
            ax1 = axes[0]
            bars1 = ax1.bar(success_labels, success_values, color=['#2ecc71', '#3498db', '#9b59b6', '#f1c40f'])
            ax1.set_ylabel('成功率 / 准确率 (%)')
            ax1.set_ylim(0, 100)
            for b in bars1:
                ax1.text(b.get_x() + b.get_width()/2, b.get_height() + 1, f"{b.get_height():.1f}%", ha='center', va='bottom', fontsize=9)
            ax1.grid(axis='y', alpha=0.2)
            ax2 = axes[1]
            bars2 = ax2.bar(time_labels, time_values, color=['#e74c3c', '#e67e22', '#16a085', '#34495e'])
            ax2.set_ylabel('平均时延 (秒)')
            for b, v in zip(bars2, time_values):
                ax2.text(b.get_x() + b.get_width()/2, v + max(0.02, v*0.03), f"{v:.2f}s", ha='center', va='bottom', fontsize=9)
            ax2.grid(axis='y', alpha=0.2)
            plt.tight_layout()
            filename = f"xiaozhi_summary_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(FIGURES_DIR, filename)
            plt.savefig(filepath, dpi=200, bbox_inches='tight')
            print(f"📊 结果总览图已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"生成结果总览图时出错: {e}")
            return None

    def _generate_latency_distributions(self):
        """生成 2x2 时延直方图并拟合正态曲线：连接/Hello/Detect/用户感知。"""
        if not HAS_MATPLOTLIB:
            return None
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            from matplotlib.ticker import MaxNLocator
            from datetime import datetime as _dt
            
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'DejaVu Sans', 'Liberation Sans', 'Arial Unicode MS', 'SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            series = self.metrics.get_distribution_series()
            fig, axes = plt.subplots(2, 2, figsize=(12, 8))
            fig.suptitle(f"Xiaozhi 并发测试", fontsize=14, fontweight='bold')
            palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
            cfg = [
                ('连接时间', series['connection'], axes[0,0], palette[0]),
                ('Hello时间', series['hello'], axes[0,1], palette[1]),
                ('Detect时间', series['detect'], axes[1,0], palette[2]),
                ('用户感知时延', series['user_perceived'], axes[1,1], palette[3]),
            ]
            for title, data, ax, color in cfg:
                arr = np.array(data, dtype=float) if data else np.array([])
                if arr.size == 0:
                    ax.text(0.5, 0.5, '无数据', ha='center', va='center')
                    ax.set_title(title)
                    ax.grid(True, alpha=0.3)
                    continue
                bins = min(30, max(8, int(np.sqrt(arr.size))))
                n, bin_edges, patches = ax.hist(
                    arr,
                    bins=bins,
                    color=color,
                    alpha=0.75,
                    edgecolor='white',
                    density=False,
                    rwidth=0.7
                )
                mu = float(np.mean(arr))
                sigma = float(np.std(arr)) if arr.size > 1 else 0.0
                if sigma > 0:
                    xs = np.linspace(arr.min(), arr.max(), 200)
                    # 将正态分布线缩放到计数尺度：总样本数 * bin宽度
                    # 使曲线与直方图量级一致，仅展示曲线，不显示公式文字
                    bin_width = (arr.max() - arr.min()) / bins if bins > 0 else 1.0
                    ys = (arr.size * bin_width) * (1.0/(sigma*np.sqrt(2*np.pi)) * np.exp(-0.5*((xs-mu)/sigma)**2))
                    ax.plot(xs, ys, 'r-', linewidth=2)
                # 在每个柱子上标注数量（整数）
                if 'n' in locals() and 'patches' in locals():
                    for count, patch in zip(n, patches):
                        if count <= 0:
                            continue
                        x = patch.get_x() + patch.get_width()/2
                        y = patch.get_height()
                        ax.text(x, y + max(0.02 * max(n), 0.1), f"{int(round(count))}", ha='center', va='bottom', fontsize=9)
                # 右上角显示平均时间
                ax.text(0.98, 0.95, f"平均: {mu:.3f}s", transform=ax.transAxes, ha='right', va='top', fontsize=10, color='#333')
                ax.set_title(title)
                ax.set_xlabel('时延(秒)')
                ax.set_ylabel('数量')
                ax.grid(True, alpha=0.3)
                # Y轴强制使用整数刻度
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            plt.tight_layout()
            filename = f"xiaozhi_latency_dist_{_dt.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(FIGURES_DIR, filename)
            plt.savefig(filepath, dpi=200, bbox_inches='tight')
            print(f"📈 时延分布图已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"生成时延分布图时出错: {e}")
            return None

    def start_display_monitoring(self, total_clients: int, rounds: int = 1):
        """启动实时显示监控"""
        self.progress = ProgressTracker(total_clients, rounds)
        self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
        self.display_thread.start()

    def display_loop(self):
        """显示循环 - 实时进度条和系统状态"""
        print("\n" + "="*100)
        print("Xiaozhi WebSocket 并发测试 - 实时监控")
        print("="*100)
        
        last_completed = 0  # 记录上次显示的完成数
        
        while self.running:
            try:
                # 检查是否所有测试都完成了
                current_completed = self.progress.completed + self.progress.failed
                if current_completed >= self.progress.total_tests and current_completed > last_completed:
                    # 所有测试完成，再显示一次最终状态然后退出显示循环
                    self.display_current_status()
                    time.sleep(1)  # 让用户看到最终状态
                    break
                
                last_completed = current_completed
                self.display_current_status()
                
                time.sleep(0.5)  # 每0.5秒更新一次，提高刷新频率以便看到快速阶段
                
            except Exception as e:
                logger.error(f"显示循环错误: {e}")
                time.sleep(0.5)
    
    def display_current_status(self):
        """显示当前状态"""
        # 清空前面的行并重新绘制
        print("\033[2J\033[H", end="")  # 清屏并移动到顶部
        
        print("Xiaozhi WebSocket 并发测试 - 实时监控")
        print("="*100)
        
        # 进度条
        progress_bar = self.progress.get_progress_bar(60)
        print(f"测试进度: {progress_bar}")
        
        # 状态行
        status_line = self.progress.get_status_line()
        print(f"测试状态: {status_line}")
        
        # 实时测试指标
        summary = self.metrics.get_summary()
        frame_info = summary['frame_timing']
        frame_status = "✓良好" if frame_info['is_good_rate'] else "⚠延迟"
        audio_traffic = summary['audio_traffic']
        
        print(f"连接成功率: {summary['connection']['success_rate']*100:.1f}% | "
              f"Hello成功率: {summary['hello_response']['success_rate']*100:.1f}% | "
              f"唤醒词成功率: {summary['detect_response']['success_rate']*100:.1f}% | "
              f"唤醒词时延: {summary['detect_response']['avg_time']:.2f}s")
        
        print(f"音频时长: {summary['audio_receive']['avg_time']:.2f}s | "
              f"帧率: {frame_info['avg_interval']:.1f}ms (目标60ms) {frame_status} | "
              f"延迟率: {frame_info['delay_rate']*100:.1f}%")
        
        print(f"音频流量: 总计{audio_traffic['total_mb']:.2f}MB | "
              f"接收{audio_traffic['received_mb']:.2f}MB | 发送{audio_traffic['sent_mb']:.2f}MB | "
              f"峰值接收{audio_traffic['peak_received_rate_kbps']:.1f}kbps")
        
        # 真实音频测试指标
        real_audio = summary['real_audio_test']
        print(f"真实音频测试: 语音识别准确率{real_audio['stt_accuracy_rate']*100:.1f}% | "
              f"用户时延{real_audio['avg_response_time']:.2f}s | "
              f"服务器时延{real_audio['avg_server_processing_time']:.2f}s | "
              f"发送成功率{real_audio['send_success_rate']*100:.1f}% | "
              f"测试数{real_audio['total_tests']}")
        
        print("="*100)
        
        # 检查是否完成
        total_finished = self.progress.completed + self.progress.failed
        if total_finished >= self.progress.total_tests:
            print("✅ 所有测试已完成")
        else:
            print("按 Ctrl+C 停止测试")

    def reorder_client_flow_log(self):
        """将客户端流程日志按设备ID与时间排序，输出到 logs/xiaozhi_client_flow_sorted_<ts>.log"""
        import re
        in_path = os.path.join(LOG_DIR, f"xiaozhi_client_flow_{timestamp}.log")
        if not os.path.exists(in_path):
            return
        with open(in_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n') for line in f]
        # 解析格式: [HH:MM:SS.mmm] [client_id] [STAGE]? message
        pattern = re.compile(r"^\[(?P<ts>\d{2}:\d{2}:\d{2}\.\d{3})\] \[(?P<cid>[^\]]+)\](?: \[(?P<stage>[^\]]+)\])? (?P<msg>.*)$")
        parsed = []
        for line in lines:
            m = pattern.match(line)
            if not m:
                continue
            ts = m.group('ts')
            cid = m.group('cid')
            stage = m.group('stage') or ''
            msg = m.group('msg')
            # 转换时间为排序键（HH:MM:SS.mmm -> 秒）
            try:
                h, mnt, s_ms = ts.split(':')
                s, ms = s_ms.split('.')
                total_ms = int(h)*3600000 + int(mnt)*60000 + int(s)*1000 + int(ms)
            except Exception:
                total_ms = 0
            parsed.append((cid, total_ms, ts, stage, msg))
        # 先按设备，再按时间排序
        parsed.sort(key=lambda x: (x[0], x[1]))
        out_path = os.path.join(LOG_DIR, f"xiaozhi_client_flow_sorted_{timestamp}.log")
        with open(out_path, 'w', encoding='utf-8') as f:
            current_cid = None
            for cid, _, ts, stage, msg in parsed:
                if cid != current_cid:
                    current_cid = cid
                    f.write(f"\n===== 设备 {cid} =====\n")
                if stage:
                    f.write(f"[{ts}] [{cid}] [{stage}] {msg}\n")
                else:
                    f.write(f"[{ts}] [{cid}] {msg}\n")

    def _parse_dt_to_ms(self, dt_str: str) -> int:
        """将如 2025-10-03 22:08:55,123 或 .123 转为毫秒整数。失败返回0。"""
        from datetime import datetime as _dt
        for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = _dt.strptime(dt_str, fmt)
                return int(dt.timestamp() * 1000)
            except Exception:
                pass
        return 0

    def reorder_standard_log(self, src_filename: str, dst_prefix: str):
        """按照设备ID(若有)与时间戳对标准日志进行重排（忽略GLOBAL）。输出 logs/<dst_prefix>_sorted_<ts>.log"""
        import re
        in_path = os.path.join(LOG_DIR, src_filename)
        if not os.path.exists(in_path):
            return
        with open(in_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n') for line in f]
        # 形如: 2025-10-03 22:08:55,123 - LEVEL - [client] msg 或没有 [client]
        pat = re.compile(r"^(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[\.,]\d{3}) - [^-]+ - (?P<msg>.*)$")
        parsed = []
        for line in lines:
            m = pat.match(line)
            if not m:
                continue
            dt_ms = self._parse_dt_to_ms(m.group('dt'))
            msg = m.group('msg')
            # 从消息中抽取可选的 [client_id]
            cid = 'GLOBAL'
            if msg.startswith('['):
                try:
                    rb = msg.index(']')
                    cid = msg[1:rb]
                except Exception:
                    pass
            # 仅保留带设备ID的记录，忽略 GLOBAL
            if cid != 'GLOBAL':
                parsed.append((cid, dt_ms, m.group('dt'), msg))
        parsed.sort(key=lambda x: (x[0], x[1]))
        out_path = os.path.join(LOG_DIR, f"{dst_prefix}_sorted_{timestamp}.log")
        with open(out_path, 'w', encoding='utf-8') as f:
            current_cid = None
            for cid, _, dt_str, msg in parsed:
                if cid != current_cid:
                    current_cid = cid
                    f.write(f"\n===== 设备 {cid} =====\n")
                f.write(f"{dt_str} - {msg}\n")

    async def run_single_test(self, client_id: int, rounds: int = 1):
        """运行单个客户端测试（支持多轮）
        
        Args:
            client_id: 客户端ID
            rounds: 执行轮数，每轮测试完成后会重置状态并重新开始
        """
        # 生成固定格式的设备ID: xiaozhi-test-000001 到 xiaozhi-test-999999
        device_id = f"xiaozhi-test-{client_id+1:06d}"
        
        log_debug(f"准备创建客户端: {device_id}, 执行轮数: {rounds}", device_id)

        client = XiaozhiTestClient(
            self.server_url,
            device_id,
            self.metrics,
            self.progress,
            self.test_audio_path
        )

        # 使用连接建立/关闭事件跟踪活跃数，这里不再手动+1，避免重复统计
        
        try:
            for round_num in range(1, rounds + 1):
                if rounds > 1:
                    log_debug(f"开始第 {round_num}/{rounds} 轮测试: {device_id}", device_id)
                else:
                    log_debug(f"开始运行测试: {device_id}", device_id)
                
                await client.run_test()
                
                if rounds > 1:
                    log_debug(f"第 {round_num}/{rounds} 轮测试完成: {device_id}", device_id)
                else:
                    log_debug(f"测试完成: {device_id}", device_id)
                
                # 如果不是最后一轮，重置客户端状态并等待一小段时间
                if round_num < rounds:
                    await asyncio.sleep(0.5)  # 轮次之间短暂延迟
                    client.reset_for_next_round()
                    
        except Exception as e:
            log_debug(f"测试异常: {device_id} - {e}", device_id)
            logger.error(f"客户端 {device_id} 测试异常: {e}")
        finally:
            # 使用连接关闭事件跟踪活跃数，这里不再手动-1
            pass

    async def run_concurrent_tests(self, num_clients: int, rounds: int = 1):
        """运行并发测试
        
        Args:
            num_clients: 并发客户端数量
            rounds: 每个客户端执行轮数
        """
        if rounds > 1:
            print(f"开始并发测试，客户端数量: {num_clients}, 每个客户端执行 {rounds} 轮")
        else:
            print(f"开始并发测试，客户端数量: {num_clients}")

        # 创建所有任务
        all_tasks = []
        for i in range(num_clients):
            task = asyncio.create_task(self.run_single_test(i, rounds))
            all_tasks.append(task)
        
        # 等待所有任务完成
        await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # 确保显示线程有机会更新最终状态
        await asyncio.sleep(0.5)

    def run_full_test(self, num_clients: int, rounds: int = 1):
        """运行完整测试
        
        Args:
            num_clients: 并发客户端数量
            rounds: 每个客户端执行轮数
        """
        print("="*100)
        print("Xiaozhi WebSocket 并发测试工具")
        print("="*100)
        print(f"服务器地址: {self.server_url}")
        print(f"并发客户端数: {num_clients}")
        if rounds > 1:
            print(f"执行轮数: {rounds} 轮/客户端")
            print(f"总测试次数: {num_clients * rounds}")
        print(f"测试音频: {self.test_audio_path or '自动生成'}")
        print(f"调试日志: {os.path.join(LOG_DIR, f'xiaozhi_debug_{timestamp}.log')}")
        print(f"客户端流程日志: {os.path.join(LOG_DIR, f'xiaozhi_client_flow_{timestamp}.log')}")
        print("="*100)
        
        # 记录测试开始信息
        logger.info(f"测试开始 - 服务器: {self.server_url}, 客户端数: {num_clients}, 轮数: {rounds}")
        debug_logger.debug(f"测试配置 - 服务器地址: {self.server_url}, 并发客户端数: {num_clients}, 执行轮数: {rounds}")

        # 启动显示监控
        self.start_display_monitoring(num_clients, rounds)
        time.sleep(1)

        try:
            # 运行测试
            asyncio.run(self.run_concurrent_tests(num_clients, rounds))
        except KeyboardInterrupt:
            print("\n\n测试被用户中断")
        finally:
            self.running = False
            
            # 等待显示线程完成，给它更多时间显示最终状态
            if self.display_thread:
                self.display_thread.join(timeout=3)
            
            # 清屏并显示最终完成状态
            print("\033[2J\033[H", end="")
            print("="*100)
            print("✅ 测试执行完成，正在生成最终报告...")
            print("="*100)
            
            # 记录测试完成
            logger.info("测试执行完成，开始生成最终报告")
            debug_logger.debug("所有客户端测试已完成")

            # 生成最终报告
            self.print_final_results()

    def print_final_results(self):
        """输出最终测试结果"""
        summary = self.metrics.get_summary()

        print("\n" + "="*100)
        print("Xiaozhi WebSocket 并发测试 - 最终结果报告")
        print("="*100)

        rows_overview = [
            ["连接", f"{summary['connection']['success_rate']*100:.2f}% ({summary['connection']['success_count']}/{summary['connection']['total_count']})", f"{summary['connection']['avg_time']:.3f}s"],
            ["Hello", f"{summary['hello_response']['success_rate']*100:.2f}% ({summary['hello_response']['success_count']}/{summary['hello_response']['total_count']})", f"{summary['hello_response']['avg_time']:.3f}s"],
            ["唤醒词", f"{summary['detect_response']['success_rate']*100:.2f}% ({summary['detect_response']['success_count']}/{summary['detect_response']['total_count']})", f"{summary['detect_response']['avg_time']:.3f}s"],
            ["音频接收", f"成功{summary['audio_receive']['success_count']}, 超时{summary['audio_receive']['timeout_count']}", "-"],
        ]
        print(self._render_table(["指标", "成功率/计数", "平均耗时"], rows_overview, title="\n📊 核心指标"))
        if summary['detect_response']['timeout_count'] > 0:
            print("(提示) Detect存在超时: ", summary['detect_response']['timeout_count'])

        frame_info = summary['frame_timing']
        frame_quality = "优秀" if frame_info['delay_rate'] < 0.05 else "良好" if frame_info['delay_rate'] < 0.1 else "一般" if frame_info['delay_rate'] < 0.2 else "较差"
        rows_frame = [
            ["平均间隔", f"{frame_info['avg_interval']:.2f}ms"],
            ["质量", f"{frame_quality} ({frame_info['delayed_frames']}/{frame_info['total_frames']} 延迟, {frame_info['delay_rate']*100:.2f}%)"],
            ["范围", f"最小{frame_info['min_interval']:.1f}ms / 最大{frame_info['max_interval']:.1f}ms"],
        ]
        print(self._render_table(["音频帧率统计", "值"], rows_frame))

        audio_traffic = summary['audio_traffic']
        rows_traffic = [
            ["接收/发送/总", f"{audio_traffic['received_mb']:.2f}MB / {audio_traffic['sent_mb']:.2f}MB / {audio_traffic['total_mb']:.2f}MB"],
            ["平均每客户端", f"接收{audio_traffic['avg_per_client_received_mb']:.2f}MB / 发送{audio_traffic['avg_per_client_sent_mb']:.2f}MB"],
            ["平均速率", f"接收{audio_traffic['avg_received_rate_kbps']:.1f}kbps / 发送{audio_traffic['avg_sent_rate_kbps']:.1f}kbps"],
            ["峰值速率", f"接收{audio_traffic['peak_received_rate_kbps']:.1f}kbps / 发送{audio_traffic['peak_sent_rate_kbps']:.1f}kbps"],
        ]
        print(self._render_table(["音频流量统计", "值"], rows_traffic))

        real_audio = summary['real_audio_test']
        rows_real = [
            ["发送成功率", f"{real_audio['send_success_rate']*100:.2f}% ({real_audio['total_tests']} 次)"],
            ["语音识别准确率", f"{real_audio['stt_accuracy_rate']*100:.2f}% ({real_audio['accurate_count']}/{real_audio['total_tests']})"],
            ["发送音频时长", f"{real_audio['avg_send_time']:.3f}s"],
            ["语音识别时延", f"均值{summary['stt']['avg_time']:.3f}s / 最小{summary['stt']['min_time']:.3f}s / 最大{summary['stt']['max_time']:.3f}s"],
            ["服务器处理", f"均值{real_audio['avg_server_processing_time']:.3f}s / 最小{real_audio['server_processing_time_min']:.3f}s / 最大{real_audio['server_processing_time_max']:.3f}s"],
            ["用户感知", f"均值{real_audio['avg_response_time']:.3f}s / 最小{real_audio['response_time_min']:.3f}s / 最大{real_audio['response_time_max']:.3f}s"],
        ]
        print(self._render_table(["真实音频测试", "值"], rows_real))

        if summary['connection']['errors']:
            print("\n连接错误分类:", summary['connection']['errors'])
        if summary['detect_response'].get('errors'):
            print(f"\nDetect错误明细: 共{len(summary['detect_response']['errors'])}条 (仅展示前10条)")
            for e in summary['detect_response']['errors'][:10]:
                print(f"  device={e['device_id']} session_id={e['session_id']} reason={e['reason']} duration={e['duration']:.3f}s")

        print("="*100)
        
        # 显示日志文件位置
        # 不再生成详细日志文件
        # print(f"\n📄 详细日志已保存到: {log_filename}")
        print(f"🔍 调试日志已保存到: {os.path.join(LOG_DIR, f'xiaozhi_debug_{timestamp}.log')}")
        print(f"📋 客户端流程日志已保存到: {os.path.join(LOG_DIR, f'xiaozhi_client_flow_{timestamp}.log')}")

        
        # 对客户端流程日志按设备与时间重排
        try:
            self.reorder_client_flow_log()
            # 重排调试日志
            self.reorder_standard_log(f"xiaozhi_debug_{timestamp}.log", "xiaozhi_debug")
        except Exception as e:
            print(f"重排客户端流程日志时出错: {e}")
        
        # 记录测试结束
        logger.info("测试报告生成完成，所有日志已保存")
        debug_logger.debug("测试流程全部结束")
        
        # 生成可视化图表
        if HAS_MATPLOTLIB:
            self._generate_latency_distributions()

