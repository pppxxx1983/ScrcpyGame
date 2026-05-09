# 游戏 AI Agent 数据采集与场景识别架构设计文档

## 1. 项目目标

构建一套用于手游 AI Agent 的：

- 游戏画面识别系统
- 场景指纹系统
- OCR/UI识别系统
- 用户点击行为学习系统
- Scene Graph（场景图）系统
- 自动化操作系统

最终目标：

```text
通过录制玩家行为
自动学习游戏如何操作
```

---

# 2. 系统总体架构

```text
游戏画面
    ↓
录屏/截图
    ↓
Scene识别
    ↓
OCR/UI检测
    ↓
记录用户点击
    ↓
状态转移分析
    ↓
Scene Graph
    ↓
AI Agent 自动操作
```

---

# 3. 数据采集方案

## 3.1 录屏数据

推荐：

```text
有损视频
+ 点击前后无损截图
```

原因：

| 数据 | 用途 |
|---|---|
| 有损录像 | 行为回放、流程分析 |
| 点击前无损图 | 场景识别、OCR、训练 |
| 点击后无损图 | 状态转移分析 |
| 点击坐标 | 行为学习 |

---

## 3.2 推荐保存时机

每次用户点击：

保存：

```text
点击前 100~300ms
点击后 300ms
点击后 800ms
点击后 1500ms（可选）
```

原因：

很多游戏存在：

- 点击动画
- Loading
- 特效
- 转场

不能立即截取 after 图。

---

# 4. 文件目录结构

推荐：

```text
game_agent_data/
├── games/
│   └── my_game/
│       ├── raw_videos/
│       │   └── 20260509_001.mp4
│       │
│       ├── sessions/
│       │   └── 20260509_001/
│       │       ├── clicks/
│       │       │   ├── click_000001_before.png
│       │       │   ├── click_000001_after_300ms.png
│       │       │   ├── click_000001_after_800ms.png
│       │       │   └── click_000001.json
│       │       │
│       │       ├── frames/
│       │       └── session.json
│       │
│       ├── scenes/
│       │   ├── main_city/
│       │   │   ├── samples/
│       │   │   └── scene.json
│       │   │
│       │   └── shop/
│       │
│       ├── labels/
│       ├── crops/
│       └── agent.db
```

---

# 5. Scene 场景系统

## 5.1 Scene 的定义

一个 Scene 代表：

```text
一个稳定的游戏界面状态
```

例如：

```text
main_city
shop
bag
battle
popup_reward
```

---

## 5.2 Scene 核心结构

推荐：

```json
{
  "scene": "main_city",

  "hash": {
    "full": "xxxx",
    "top": "xxxx",
    "bottom": "xxxx",
    "center": "xxxx"
  },

  "ocr": [
    "商城",
    "活动",
    "背包"
  ],

  "actions": [
    {
      "name": "open_shop",
      "x": 900,
      "y": 1600,
      "next_scene": "shop"
    }
  ]
}
```

---

# 6. 指纹（Hash）系统

## 6.1 为什么不能只用整图 hash

因为游戏存在：

- 动态角色
- 飘字
- 特效
- 动画
- 弹窗
- 红点

会导致整图变化。

---

## 6.2 推荐使用区域 hash

推荐区域：

```text
顶部资源栏
底部菜单栏
左侧任务栏
右侧活动栏
中心弹窗区
```

---

## 6.3 推荐 Hash 算法

推荐：

```text
pHash
+dHash
```

用于：

```text
快速判断是否是同一个界面
```

---

## 6.4 推荐匹配流程

```text
全图 hash
    ↓
顶部区域 hash
    ↓
底部区域 hash
    ↓
OCR 校验
    ↓
最终判定 scene
```

---

# 7. OCR 系统

## 7.1 推荐 OCR

推荐：

```text
RapidOCR
PaddleOCR
```

---

## 7.2 OCR 的作用

OCR 负责：

```text
识别文字
识别文字框
识别数字
识别按钮标题
```

不是负责：

```text
复杂语义理解
```

---

## 7.3 OCR 输出结构

```json
[
  {
    "text": "开始游戏",
    "score": 0.99,
    "box": [100, 200, 300, 240]
  }
]
```

---

# 8. 用户点击行为系统

## 8.1 核心思想

```text
画面 = 状态
点击 = 行为
```

AI Agent 本质：

```text
(state) -> (action)
```

---

## 8.2 点击记录结构

```json
{
  "before_scene": "main_city",
  "click": [820, 1550],
  "after_scene": "shop"
}
```

---

# 9. Scene Graph（场景图）

## 9.1 核心结构

```text
main_city
 ├── 点击商城 → shop
 ├── 点击背包 → bag
 └── 点击活动 → event
```

---

## 9.2 Scene Graph 的价值

Scene Graph 可以：

- 自动导航
- 自动返回
- 自动寻找路径
- 自动探索界面
- 自动生成行为树

---

# 10. 数据库存储方案

推荐：

```text
SQLite
```

原因：

- 简单
- 单文件
- 易调试
- 足够第一版使用

---

# 11. 推荐数据库结构

## 11.1 scene

```sql
CREATE TABLE scene (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 11.2 scene_sample

```sql
CREATE TABLE scene_sample (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER,
    image_path TEXT,
    width INTEGER,
    height INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 11.3 scene_hash

```sql
CREATE TABLE scene_hash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER,

    region_name TEXT,

    box_x1 INTEGER,
    box_y1 INTEGER,
    box_x2 INTEGER,
    box_y2 INTEGER,

    phash TEXT,
    dhash TEXT,

    weight REAL DEFAULT 1.0
);
```

---

## 11.4 ocr_result

```sql
CREATE TABLE ocr_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER,

    text TEXT,
    score REAL,

    box_x1 INTEGER,
    box_y1 INTEGER,
    box_x2 INTEGER,
    box_y2 INTEGER
);
```

---

## 11.5 action

```sql
CREATE TABLE action (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    from_scene_id INTEGER,
    to_scene_id INTEGER,

    action_name TEXT,

    x INTEGER,
    y INTEGER,

    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0
);
```

---

# 12. 推荐第一版实现路线

## 阶段 1

实现：

```text
截图
+ hash
+ OCR
+ 点击记录
```

---

## 阶段 2

实现：

```text
Scene 自动识别
```

---

## 阶段 3

实现：

```text
Scene Graph
```

---

## 阶段 4

实现：

```text
自动点击
自动返回
自动导航
```

---

## 阶段 5

实现：

```text
YOLO/UI检测
```

---

## 阶段 6

实现：

```text
大模型 UI 理解
```

例如：

- Qwen-VL
- UI-TARS
- GPT-4.1/4o

---

# 13. 最终目标架构

```text
游戏画面
    ↓
Scene识别
    ↓
UI树构建
    ↓
Scene Graph
    ↓
LLM规划
    ↓
Agent自动操作
```

最终形成：

```text
游戏UI DOM树
```

AI Agent 不再是在图片上乱点。

而是在：

```text
结构化UI系统
```

上操作。

---

# 14. 文件保存结构设计

## 14.1 推荐目录结构

```text
game_agent_data/
├── games/
│   └── my_game/
│       ├── raw_videos/
│       │   └── 20260509_001.mp4
│       │
│       ├── sessions/
│       │   └── 20260509_001/
│       │       ├── clicks/
│       │       │   ├── click_000001_before.png
│       │       │   ├── click_000001_after_300ms.png
│       │       │   ├── click_000001_after_800ms.png
│       │       │   └── click_000001.json
│       │       │
│       │       ├── frames/
│       │       └── session.json
│       │
│       ├── scenes/
│       │   ├── main_city/
│       │   │   ├── samples/
│       │   │   │   ├── main_city_001.png
│       │   │   │   └── main_city_002.png
│       │   │   └── scene.json
│       │   │
│       │   └── shop/
│       │
│       ├── labels/
│       ├── crops/
│       └── agent.db
```

---

## 14.2 clicks 目录说明

每次点击保存：

```text
before.png
after_300ms.png
after_800ms.png
click.json
```

其中：

| 文件 | 用途 |
|---|---|
| before.png | 当前 Scene 识别 |
| after_300ms.png | UI状态变化分析 |
| after_800ms.png | 最终状态确认 |
| click.json | 行为记录 |

---

## 14.3 click.json 结构

```json
{
  "session_id": "20260509_001",
  "click_index": 1,
  "timestamp_ms": 123456,

  "click": {
    "x": 820,
    "y": 1550
  },

  "before_image": "click_000001_before.png",

  "after_images": [
    "click_000001_after_300ms.png",
    "click_000001_after_800ms.png"
  ],

  "before_scene": "main_city",
  "after_scene": "shop"
}
```

---

# 15. 图片初筛 JSON 结构

## 15.1 初筛目标

用于：

```text
快速识别当前 Scene
```

不进行复杂 AI 推理。

---

## 15.2 初筛流程

```text
截图
 ↓
生成 hash
 ↓
OCR
 ↓
生成 fingerprint json
 ↓
和库内 scene 对比
```

---

## 15.3 fingerprint.json 示例

```json
{
  "image": "screen_001.png",

  "hash": {
    "full_phash": "a1b2c3d4",
    "top_phash": "99887766",
    "bottom_phash": "11223344",
    "center_phash": "55667788"
  },

  "ocr": [
    {
      "text": "商城",
      "score": 0.98,
      "box": [820, 1500, 980, 1650]
    },
    {
      "text": "活动",
      "score": 0.93,
      "box": [700, 120, 860, 220]
    }
  ],

  "meta": {
    "width": 1080,
    "height": 1920,
    "device": "android"
  }
}
```

---

## 15.4 Scene 匹配逻辑

推荐：

```text
full_hash
+ top_hash
+ bottom_hash
+ OCR文本
```

综合打分。

---

## 15.5 推荐阈值

```text
score >= 0.80    命中 Scene
0.60~0.80        疑似 Scene
< 0.60           Unknown Scene
```

---

# 16. Unknown Scene 处理流程

## 16.1 Unknown Scene 定义

当：

```text
hash不匹配
OCR不匹配
```

则认为：

```text
未知界面
```

---

## 16.2 Unknown Scene 处理流程

```text
Unknown Scene
    ↓
向量检索
    ↓
仍然失败
    ↓
问 VL 大模型
    ↓
自动生成弱标签
    ↓
自动入库
```

---

## 16.3 推荐大模型输出结构

```json
{
  "scene_name": "reward_popup",

  "elements": [
    {
      "type": "button",
      "name": "confirm",
      "text": "确定",
      "box": [700, 1450, 950, 1600],
      "confidence": 0.82
    },
    {
      "type": "close_button",
      "name": "close",
      "text": "X",
      "box": [960, 120, 1030, 190],
      "confidence": 0.76
    }
  ]
}
```

---

# 17. 推荐完整数据库结构

## 17.1 session

```sql
CREATE TABLE session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_key TEXT,
    game_name TEXT,

    video_path TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 17.2 scene

```sql
CREATE TABLE scene (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT,
    description TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 17.3 scene_sample

```sql
CREATE TABLE scene_sample (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    scene_id INTEGER,

    image_path TEXT,

    width INTEGER,
    height INTEGER,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 17.4 scene_hash

```sql
CREATE TABLE scene_hash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    sample_id INTEGER,

    region_name TEXT,

    box_x1 INTEGER,
    box_y1 INTEGER,
    box_x2 INTEGER,
    box_y2 INTEGER,

    phash TEXT,
    dhash TEXT,
    ahash TEXT,

    weight REAL DEFAULT 1.0
);
```

---

## 17.5 ocr_result

```sql
CREATE TABLE ocr_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    sample_id INTEGER,

    text TEXT,
    score REAL,

    box_x1 INTEGER,
    box_y1 INTEGER,
    box_x2 INTEGER,
    box_y2 INTEGER
);
```

---

## 17.6 click_event

```sql
CREATE TABLE click_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id INTEGER,

    index_no INTEGER,

    timestamp_ms INTEGER,

    x INTEGER,
    y INTEGER,

    before_image TEXT,
    after_300ms_image TEXT,
    after_800ms_image TEXT,

    before_scene_id INTEGER,
    after_scene_id INTEGER
);
```

---

## 17.7 action

```sql
CREATE TABLE action (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    from_scene_id INTEGER,
    to_scene_id INTEGER,

    action_name TEXT,

    x INTEGER,
    y INTEGER,

    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0
);
```

---

## 17.8 ui_element（后续扩展）

```sql
CREATE TABLE ui_element (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    scene_id INTEGER,

    element_type TEXT,
    element_name TEXT,

    text TEXT,

    x1 INTEGER,
    y1 INTEGER,
    x2 INTEGER,
    y2 INTEGER,

    source TEXT,

    confidence REAL
);
```

其中：

```text
source:
ocr
cv
yolo
vlm
human
```

---

# 18. 第一版建议

不要一开始就：

- 强化学习
- 超大模型
- 自动探索
- 自动规划

先做：

```text
Scene识别
+ 点击记录
+ 状态转移
+ Scene Graph
```

先把：

```text
截图 → 识别 Scene → 执行点击 → 进入下一个 Scene
```

整个链路跑通。

这是整个 AI Agent 最核心的数据基础。

这是整个系统最核心的部分。

