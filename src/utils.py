"""
工具函数 - 音频处理
"""
import wave
import io
import numpy as np
from .config import (
    AUDIO_SAMPLE_RATE, 
    AUDIO_CHANNELS, 
    AUDIO_FRAME_DURATION_MS, 
    AUDIO_FRAME_SIZE,
    HAS_OPUS
)

if HAS_OPUS:
    import opuslib


def load_audio_file(file_path: str) -> bytes:
    """加载音频文件并转换为PCM数据"""
    try:
        with wave.open(file_path, 'rb') as wf:
            if wf.getnchannels() != AUDIO_CHANNELS:
                raise ValueError(f"音频文件通道数必须为{AUDIO_CHANNELS}")
            if wf.getframerate() != AUDIO_SAMPLE_RATE:
                raise ValueError(f"音频文件采样率必须为{AUDIO_SAMPLE_RATE}Hz")
            
            pcm_data = wf.readframes(wf.getnframes())
            return pcm_data
    except Exception as e:
        raise Exception(f"加载音频文件失败: {e}")


def generate_sine_wave_audio(duration_ms: int = 1000, frequency: int = 440) -> bytes:
    """生成正弦波音频数据（PCM格式）"""
    num_samples = int(AUDIO_SAMPLE_RATE * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, num_samples, False)
    
    # 生成正弦波
    audio_signal = np.sin(2 * np.pi * frequency * t) * 32767
    audio_signal = audio_signal.astype(np.int16)
    
    # 转换为bytes
    return audio_signal.tobytes()


def pcm_to_opus(pcm_data: bytes, frame_size: int = AUDIO_FRAME_SIZE) -> bytes:
    """将PCM数据编码为Opus格式
    
    Args:
        pcm_data: PCM音频数据
        frame_size: 每帧的样本数
    
    Returns:
        Opus编码后的音频数据
    """
    if not HAS_OPUS:
        # 如果没有opuslib，返回原始PCM数据（用于测试）
        return pcm_data
    
    try:
        # 创建Opus编码器
        encoder = opuslib.Encoder(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, opuslib.APPLICATION_VOIP)
        
        # 将PCM数据编码为Opus
        opus_frames = []
        pcm_array = np.frombuffer(pcm_data, dtype=np.int16)
        
        # 按帧编码
        for i in range(0, len(pcm_array), frame_size):
            frame = pcm_array[i:i + frame_size]
            if len(frame) < frame_size:
                # 最后一帧不足，进行填充
                frame = np.pad(frame, (0, frame_size - len(frame)), mode='constant')
            
            # 编码这一帧
            encoded_frame = encoder.encode(frame.tobytes(), frame_size)
            opus_frames.append(encoded_frame)
        
        # 合并所有帧
        return b''.join(opus_frames)
    
    except Exception as e:
        raise Exception(f"Opus编码失败: {e}")


def opus_to_pcm(opus_data: bytes, frame_size: int = AUDIO_FRAME_SIZE) -> bytes:
    """将Opus数据解码为PCM格式
    
    Args:
        opus_data: Opus编码的音频数据
        frame_size: 每帧的样本数
    
    Returns:
        PCM音频数据
    """
    if not HAS_OPUS:
        # 如果没有opuslib，返回原始数据（用于测试）
        return opus_data
    
    try:
        # 创建Opus解码器
        decoder = opuslib.Decoder(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS)
        
        # 解码（这里需要按包解码，简化实现）
        pcm_data = decoder.decode(opus_data, frame_size)
        return pcm_data
    
    except Exception as e:
        raise Exception(f"Opus解码失败: {e}")


def save_pcm_as_wav(pcm_data: bytes, output_path: str):
    """将PCM数据保存为WAV文件"""
    try:
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(AUDIO_CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(AUDIO_SAMPLE_RATE)
            wf.writeframes(pcm_data)
    except Exception as e:
        raise Exception(f"保存WAV文件失败: {e}")


def calculate_audio_duration(audio_data: bytes) -> float:
    """计算音频数据的时长（秒）"""
    # 假设是16-bit PCM
    num_samples = len(audio_data) // 2  # 2 bytes per sample (16-bit)
    duration = num_samples / AUDIO_SAMPLE_RATE
    return duration

