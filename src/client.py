"""
WebSocket 测试客户端 - 单个客户端的测试流程
"""
import asyncio
import json
import time
import wave
import io
import os
from typing import Optional, Dict, Any, List, Tuple
import websockets
import numpy as np

from .metrics import TestMetrics
from .progress import ProgressTracker
from .logger import log_debug, log_client_flow, logger, debug_logger, client_flow_logger
from .config import HAS_OPUS

if HAS_OPUS:
    import opuslib


class XiaozhiTestClient:
    """Xiaozhi WebSocket测试客户端"""

    def __init__(self, server_url: str, device_id: str, metrics: TestMetrics, 
                 progress: ProgressTracker, test_audio_path: str = None):
        self.server_url = server_url
        self.device_id = device_id
        self.session_id = ""  # 服务器分配的session_id
        self.metrics = metrics
        self.progress = progress
        self.test_audio_path = test_audio_path
        self.websocket = None

        # 状态跟踪
        self.connected = False
        self.hello_sent = False
        self.hello_received = False
        self.detect_sent = False          # 唤醒词发送状态
        self.detect_audio_received = False # 唤醒词音频接收状态
        self.test_completed = False       # 测试完成状态
        self.audio_sending = False
        self.audio_receiving = False
        self.has_failed = False

        # 时间戳 - 使用perf_counter以提高精度
        self.connection_start_time = 0
        self.hello_send_time = 0
        self.hello_receive_time = 0
        self.detect_send_time = 0         # 唤醒词发送时间
        self.detect_audio_receive_time = 0 # 唤醒词音频接收时间
        self.audio_send_start_time = 0
        self.audio_send_end_time = 0
        self.stt_complete_time = 0
        self.start_receive_time = 0
        self.audio_receive_start_time = 0
        
        # 性能计数器基准时间（用于perf_counter转换）
        self.perf_counter_base = time.perf_counter()
        self.time_base = time.time()

        # 音频帧时间戳
        self.last_frame_time = 0
        self.frame_count = 0

        # 多段音频接收状态（用于分析每个sentence_start的音频片段）
        self.current_segment_start_time = 0
        self.segment_frame_count = 0
        self.segment_intervals = []
        self.total_segments = 0
        self.completed_segments = 0
        self.segment_frame_rates = []  # 每个片段的帧率

        # 音频流量统计
        self.total_audio_bytes = 0  # 接收到的总音频字节数
        self.audio_start_time = 0   # 音频开始接收时间

        # 真实音频测试状态
        self.real_audio_phase = False  # 是否进入真实音频测试阶段
        self.real_audio_sent = False   # 是否已发送真实音频
        self.real_audio_send_end_time = 0  # 真实音频发送结束时间
        self.expected_stt_text = ""    # 期望的STT识别文本
        self.server_processing_complete = False  # 服务器是否完成STT处理
        self.server_stt_start_time = 0  # 服务器开始STT处理的时间（用于响应时延计算）

        # 测试音频数据
        self.real_audio_data = self.load_real_audio_data()
        
        # 预生成Opus静音帧（避免每次重新生成）
        self.opus_silence_frame = self.generate_opus_silence_frame()

    def get_precise_time(self) -> float:
        """获取精确时间戳（基于perf_counter，但转换为time.time()的基准）"""
        elapsed = time.perf_counter() - self.perf_counter_base
        return self.time_base + elapsed
    
    def complete_test(self):
        """完成测试"""
        if not self.test_completed:
            self.test_completed = True
            
            # 清理所有可能残留的阶段状态
            # 注意：由于我们无法知道当前处于哪个阶段，所以需要根据状态标志来清理
            # 这些标志在测试过程中会被设置，如果测试完成时还是True，说明需要清理对应的阶段计数
            
            # 注意：connecting 和 hello 阶段通常在测试完成前就已经清理，这里不需要处理
            # detect 阶段也是在收到响应后就清理了
            
            # 检查是否还在 audio_sending 阶段
            if self.audio_sending:
                self.progress.update_stage('audio_sending', -1)
                self.audio_sending = False
            
            # 检查是否还在 audio_receiving 阶段
            if self.audio_receiving:
                self.progress.update_stage('audio_receiving', -1)
                self.audio_receiving = False
            
            # 检查是否还在 waiting_response 阶段（这个状态没有专门的标志，需要通过其他状态推断）
            # waiting_response 通常在收到start或音频数据时会清理
            
            self.progress.increment_completed()

    def load_real_audio_data(self) -> Dict[str, bytes]:
        """加载真实测试音频文件"""
        audio_files = {
            "1加一等于几": "1加一等于几.wav"
        }
        
        loaded_audio = {}
        for text, filename in audio_files.items():
            if os.path.exists(filename):
                try:
                    with wave.open(filename, 'rb') as wav_file:
                        # 读取WAV文件信息
                        sample_rate = wav_file.getframerate()
                        channels = wav_file.getnchannels()
                        sample_width = wav_file.getsampwidth()
                        frames = wav_file.readframes(wav_file.getnframes())
                        
                        # 转换为16kHz单声道16位（如果需要）
                        if sample_rate != 16000 or channels != 1 or sample_width != 2:
                            logger.warning(f"音频文件 {filename} 格式不匹配，建议使用16kHz单声道16位WAV")
                        
                        loaded_audio[text] = frames
                        logger.info(f"成功加载音频文件: {filename}")
                except Exception as e:
                    logger.error(f"加载音频文件 {filename} 失败: {e}")
                    # 生成默认音频数据
                    loaded_audio[text] = self.generate_default_audio(text)
            else:
                logger.warning(f"音频文件 {filename} 不存在，使用默认音频数据")
                loaded_audio[text] = self.generate_default_audio(text)
        
        return loaded_audio

    def generate_default_audio(self, text: str) -> bytes:
        """为指定文本生成默认音频数据"""
        # 生成不同频率的音频以区分不同文本
        sample_rate = 16000
        duration = 2.0
        frequency = 440 if "北京" in text else 880
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio_data = np.sin(2 * np.pi * frequency * t) * 0.3
        audio_16bit = (audio_data * 32767).astype(np.int16)
        
        return audio_16bit.tobytes()

    def encode_to_opus_frames(self, pcm_data: bytes, sample_rate: int = 16000) -> List[bytes]:
        """将PCM音频数据编码为Opus帧"""
        if not HAS_OPUS:
            # 如果没有opus库，返回模拟的opus帧
            frame_size_ms = 60
            frame_size_samples = int(sample_rate * frame_size_ms / 1000)
            frame_size_bytes = frame_size_samples * 2  # 16位音频
            
            frames = []
            for i in range(0, len(pcm_data), frame_size_bytes):
                frame_data = pcm_data[i:i + frame_size_bytes]
                if len(frame_data) < frame_size_bytes:
                    # 填充最后一帧
                    frame_data += b'\x00' * (frame_size_bytes - len(frame_data))
                frames.append(frame_data)  # 直接使用PCM数据作为模拟
            
            return frames
        
        try:
            # 使用opuslib进行真实编码
            encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_VOIP)
            encoder.bitrate = 64000  # 64kbps
            
            frame_size_ms = 60
            frame_size_samples = int(sample_rate * frame_size_ms / 1000)
            frame_size_bytes = frame_size_samples * 2
            
            frames = []
            for i in range(0, len(pcm_data), frame_size_bytes):
                frame_data = pcm_data[i:i + frame_size_bytes]
                if len(frame_data) < frame_size_bytes:
                    # 填充最后一帧
                    frame_data += b'\x00' * (frame_size_bytes - len(frame_data))
                
                try:
                    opus_frame = encoder.encode(frame_data, frame_size_samples)
                    frames.append(opus_frame)
                except Exception as e:
                    logger.warning(f"Opus编码失败: {e}")
                    frames.append(frame_data)  # 使用原始数据作为备选
            
            return frames
        except Exception as e:
            logger.error(f"Opus编码器初始化失败: {e}")
            return [pcm_data]  # 返回原始数据作为单帧

    async def connect(self):
        """建立WebSocket连接 - 使用精确时间戳"""
        self.connection_start_time = self.get_precise_time()  # 使用精确时间
        try:
            self.progress.update_stage('connecting', 1)
            url = f"{self.server_url}?device-id={self.device_id}"

            self.websocket = await websockets.connect(
                url,
                ping_interval=30,
                ping_timeout=10
            )

            connection_duration = self.get_precise_time() - self.connection_start_time
            self.metrics.record_connection_time(connection_duration, True)
            self.connected = True
            # 活跃+1：连接建立
            self.progress.increment_active()
            self.progress.update_stage('connecting', -1)
            log_client_flow(f"连接成功，耗时: {connection_duration:.3f}s", self.device_id, "CONNECT")
            
        except Exception as e:
            connection_duration = self.get_precise_time() - self.connection_start_time if self.connection_start_time > 0 else 0
            error_type = type(e).__name__
            self.metrics.record_connection_time(connection_duration, False, error_type)
            self.progress.update_stage('connecting', -1)
            logger.error(f"客户端 {self.device_id} 连接失败: {e}")
            return False

        return True

    async def send_hello(self):
        """发送hello消息 - 使用精确时间戳"""
        if not self.websocket or not self.connected:
            return False

        try:
            self.progress.update_stage('hello', 1)
            self.hello_send_time = self.get_precise_time()

            hello_message = {
                "type": "hello",
                "audioParams": {
                    "format": "opus",
                    "sampleRate": 16000,
                    "channels": 1,
                    "frameDuration": 60
                }
            }

            await self.websocket.send(json.dumps(hello_message))
            self.hello_sent = True

        except Exception as e:
            logger.error(f"客户端 {self.device_id} 发送hello消息失败: {e}")
            self.progress.update_stage('hello', -1)
            return False

        return True

    async def send_detect_message(self):
        """发送唤醒词消息"""
        if not self.websocket or not self.connected:
            return False

        try:
            self.progress.update_stage('detect', 1)
            self.detect_send_time = self.get_precise_time()

            # 生成唯一的session_id
            import uuid
            session_id = str(uuid.uuid4())
            self.detect_session_id = session_id  # 保存以便错误关联

            detect_message = {
                "session_id": session_id,
                "type": "listen",
                "state": "detect", 
                "text": "你好小明"
            }

            await self.websocket.send(json.dumps(detect_message))
            self.detect_sent = True

        except Exception as e:
            logger.error(f"Detect发送失败 device={self.device_id} session_id={getattr(self, 'detect_session_id', '')} error={e}")
            self.progress.update_stage('detect', -1)
            return False

        return True

    def generate_opus_silence_frame(self, sample_rate: int = 16000, frame_duration_ms: int = 60) -> bytes:
        """生成Opus静音帧"""
        if not HAS_OPUS:
            # 如果没有opus库，返回最小的有效帧
            # Opus最小帧大小约为2-3字节
            return b'\xF8\xFF\xFE'  # Opus DTX (Discontinuous Transmission) 帧标记
        
        try:
            # 使用opuslib编码静音
            encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_VOIP)
            encoder.bitrate = 64000
            
            # 生成静音PCM数据
            frame_size_samples = int(sample_rate * frame_duration_ms / 1000)
            silent_pcm = np.zeros(frame_size_samples, dtype=np.int16).tobytes()
            
            # 编码为Opus静音帧
            opus_frame = encoder.encode(silent_pcm, frame_size_samples)
            return opus_frame
        except Exception as e:
            logger.warning(f"生成Opus静音帧失败: {e}, 使用DTX标记")
            return b'\xF8\xFF\xFE'
    
    async def send_empty_opus_frames(self):
        """发送真正的Opus静音帧，等待服务器VAD检测超时"""
        debug_logger.debug(f"🔇 客户端 {self.device_id} 开始发送Opus静音帧（{len(self.opus_silence_frame)}字节），等待服务器VAD检测（800ms超时）")
        
        # 持续发送静音帧，直到收到服务器的STT响应
        max_empty_frames = 100  # 最多发送100帧（6秒），足够VAD检测
        frame_count = 0
        empty_frame_start = self.get_precise_time()
        
        while frame_count < max_empty_frames and self.websocket:
            # 检查是否已经收到服务器的STT响应
            if hasattr(self, 'server_processing_complete') and self.server_processing_complete:
                elapsed = self.get_precise_time() - empty_frame_start
                debug_logger.debug(f"🔇 客户端 {self.device_id} 收到服务器STT响应，停止发送静音帧")
                debug_logger.debug(f"🔇 静音帧发送: {frame_count} 帧，耗时 {elapsed:.3f}s")
                break
                
            await self.websocket.send(self.opus_silence_frame)
            frame_count += 1
            
            if frame_count % 15 == 0:  # 每15帧打印一次（约0.9秒）
                elapsed = self.get_precise_time() - empty_frame_start
                debug_logger.debug(f"🔇 客户端 {self.device_id} 已发送 {frame_count} 个静音帧 ({elapsed:.3f}s)，等待VAD检测...")
            
            await asyncio.sleep(0.06)  # 保持60ms间隔
        
        total_elapsed = self.get_precise_time() - empty_frame_start
        debug_logger.debug(f"🔇 客户端 {self.device_id} 静音帧发送结束，共 {frame_count} 帧，总耗时 {total_elapsed:.3f}s")

    async def send_real_audio(self, audio_text: str):
        """发送真实音频数据（使用精确定时）"""
        logger.info(f"客户端 {self.device_id} 尝试发送真实音频: {audio_text}")
        logger.info(f"客户端 {self.device_id} 可用音频数据: {list(self.real_audio_data.keys())}")
        
        if audio_text not in self.real_audio_data:
            logger.error(f"客户端 {self.device_id} 未找到音频数据: {audio_text}")
            # 不需要更新阶段状态，因为还没有进入try块
            return False
        
        try:
            # 更新阶段状态：进入音频发送阶段
            self.progress.update_stage('audio_sending', 1)
            self.audio_sending = True
            
            pcm_data = self.real_audio_data[audio_text]
            debug_logger.debug(f"🎵 客户端 {self.device_id} PCM数据长度: {len(pcm_data)} 字节")
            opus_frames = self.encode_to_opus_frames(pcm_data)
            debug_logger.debug(f"🎵 客户端 {self.device_id} Opus帧数量: {len(opus_frames)}")
            
            # 使用精确时间戳
            send_start_time = self.get_precise_time()
            send_start_perf = time.perf_counter()
            logger.info(f"客户端 {self.device_id} 开始发送真实音频: {audio_text} ({len(opus_frames)} 帧)")
            
            # 按60ms间隔发送音频帧 - 使用基于目标时间的精确调度
            debug_logger.debug(f"🎵 客户端 {self.device_id} 开始发送 {len(opus_frames)} 个音频帧")
            frame_interval = 0.06  # 60ms
            
            for i, frame in enumerate(opus_frames):
                if self.websocket:
                    # 计算目标发送时间
                    target_time = send_start_perf + i * frame_interval
                    
                    # 发送音频帧
                    await self.websocket.send(frame)
                    
                    if i % 10 == 0:  # 每10帧打印一次进度
                        current_perf = time.perf_counter()
                        actual_elapsed = (current_perf - send_start_perf) * 1000
                        expected_elapsed = i * frame_interval * 1000
                        drift = actual_elapsed - expected_elapsed
                        debug_logger.debug(f"🎵 客户端 {self.device_id} 已发送帧 {i+1}/{len(opus_frames)}, "
                                          f"预期时间: {expected_elapsed:.1f}ms, 实际时间: {actual_elapsed:.1f}ms, "
                                          f"漂移: {drift:.1f}ms")
                    
                    # 除了最后一帧，都要等待到下一帧的目标时间
                    if i < len(opus_frames) - 1:
                        current_perf = time.perf_counter()
                        next_target = send_start_perf + (i + 1) * frame_interval
                        sleep_time = next_target - current_perf
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        elif sleep_time < -0.01:  # 如果落后超过10ms，记录警告
                            debug_logger.debug(f"⚠️ 客户端 {self.device_id} 发送落后 {-sleep_time*1000:.1f}ms")
                else:
                    debug_logger.debug(f"❌ 客户端 {self.device_id} WebSocket连接在发送第 {i+1} 帧时已断开")
                    logger.error(f"客户端 {self.device_id} WebSocket连接已断开")
                    # 更新阶段状态：退出音频发送阶段（连接断开）
                    self.progress.update_stage('audio_sending', -1)
                    self.audio_sending = False
                    return False
            
            # 【关键修改】音频帧发送完成，立即记录结束时间（在发送空帧之前）
            real_audio_end_time = self.get_precise_time()
            real_audio_send_duration = real_audio_end_time - send_start_time
            
            # 立即设置状态和时间戳，因为stt消息可能很快到达
            self.real_audio_sent = True
            self.expected_stt_text = audio_text
            self.real_audio_send_end_time = real_audio_end_time  # 这是真实的音频帧发送完成时间
            
            # 立即记录到日志（使用真实的发送完成时间）
            log_client_flow(
                f"真实音频帧发送完成: {audio_text}, 发送音频时长: {real_audio_send_duration:.3f}s (session_id={self.session_id})",
                self.device_id,
                "REAL_AUDIO_FRAMES_SENT"
            )
            
            debug_logger.debug(f"🎵 客户端 {self.device_id} 音频帧发送完成，实际耗时: {real_audio_send_duration:.3f}s")
            debug_logger.debug(f"🎵 客户端 {self.device_id} 设置real_audio_sent=True, expected_stt_text='{audio_text}', real_audio_send_end_time={real_audio_end_time}")
            debug_logger.debug(f"🎵 客户端 {self.device_id} 开始发送Opus编码的静音帧，等待服务器VAD检测（约800-900ms后触发）")
            
            # 发送空的opus数据，直到收到服务器的STT结果（VAD检测静音超时800ms）
            await self.send_empty_opus_frames()
            
            # 计算发送的总字节数（使用实际发送的opus帧大小）
            total_sent_bytes = sum(len(frame) for frame in opus_frames)
            pcm_size = len(pcm_data)
            compression_ratio = pcm_size / total_sent_bytes if total_sent_bytes > 0 else 0
            
            debug_logger.debug(f"📊 音频流量统计 - PCM: {pcm_size/1024:.1f}KB, Opus: {total_sent_bytes/1024:.1f}KB, 压缩比: {compression_ratio:.1f}:1")
            
            self.metrics.record_real_audio_send_time(real_audio_send_duration, True)
            self.metrics.record_audio_traffic_sent(self.device_id, total_sent_bytes, real_audio_send_duration)
            
            # 更新阶段状态：退出音频发送阶段
            self.progress.update_stage('audio_sending', -1)
            self.audio_sending = False
            
            logger.info(f"客户端 {self.device_id} 真实音频测试完成，音频帧发送耗时: {real_audio_send_duration:.3f}s，发送流量: {total_sent_bytes/1024:.1f}KB (PCM: {pcm_size/1024:.1f}KB)")
            return True
            
        except Exception as e:
            logger.error(f"客户端 {self.device_id} 发送真实音频失败: {e}")
            if 'send_start_time' in locals():
                send_duration = self.get_precise_time() - send_start_time
            else:
                send_duration = 0
            self.metrics.record_real_audio_send_time(send_duration, False)
            
            # 更新阶段状态：退出音频发送阶段（失败情况）
            self.progress.update_stage('audio_sending', -1)
            self.audio_sending = False
            
            return False

    async def start_real_audio_test(self):
        """开始真实音频测试（延迟1秒后发送）"""
        try:
            debug_logger.debug(f"🚀 客户端 {self.device_id} start_real_audio_test 方法被调用！")
            logger.info(f"🚀 客户端 {self.device_id} 准备开始真实音频测试，延迟1秒...")
            log_client_flow(f"开始真实音频测试，延迟1秒 (session_id={self.session_id})", self.device_id, "REAL_AUDIO_START")
            # 延迟1秒
            await asyncio.sleep(1.0)
            debug_logger.debug(f"🚀 客户端 {self.device_id} 延迟1秒完成，开始检查连接状态")
            logger.info(f"🚀 客户端 {self.device_id} 延迟结束，开始真实音频测试阶段")
            log_client_flow(f"延迟结束，开始发送真实音频 (session_id={self.session_id})", self.device_id, "REAL_AUDIO_SEND")
            
            # 检查连接状态
            is_closed = False
            try:
                # 检查连接是否关闭，不同版本的websockets库可能有不同的属性
                if hasattr(self.websocket, 'closed'):
                    is_closed = self.websocket.closed
                elif hasattr(self.websocket, 'close_code'):
                    is_closed = self.websocket.close_code is not None
                else:
                    # 尝试发送ping来检查连接状态
                    try:
                        await self.websocket.ping()
                        is_closed = False
                    except:
                        is_closed = True
            except:
                is_closed = True
                
            debug_logger.debug(f"🚀 客户端 {self.device_id} 检查连接状态: websocket={self.websocket is not None}, is_closed={is_closed}")
            
            if not self.websocket or is_closed:
                debug_logger.debug(f"❌ 客户端 {self.device_id} WebSocket连接已关闭，无法进行真实音频测试")
                logger.error(f"客户端 {self.device_id} WebSocket连接已关闭，无法进行真实音频测试")
                self.complete_test()
                return
            
            # 先发送listen start消息
            debug_logger.debug(f"🎵 客户端 {self.device_id} 发送listen start消息")
            listen_success = await self.send_listen_start()
            if not listen_success:
                debug_logger.debug(f"❌ 客户端 {self.device_id} listen start发送失败")
                self.complete_test()
                return
            
            # 短暂等待
            await asyncio.sleep(0.1)
            
            # 选择要测试的音频（这里先测试"1加一等于几"）
            test_audio = "1加一等于几"
            debug_logger.debug(f"🎵 客户端 {self.device_id} 准备发送音频: {test_audio}")
            logger.info(f"客户端 {self.device_id} 准备发送音频: {test_audio}")
            success = await self.send_real_audio(test_audio)
            debug_logger.debug(f"🎵 客户端 {self.device_id} 音频发送结果: {success}")
            
            if not success:
                logger.error(f"客户端 {self.device_id} 真实音频测试失败")
                self.complete_test()
            else:
                logger.info(f"客户端 {self.device_id} 真实音频发送成功，等待服务器响应")
                
        except Exception as e:
            debug_logger.debug(f"❌ 客户端 {self.device_id} 真实音频测试出错: {e}")
            logger.error(f"客户端 {self.device_id} 真实音频测试出错: {e}")
            import traceback
            debug_logger.debug(f"❌ 异常堆栈: {traceback.format_exc()}")
            self.complete_test()

    async def send_listen_start(self):
        """发送listen start消息"""
        if not self.websocket:
            return False

        try:
            self.listen_start_time = time.time()
            
            listen_message = {
                "type": "listen",
                "state": "start",
                "mode": "manual"
            }

            await self.websocket.send(json.dumps(listen_message))

        except Exception as e:
            logger.error(f"客户端 {self.device_id} 发送listen start失败: {e}")
            return False

        return True


    async def receive_messages(self):
        """接收和处理消息"""
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    await self.handle_text_message(message)
                else:
                    await self.handle_binary_message(message)

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"客户端 {self.device_id} 接收消息时出错: {e}")

    async def handle_text_message(self, message: str):
        """处理文本消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            log_debug(f"📨 DEBUG: 客户端 {self.device_id} 收到消息类型: {msg_type}, 内容: {data}", self.device_id)

            if msg_type == "hello":
                # hello响应 - 防止重复处理，使用精确时间戳
                if not self.hello_received:
                    # 保存服务器分配的session_id
                    self.session_id = data.get("session_id", "")
                    self.hello_receive_time = self.get_precise_time()
                    hello_duration = self.hello_receive_time - self.hello_send_time
                    self.metrics.record_hello_response_time(hello_duration, True)
                    self.hello_received = True
                    self.progress.update_stage('hello', -1)
                    logger.info(f"客户端 {self.device_id} 收到hello响应，耗时 {hello_duration:.3f}s")
                    log_client_flow(f"Hello响应成功，耗时: {hello_duration:.3f}s (session_id={self.session_id})", self.device_id, "HELLO")

            elif msg_type == "stt":
                # STT消息处理
                text = data.get("text", "")
                log_debug(f"🎯 DEBUG: 收到stt消息: text='{text}'", self.device_id)
                log_debug(f"🎯 DEBUG: real_audio_sent={self.real_audio_sent}, expected_stt_text='{self.expected_stt_text}'", self.device_id)
                log_debug(f"🎯 DEBUG: text为空？ {not text}", self.device_id)
                
                if text and not self.detect_audio_received:
                    # 这是detect流程中的STT响应，继续等待音频数据
                    pass
                elif text and not self.detect_sent:
                    # 这是原有流程的STT（暂时禁用）
                    self.stt_complete_time = self.get_precise_time()
                    stt_duration = self.stt_complete_time - self.audio_send_start_time
                    self.metrics.record_stt_time(stt_duration, True, 1.0)
                    self.stt_completed = True
                elif text and self.real_audio_sent and self.expected_stt_text:
                    # 真实音频测试的STT结果
                    log_debug(f"🎯 DEBUG: 这是真实音频测试的STT结果，开始记录", self.device_id)
                    
                    # 使用精确时间戳
                    self.stt_complete_time = self.get_precise_time()
                    self.server_stt_start_time = self.stt_complete_time  # 用于后续计算服务器处理时延
                    self.server_processing_complete = True  # 标记服务器STT处理完成，停止发送空帧
                    
                    # 记录STT准确率
                    self.metrics.record_stt_accuracy(self.expected_stt_text, text)
                    logger.info(f"客户端 {self.device_id} STT结果: 期望='{self.expected_stt_text}' 实际='{text}'")
                    
                    # 【核心指标】语音识别时延：从音频帧发送完成到收到STT结果
                    # 这包含了：空帧发送时间 + 服务器VAD检测（800ms） + 服务器STT处理时间
                    if hasattr(self, 'real_audio_send_end_time') and self.real_audio_send_end_time > 0:
                        stt_recognition_latency = self.stt_complete_time - self.real_audio_send_end_time
                        if stt_recognition_latency < 0:
                            log_debug(f"🔴 DEBUG: 客户端 {self.device_id} STT时延计算异常: "
                                    f"stt_complete_time={self.stt_complete_time}, "
                                    f"real_audio_send_end_time={self.real_audio_send_end_time}, "
                                    f"latency={stt_recognition_latency}", self.device_id)
                            stt_recognition_latency = 0  # 设置为0避免负数
                        
                        debug_logger.debug(f"🎯 语音识别时延: {stt_recognition_latency:.3f}s "
                              f"(音频帧发送完成时间={self.real_audio_send_end_time:.3f}, "
                              f"语音识别结果接收时间={self.stt_complete_time:.3f})")
                        
                        self.metrics.record_stt_time(stt_recognition_latency, True, 1.0)
                        log_client_flow(
                            f"语音识别完成: 期望='{self.expected_stt_text}' 实际='{text}', 识别时延: {stt_recognition_latency:.3f}s (音频帧发送完→收到STT结果) (session_id={self.session_id})",
                            self.device_id,
                            "STT_COMPLETE"
                        )
                    else:
                        log_debug(f"🔴 DEBUG: 客户端 {self.device_id} real_audio_send_end_time未设置或为0", self.device_id)
                        self.metrics.record_stt_time(0, True, 1.0)
                        log_client_flow(
                            f"语音识别完成: 期望='{self.expected_stt_text}' 实际='{text}', 识别时延: 0.000s (session_id={self.session_id})",
                            self.device_id,
                            "STT_COMPLETE"
                        )
                    
                    self.stt_completed = True

            elif msg_type == "tts":
                # TTS消息 - detect流程中的中间消息
                tts_state = data.get("state")
                if tts_state == "start" and self.detect_sent and not self.detect_audio_received:
                    # detect流程中的tts start消息，继续等待二进制音频数据
                    pass
                elif tts_state == "start" and self.real_audio_sent:
                    # 真实音频测试阶段的tts start，表示服务器开始处理，停止发送空帧
                    debug_logger.debug(f"🎯 收到真实音频测试的tts start，服务器开始处理")
                    self.server_processing_complete = True
                elif tts_state == "sentence_start":
                    text = data.get("text", "")
                    debug_logger.debug(f"🎯 客户端 {self.device_id} 收到sentence_start: text='{text}'")
                    debug_logger.debug(f"🎯 detect_sent={self.detect_sent}, detect_audio_received={self.detect_audio_received}")
                    debug_logger.debug(f"🎯 real_audio_sent={self.real_audio_sent}, expected_stt_text='{self.expected_stt_text}'")
                    
                    if self.detect_sent and not self.detect_audio_received:
                        # detect流程中的sentence_start消息，继续等待二进制音频数据
                        debug_logger.debug(f"🎯 这是detect流程的sentence_start，忽略")
                        pass
                    elif self.real_audio_sent and self.expected_stt_text:
                        # 真实音频测试阶段的sentence_start - 这是AI的回答，不是STT结果
                        debug_logger.debug(f"🎯 这是真实音频测试阶段的AI回答: '{text}'")
                        # STT结果会在stt消息中单独处理
                        
                        # 进入等待服务器音频响应阶段
                        self.progress.update_stage('waiting_response', 1)
                    else:
                        debug_logger.debug(f"🎯 sentence_start消息不符合任何处理条件")
                elif tts_state == "stop":
                    # 音频播放结束 - 处理detect阶段和真实音频阶段的stop信号
                    debug_logger.debug(f"🔴 客户端 {self.device_id} 收到tts stop信号")
                    debug_logger.debug(f"🔴 detect_sent={self.detect_sent}, real_audio_phase={self.real_audio_phase}, real_audio_sent={self.real_audio_sent}")
                    logger.info(f"客户端 {self.device_id} 收到tts stop信号")
                    
                    # 如果正在接收音频，先处理音频接收完成的逻辑
                    if self.audio_receiving:
                        audio_receive_duration = time.time() - self.audio_receive_start_time
                        # 记录音频播放时长
                        self.metrics.record_audio_receive_time(audio_receive_duration, success=True)
                        
                        # 如果是真实音频阶段，完成最后一个片段的统计
                        if self.real_audio_sent and self.segment_frame_count > 0:
                            avg_interval = sum(self.segment_intervals) / len(self.segment_intervals) if self.segment_intervals else 0
                            self.segment_frame_rates.append(avg_interval)
                            debug_logger.debug(f"📊 最后片段 {self.total_segments} 完成，帧数: {self.segment_frame_count}, 平均帧率: {avg_interval:.1f}ms")
                            self.completed_segments += 1
                            
                            # 输出所有片段的帧率统计
                            if self.segment_frame_rates:
                                overall_avg = sum(self.segment_frame_rates) / len(self.segment_frame_rates)
                                debug_logger.debug(f"📊 总共 {len(self.segment_frame_rates)} 个音频片段，整体平均帧率: {overall_avg:.1f}ms")
                                for i, rate in enumerate(self.segment_frame_rates, 1):
                                    status = "✓良好" if rate <= 65 else "❌延迟"
                                    debug_logger.debug(f"📊 片段{i}: {rate:.1f}ms {status}")
                        
                        # 记录音频流量统计
                        if self.total_audio_bytes > 0 and self.audio_start_time > 0:
                            total_duration = time.time() - self.audio_start_time
                            self.metrics.record_audio_traffic_received(
                                self.device_id, 
                                self.total_audio_bytes, 
                                total_duration
                            )
                        
                        self.audio_receiving = False
                        # 退出音频接收中的状态
                        self.progress.update_stage('audio_receiving', -1)
                        logger.info(f"客户端 {self.device_id} 音频接收完成，总时长 {audio_receive_duration:.3f}s，总流量 {self.total_audio_bytes} 字节")
                    
                    # 判断当前处于哪个测试阶段
                    if self.detect_sent and not self.real_audio_phase:
                        # Detect阶段的stop信号 - 进入真实音频测试阶段
                        self.real_audio_phase = True
                        logger.info(f"🎯 客户端 {self.device_id} Detect阶段完成，准备开始真实音频测试")
                        debug_logger.debug(f"🎯 客户端 {self.device_id} 即将启动真实音频测试任务")
                        log_client_flow(f"Detect阶段完成，准备开始真实音频测试 (session_id={self.session_id})", self.device_id, "DETECT_COMPLETE")
                        # 延迟1秒后发送真实音频
                        task = asyncio.create_task(self.start_real_audio_test())
                        logger.info(f"🎯 客户端 {self.device_id} 真实音频测试任务已创建: {task}")
                        
                    elif self.real_audio_phase and self.real_audio_sent:
                        # 真实音频阶段的stop信号 - 完成整个测试
                        logger.info(f"客户端 {self.device_id} 真实音频测试阶段完成，测试结束")
                        log_client_flow(f"真实音频测试阶段完成，测试结束 (session_id={self.session_id})", self.device_id, "REAL_AUDIO_COMPLETE")
                        self.complete_test()
                        
                    else:
                        # 异常情况或原有流程
                        logger.warning(f"客户端 {self.device_id} 收到tts stop，但状态异常: detect_sent={self.detect_sent}, real_audio_phase={self.real_audio_phase}, real_audio_sent={self.real_audio_sent}")
                        # 如果没有进入detect流程，可能是原有的测试流程
                        if not self.detect_sent:
                            self.progress.update_stage('waiting_response', -1)
                        else:
                            # 状态异常，直接完成测试
                            self.complete_test()

            elif msg_type == "llm":
                # LLM消息（如emotion等） - detect流程中的中间消息，继续等待音频数据
                if self.detect_sent and not self.detect_audio_received:
                    emotion = data.get("emotion", "")
                    # 记录emotion信息但不计算时延
                    pass

            elif msg_type == "start" or (msg_type == "tts" and data.get("state") == "start"):
                # 原有的start消息处理逻辑（暂时保留但不用于detect流程）
                if not self.detect_sent:  # 只有非detect流程才处理
                    current_time = time.time()
                    self.progress.update_stage('waiting_response', 1)
                    self.start_receive_time = current_time
                    
                    # 计算响应时延
                    if hasattr(self, 'audio_send_start_time') and self.audio_send_start_time > 0:
                        response_delay = self.start_receive_time - self.audio_send_start_time
                        self.metrics.record_audio_receive_time(response_delay, success=True)
                    
                    # STT到start时延
                    if self.stt_complete_time > 0:
                        stt_to_start_duration = self.start_receive_time - self.stt_complete_time
                        self.metrics.record_stt_to_start_time(stt_to_start_duration)

                    self.audio_receiving = True
                    self.audio_receive_start_time = self.start_receive_time
                    self.last_frame_time = self.audio_receive_start_time

            elif msg_type == "tts" and data.get("state") == "stop":
                # 音频播放结束 - 统一处理音频接收完成逻辑
                if self.audio_receiving:
                    audio_receive_duration = time.time() - self.audio_receive_start_time
                    self.metrics.record_audio_receive_time(audio_receive_duration)
                    self.audio_receiving = False
                    self.progress.update_stage('waiting_response', -1)
                    self.progress.update_stage('audio_receiving', -1)

            elif msg_type == "tts" and data.get("state") == "sentence_start":
                # 句子开始 - 新的音频片段开始
                text = data.get("text", "")
                if self.audio_receiving and self.real_audio_sent:
                    # 如果前一个片段还在接收，先完成前一个片段的统计
                    if self.segment_frame_count > 0:
                        avg_interval = sum(self.segment_intervals) / len(self.segment_intervals) if self.segment_intervals else 0
                        self.segment_frame_rates.append(avg_interval)
                        debug_logger.debug(f"📊 片段 {self.completed_segments + 1} 完成，帧数: {self.segment_frame_count}, 平均帧率: {avg_interval:.1f}ms")
                        self.completed_segments += 1
                    
                    # 开始新的音频片段
                    self.total_segments += 1
                    self.current_segment_start_time = time.time()
                    self.segment_frame_count = 0
                    self.segment_intervals = []
                    # 重置last_frame_time，避免计算跨片段的间隔
                    self.last_frame_time = 0
                    debug_logger.debug(f"🎵 开始接收音频片段 {self.total_segments}: '{text}'")
                elif self.audio_receiving:
                    # 普通的sentence_start处理
                    self.frame_count = 0
                    self.last_frame_time = time.time()


        except json.JSONDecodeError:
            logger.warning(f"客户端 {self.device_id} 收到无效JSON消息")

    async def handle_binary_message(self, message: bytes):
        """处理二进制消息（opus音频数据）"""
        log_debug(f"📥 收到二进制消息，大小: {len(message)} 字节", self.device_id)
        current_time = self.get_precise_time()
        audio_bytes = len(message)
        
        # 如果这是唤醒词流程的第一个音频数据包，记录唤醒词时延
        if self.detect_sent and not self.detect_audio_received:
            self.detect_audio_receive_time = current_time
            detect_duration = self.detect_audio_receive_time - self.detect_send_time
            self.metrics.record_detect_response_time(detect_duration, True)
            self.detect_audio_received = True
            self.progress.update_stage('detect', -1)
            log_client_flow(f"Detect音频响应成功，耗时: {detect_duration:.3f}s (session_id={self.session_id})", self.device_id, "DETECT")
            
            # 开始音频接收阶段，初始化帧计数和流量统计
            if not self.audio_receiving:  # 只在第一次设置
                self.audio_receiving = True
                self.audio_receive_start_time = current_time
                self.audio_start_time = current_time
                self.last_frame_time = current_time
                self.frame_count = 1  # 第一帧
                self.total_audio_bytes = audio_bytes  # 第一帧的字节数
                log_debug(f"📊 Detect首帧接收，时间基准: {current_time}", self.device_id)
                # 进入音频接收中的状态
                self.progress.update_stage('audio_receiving', 1)
            
            # 不要结束测试，继续接收后续音频帧
            return
        
        # 如果这是真实音频测试的第一个音频响应，记录两种时延
        if self.real_audio_sent and not self.audio_receiving:
            # 1. 用户感知时延：从真实音频帧发送完成到收到响应音频（包含整个识别+生成过程）
            if hasattr(self, 'real_audio_send_end_time') and self.real_audio_send_end_time > 0:
                user_perceived_duration = current_time - self.real_audio_send_end_time
                if user_perceived_duration < 0:
                    log_debug(f"🔴 DEBUG: 客户端 {self.device_id} 用户感知时延计算异常: "
                            f"current_time={current_time}, real_audio_send_end_time={self.real_audio_send_end_time}, "
                            f"duration={user_perceived_duration}", self.device_id)
                    user_perceived_duration = 0  # 设置为0避免负数
                
                self.metrics.record_audio_response_time(user_perceived_duration)
                logger.info(f"客户端 {self.device_id} 用户感知时延（音频帧发送完→收到第一帧响应音频）: {user_perceived_duration:.3f}s")
                log_client_flow(
                    f"用户感知时延: {user_perceived_duration:.3f}s (音频帧发送完→收到第一帧响应音频) (session_id={self.session_id})",
                    self.device_id,
                    "USER_PERCEIVED_LATENCY"
                )
            
            # 2. 服务器AI处理时延：从STT完成到返回音频（仅LLM+TTS时间）
            if hasattr(self, 'server_stt_start_time') and self.server_stt_start_time > 0:
                server_processing_duration = current_time - self.server_stt_start_time
                if server_processing_duration < 0:
                    log_debug(f"🔴 DEBUG: 客户端 {self.device_id} 服务器AI处理时延计算异常: "
                            f"current_time={current_time}, server_stt_start_time={self.server_stt_start_time}, "
                            f"duration={server_processing_duration}", self.device_id)
                    server_processing_duration = 0  # 设置为0避免负数
                
                self.metrics.record_server_processing_time(server_processing_duration)
                logger.info(f"客户端 {self.device_id} 服务器AI处理时延（STT完成→返回第一帧音频）: {server_processing_duration:.3f}s")
                log_client_flow(
                    f"服务器AI处理时延: {server_processing_duration:.3f}s (STT完成→返回第一帧音频, 即LLM+TTS时间) (session_id={self.session_id})",
                    self.device_id,
                    "SERVER_AI_PROCESSING_LATENCY"
                )
            
            # 开始接收真实音频测试的响应音频
            if not self.audio_receiving:  # 只在第一次设置
                self.audio_receiving = True
                self.audio_receive_start_time = current_time
                self.audio_start_time = current_time
                self.last_frame_time = current_time
                self.frame_count = 1
                self.total_audio_bytes = audio_bytes
                log_debug(f"📊 真实音频首帧接收，时间基准: {current_time}", self.device_id)
            self.progress.update_stage('waiting_response', -1)
            # 进入音频接收中的状态
            self.progress.update_stage('audio_receiving', 1)
            return
        
        # 处理后续的音频帧（detect流程和原有流程都适用）
        if self.audio_receiving:
            # 统计音频流量
            self.total_audio_bytes += audio_bytes
            
            # 计算帧间隔（只计算同一片段内的帧间隔）
            # 重新获取时间戳以确保准确性（减少函数内部处理时间的影响）
            frame_receive_time = self.get_precise_time()
            if self.last_frame_time > 0:
                interval = (frame_receive_time - self.last_frame_time) * 1000  # 转换为毫秒
                
                # 过滤异常值：帧间隔应该在合理范围内（0-1000ms）
                if 0 <= interval <= 1000:
                    # 如果是真实音频阶段，记录片段内的帧间隔
                    if self.real_audio_sent and self.segment_frame_count > 0:
                        self.segment_intervals.append(interval)
                        self.metrics.record_frame_interval(interval)
                        log_debug(f"📊 帧间隔: {interval:.1f}ms (片段{self.total_segments}, 帧{self.segment_frame_count})", self.device_id)
                    else:
                        # 对于detect阶段，记录所有帧间隔
                        self.metrics.record_frame_interval(interval)
                        log_debug(f"📊 Detect帧间隔: {interval:.1f}ms (帧{self.frame_count})", self.device_id)
                else:
                    # 记录异常值用于调试
                    log_debug(f"🔴 DEBUG: 客户端 {self.device_id} 检测到异常帧间隔: {interval:.1f}ms (当前时间: {frame_receive_time}, 上次时间: {self.last_frame_time})", self.device_id)

            self.last_frame_time = frame_receive_time
            self.frame_count += 1
            
            # 片段级别的帧计数
            if self.real_audio_sent:
                self.segment_frame_count += 1
            
            # 计算当前音频速率并更新到metrics
            if self.audio_start_time > 0:
                duration = current_time - self.audio_start_time
                if duration > 0:
                    current_rate = self.total_audio_bytes / duration  # 字节/秒
                    self.metrics.update_current_audio_rate(current_rate)

    def reset_for_next_round(self):
        """重置客户端状态以进行下一轮测试"""
        self.session_id = ""
        self.websocket = None
        
        # 重置状态
        self.connected = False
        self.hello_sent = False
        self.hello_received = False
        self.detect_sent = False
        self.detect_audio_received = False
        self.test_completed = False
        self.audio_sending = False
        self.audio_receiving = False
        self.has_failed = False
        
        # 重置时间戳
        self.connection_start_time = 0
        self.hello_send_time = 0
        self.hello_receive_time = 0
        self.detect_send_time = 0
        self.detect_audio_receive_time = 0
        self.audio_send_start_time = 0
        self.audio_send_end_time = 0
        self.stt_complete_time = 0
        self.start_receive_time = 0
        self.audio_receive_start_time = 0
        
        # 重置计数器
        self.last_frame_time = 0
        self.frame_count = 0
        self.current_segment_start_time = 0
        self.segment_frame_count = 0
        self.segment_intervals = []
        self.total_segments = 0
        self.completed_segments = 0
        self.segment_frame_rates = []
        self.total_audio_bytes = 0
        self.audio_start_time = 0
        
        # 重置真实音频测试状态
        self.real_audio_phase = False
        self.real_audio_sent = False
        self.real_audio_send_end_time = 0
        self.expected_stt_text = ""
        self.server_processing_complete = False
        self.server_stt_start_time = 0
        
        # 更新性能计数器基准时间
        self.perf_counter_base = time.perf_counter()
        self.time_base = time.time()

    async def run_test(self):
        """运行完整测试流程"""
        try:
            # 1. 连接
            if not await self.connect():
                self.progress.increment_failed()
                self.has_failed = True
                return

            # 2. 发送hello消息
            if not await self.send_hello():
                self.progress.increment_failed()
                self.has_failed = True
                return

            # 启动消息接收任务
            receive_task = asyncio.create_task(self.receive_messages())

            # 等待hello响应
            timeout = 10
            start_time = time.time()
            while not self.hello_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            if not self.hello_received:
                hello_duration = time.time() - self.hello_send_time if self.hello_send_time > 0 else timeout
                self.metrics.record_hello_response_time(hello_duration, False, timeout=True)
                self.progress.increment_failed()
                self.has_failed = True
                logger.warning(f"客户端 {self.device_id} Hello超时，耗时 {hello_duration:.3f}s")
                return

            # 3. 发送detect消息（新的测试流程）
            # 在hello后短暂延迟，避免过快导致服务器未就绪
            await asyncio.sleep(0.1)
            if not await self.send_detect_message():
                self.progress.increment_failed()
                self.has_failed = True
                return

            # 4. 等待detect音频响应和完整的音频播放
            timeout = 60  # 增加超时时间，因为要等待完整音频
            start_time = time.time()
            
            # 首先等待detect音频开始
            while not self.detect_audio_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            # 如果detect超时，记录失败
            if not self.detect_audio_received:
                detect_duration = time.time() - self.detect_send_time
                self.metrics.record_detect_response_time(detect_duration, False, timeout=True)
                logger.error(f"Detect超时 device={self.device_id} session_id={getattr(self, 'detect_session_id', '')} duration={detect_duration:.3f}s reason=no_audio_started")
                self.metrics.record_detect_error(self.device_id, getattr(self, 'detect_session_id', ''), 'timeout_no_audio_started', detect_duration)
                log_client_flow(f"Detect超时: session_id={getattr(self, 'detect_session_id', '')}, 等待音频开始超过阈值 (session_id={self.session_id})", self.device_id, "DETECT_ERROR")
                self.progress.increment_failed()
                self.has_failed = True
                return
            
            # detect成功，现在需要等待完整的测试流程完成
            # 包括：detect音频播放完成 -> 真实音频测试 -> 真实音频响应完成
            
            # 等待整个测试完成（包括真实音频测试阶段）
            total_timeout = 120  # 总超时时间增加到2分钟，包含真实音频测试
            test_start_time = time.time()
            
            while not self.test_completed and (time.time() - test_start_time) < total_timeout:
                await asyncio.sleep(0.1)
            
            # 如果测试超时，强制完成
            if not self.test_completed:
                logger.warning(f"客户端 {self.device_id} 测试总超时，强制完成")
                if self.audio_receiving:
                    # 如果还在接收音频，记录超时
                    audio_receive_duration = time.time() - self.audio_receive_start_time if hasattr(self, 'audio_receive_start_time') else 0
                    self.metrics.record_audio_receive_time(audio_receive_duration, success=False, timeout=True)
                    self.audio_receiving = False
                self.complete_test()

            # 取消接收任务
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass

            # 这里不需要调用完成，因为已经在tts stop消息中处理了

        except Exception as e:
            logger.error(f"客户端 {self.device_id} 测试过程中出错: {e}")
            if not self.test_completed:
                self.progress.increment_failed()
                self.has_failed = True
        finally:
            # 取消接收任务
            if 'receive_task' in locals() and not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭连接
            if self.websocket:
                try:
                    await self.websocket.close()
                    logger.info(f"客户端 {self.device_id} 连接已关闭")
                except:
                    pass
            # 活跃-1：连接关闭
            self.progress.decrement_active()
            # 如果未标记完成且未失败，则视为正常完成
            if not self.test_completed and not self.has_failed:
                self.complete_test()

