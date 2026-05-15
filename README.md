# ScrcpyGame

基于 Scrcpy 的 Android 游戏自动化测试与录制工具，支持 AI 辅助场景识别、点击事件录制回放、YOLO 目标检测模型训练。

## 功能特性

- **设备连接**：通过 ADB 或 IP 连接 Android 设备
- **视频录制**：自动录制操作视频并保存截图
- **事件录制**：记录点击、滑动等操作及前后截图
- **场景识别**：基于哈希索引 + AI 视觉的场景分类
- **YOLO 训练**：支持自定义目标检测模型训练
- **规则管理**：运行时规则配置与执行
- **视频回放**：录制事件可视化回放

## 项目结构

```
ScrcpyGame/
├── analysis/              # AI 分析模块
│   ├── yolo_detection.py      # YOLO 检测
│   ├── llm_click_description.py  # LLM 点击描述
│   └── reanalyze_*.py         # 重新分析流程
├── data/                  # 数据层
│   ├── agent_schema.py        # 数据目录结构
│   └── event_store.py         # 事件存储
├── domain/                # 领域模型
│   └── coordinate_mapper.py   # 坐标映射
├── repositories/          # 数据仓库
├── services/              # 服务层
│   ├── device_connection.py    # 设备连接
│   ├── frame_capture.py       # 帧捕获
│   └── recording_event_service.py  # 录制服务
├── ui/                    # UI 层
│   ├── panels/               # 功能面板
│   └── dialogs/              # 对话框
├── tests/                  # 单元测试
├── main.py                 # 应用入口
├── llm_client.py           # LLM 客户端
└── execution_engine.py     # 执行引擎
```

## 环境要求

- Python 3.10+
- Android SDK / ADB
- Scrcpy
- PySide6
- 依赖包见 `requirements.txt`

## 安装

1. 克隆项目：
```bash
git clone <repo-url>
cd ScrcpyGame
```

2. 创建虚拟环境：
```bash
python -m venv venv
.\venv\Scripts\activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

## 运行

```bash
python main.py
```

## 测试

```bash
python -m pytest tests/ -v
```

## 配置说明

环境变量配置（`.env`）：

| 变量名 | 说明 | 必需 |
|--------|------|------|
| OFOX_API_KEY | ofox.ai API Key | 是 |
| DASHSCOPE_API_KEY | 阿里云 DashScope API Key | 是 |
| DEEPSEEK_API_KEY | DeepSeek API Key | 是 |
| SCRCPY_MAX_WIDTH | Scrcpy 最大宽度 | 否 |
| SCRCPY_MAX_FPS | Scrcpy 最大帧率 | 否 |

## 使用指南

### 1. 连接设备
- 通过 ADB USB 连接：刷新设备列表，选择设备连接
- 通过 IP 连接：输入设备 IP 地址连接

### 2. 开始录制
1. 点击「执行」按钮开始录制
2. 在设备上进行操作
3. 点击「停止」结束录制

### 3. 审核事件
1. 切换到「审核」面板
2. 查看录制的事件列表
3. 修正场景分类和点击目标
4. 批准或删除事件

### 4. 训练 YOLO 模型
1. 在审核面板中标记事件
2. 点击「训练」开始模型训练
3. 训练完成后自动更新检测模型

## 开发指南

### 添加新测试
```python
# tests/test_example.py
import pytest

def test_example():
    assert True
```

### 异常处理规范
项目使用自定义异常基类 `ScrcpyGameError`，优先捕获具体异常类型：
```python
from exceptions import ScrcpyGameError, DeviceConnectionError

try:
    connect_device()
except DeviceConnectionError as e:
    handle_error(e)
except ScrcpyGameError:
    raise
```

## 许可证

MIT License