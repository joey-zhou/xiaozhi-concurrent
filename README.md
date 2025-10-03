# Xiaozhi WebSocket 并发测试工具

WebSocket 并发测试工具，用于测试 Xiaozhi 服务的性能和稳定性。

## 📌 项目说明

本项目是为 **[Xiaozhi ESP32 Server Java](https://github.com/joey-zhou/xiaozhi-esp32-server-java)** 开发的并发测试工具。

### 关于 Xiaozhi ESP32 Server Java

**Xiaozhi ESP32 Server Java** 是基于 Xiaozhi ESP32 项目开发的 Java 版本服务端，包含完整的前后端管理平台。该项目旨在为用户提供一个功能丰富、操作便捷的管理界面，帮助用户更好地管理设备、配置等。

考虑到企业级应用场景的需求，Java 作为一种成熟的企业级开发语言，具备更完善的生态系统支持和更强大的并发处理能力，因此我们选择开发这个 Java 版本的服务端，为项目提供更多可能性和扩展空间。

**技术栈：**
- 后端框架：Spring Boot + Spring MVC
- 前端框架：Vue.js + Ant Design
- 数据存储：MySQL + Redis
- 全局响应式：适配各种设备及分辨率

**项目地址：** [https://github.com/joey-zhou/xiaozhi-esp32-server-java](https://github.com/joey-zhou/xiaozhi-esp32-server-java)

## ✨ 特性

- 🚀 **高并发测试**：支持高并发 WebSocket 连接
- 📊 **详细指标**：连接时延、语音识别时延、音频响应时延等全方位指标
- 📈 **实时监控**：实时显示进度条和测试状态
- 📉 **可视化报告**：自动生成性能分布图表
- 🔍 **详细日志**：分级日志系统，便于调试和问题追踪
- 🎯 **模块化设计**：清晰的代码结构，易于维护和扩展

## 📁 项目结构

```
xiaozhi-concurrent/
├── src/                      # 源代码目录
│   ├── __init__.py          # 包初始化
│   ├── config.py            # 配置和常量
│   ├── logger.py            # 日志配置
│   ├── progress.py          # 进度跟踪
│   ├── metrics.py           # 测试指标收集
│   ├── client.py            # WebSocket 测试客户端
│   ├── tester.py            # 并发测试器
│   └── utils.py             # 工具函数
├── run_test.py              # 主入口文件（推荐使用）
├── xiaozhi_test.py          # 单文件版本
├── requirements.txt         # 依赖包列表
├── README.md                # 本文档
└── logs/                    # 日志和输出目录（自动创建）
    ├── xiaozhi_debug_*.log          # 调试日志
    ├── xiaozhi_client_flow_*.log    # 客户端流程日志
    └── xiaozhi_client_flow_sorted_*.log  # 按设备排序的流程日志
```

## 📦 安装

### 1. 克隆或下载项目

```bash
cd ~/documents
git clone <repository-url> xiaozhi-concurrent
cd xiaozhi-concurrent
```

### 2. 安装依赖

**方法 A：使用 pip**
```bash
pip install -r requirements.txt
```

**方法 B：使用 conda（推荐）**
```bash
conda create -n test python=3.9
conda activate test
pip install -r requirements.txt
```

### 3. 依赖说明

必需依赖：
- `websockets` - WebSocket 客户端
- `numpy` - 数值计算
- `psutil` - 系统监控

可选依赖：
- `matplotlib` - 图表可视化（强烈推荐）
- `opuslib` - Opus 音频编解码（如需真实音频测试）

## 🚀 快速开始

### 基础使用

```bash
# 使用默认参数运行测试（100个客户端，20并发）
conda activate test
python run_test.py

# 或使用单文件版本
python xiaozhi_test.py
```

### 自定义参数

```bash
# 指定服务器地址和客户端数量
python run_test.py --server ws://192.168.1.100:8091/ws/xiaozhi/v1/ --clients 200 --concurrency 40

# 使用自定义音频文件
python run_test.py --audio test_audio.wav --clients 50

```

### 查看帮助

```bash
python run_test.py --help
```

## 📊 输出说明

### 实时显示

测试运行时会显示：
- **进度条**：测试完成进度和预计剩余时间
- **状态统计**：各阶段客户端数量（连接中、Hello、唤醒词、音频发送、音频接收等）
- **性能指标**：连接成功率、Hello成功率、唤醒词成功率和时延、音频帧率等

### 日志文件

所有日志保存在 `logs/` 目录：

1. **xiaozhi_debug_[timestamp].log** - 详细调试日志
   - 每个客户端的详细操作记录
   - 错误和异常信息
   
2. **xiaozhi_client_flow_[timestamp].log** - 客户端流程日志
   - 按时间顺序的流程记录
   - 精确到毫秒的时间戳

3. **xiaozhi_client_flow_sorted_[timestamp].log** - 按设备排序的流程日志
   - 按设备ID分组，便于查看单个客户端的完整流程

### 性能报告

测试完成后会显示详细的性能统计：

```
+==========+===================+==========+
| 指标     | 成功率/计数       | 平均耗时 |
+==========+===================+==========+
| 连接     | 100.00% (100/100) | 0.154s   |
| Hello    | 100.00% (100/100) | 0.184s   |
| 唤醒词   | 100.00% (100/100) | 0.459s   |
| 音频接收 | 成功200, 超时0    | -        |
+----------+-------------------+----------+
+==============+=============================+
| 音频帧率统计 | 值                          |
+==============+=============================+
| 平均间隔     | 59.60ms                     |
| 质量         | 良好 (673/8321 延迟, 8.09%) |
| 范围         | 最小0.1ms / 最大762.0ms     |
+--------------+-----------------------------+
+==============+=============================+
| 音频流量统计 | 值                          |
+==============+=============================+
| 接收/发送/总 | 0.98MB / 0.85MB / 1.82MB    |
| 平均每客户端 | 接收0.00MB / 发送0.01MB     |
| 平均速率     | 接收10.6kbps / 发送69.5kbps |
| 峰值速率     | 接收15.2kbps / 发送69.6kbps |
+--------------+-----------------------------+
+================+======================================+
| 真实音频测试   | 值                                   |
+================+======================================+
| 发送成功率     | 100.00% (100 次)                     |
| 语音识别准确率 | 100.00% (100/100)                    |
| 发送音频时长   | 1.021s                               |
| 语音识别时延   | 均值0.952s / 最小0.926s / 最大0.995s |
| 服务器处理     | 均值0.816s / 最小0.543s / 最大1.463s |
| 用户感知       | 均值1.767s / 最小1.499s / 最大2.431s |
+----------------+--------------------------------------+
```

### 可视化图表

如果安装了 matplotlib，会自动生成：

**xiaozhi_latency_dist_[timestamp].png** - 延迟分布直方图
- 连接时延分布
- Hello响应时延分布
- 唤醒词响应时延分布
- 用户感知时延分布

## 🔧 配置说明

### 配置文件：`src/config.py`

```python
# WebSocket 配置
DEFAULT_SERVER_URL = "ws://localhost:8091/ws/xiaozhi/v1/"
DEFAULT_CLIENTS = 20
DEFAULT_CONCURRENCY = 20

# 音频配置
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FRAME_DURATION_MS = 60
```

可根据需要修改这些默认值。

## 💡 使用技巧

### 1. 压力测试建议

- 逐步增加并发数，观察系统表现
- 建议从小规模开始：`--clients 10 --concurrency 5`
- 根据服务器性能调整：
  - 小型测试：`--clients 50 --concurrency 10`
  - 中型测试：`--clients 100 --concurrency 20`
  - 大型测试：`--clients 500 --concurrency 50`

### 2. 调试技巧

查看详细日志：
```bash
# 实时查看调试日志
tail -f logs/xiaozhi_debug_*.log

# 按客户端分析流程
grep "xiaozhi-test-000001" logs/xiaozhi_client_flow_sorted_*.log

# 查看失败的客户端
grep -i "失败\|超时\|error" logs/xiaozhi_debug_*.log
```

## 🐛 常见问题

### Q1: matplotlib 中文显示问题

**A:** 安装中文字体
```bash
# Ubuntu/Debian
sudo apt-get install fonts-wqy-microhei

# macOS
# 系统已自带中文字体
```

## 📈 模块说明

### client.py - WebSocket 客户端

单个客户端的完整测试流程：
- 建立 WebSocket 连接
- 发送 Hello 握手
- 发送唤醒词探测
- 发送音频数据
- 接收和统计响应

### tester.py - 并发测试器

管理多个客户端的并发测试：
- 控制并发数量
- 收集汇总指标
- 生成测试报告
- 实时显示进度

### metrics.py - 指标收集

收集和统计各类性能指标：
- 连接时延
- 各阶段响应时延
- 成功率和失败率
- 音频流量统计

### progress.py - 进度跟踪

测试进度和状态：
- 进度条显示
- 各阶段统计
- 完成/失败计数

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

[MIT License](LICENSE)

---

**版本**: 2.0.0  
**最后更新**: 2025-10-03
