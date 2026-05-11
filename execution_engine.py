"""
执行任务管理引擎
- 管理 Session、视频录制、任务队列
- 所有耗时操作在后台线程执行，不阻塞主界面
- 通过 Qt Signal 与 UI 通信
"""

import threading
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from agent_data import AgentDataManager
from ocr_client import OCRClient
from aliyun_ocr_client import AliyunOCRClient
from log_manager import LogManager
from scene_index import (
    SceneIndex, image_fingerprint, _draw_name_on_image,
)


class ExecutionEngine(QObject):
    """
    执行引擎（单例建议，但此处作为普通对象由 MainWindow 持有）。

    信号:
        status_changed(str, str)  -> 状态栏文本 + 颜色
        task_added(str, bool)     -> 任务文本 + 是否 pending
        task_cleared()            -> 清空任务队列
        task_done(str, bool)      -> 任务文本 + 是否成功
    """

    status_changed = Signal(str, str)
    task_added = Signal(str, bool)
    task_subtask_added = Signal(str, str)   # parent_text, sub_text
    task_cleared = Signal()
    task_done = Signal(str, bool)
    scene_image_ready = Signal(str, Path, list)   # text, image_path, objects
    scene_name_changed = Signal(str)                # 场景识别名字（空字符串表示清空）

    def __init__(self):
        super().__init__()
        self.dm = AgentDataManager()
        self._video_writer = None
        self._record_fps = 20
        self._record_started_perf = 0.0
        self._record_started_ms = 0
        self._record_frame_count = 0
        self._record_last_frame_perf = 0.0
        self._record_video_path: Path | None = None
        self._running = False
        self._current_frame = None          # 最新视频帧，由 write_frame 更新
        self._recognize_thread = None       # 场景识别循环线程
        self._recognize_interval = 2.0      # 每隔 2 秒识别一次
        # 延迟后台预热 OCR 引擎，避免和主窗口初始化竞争 CPU
        def _delayed_warmup():
            time.sleep(3)
            self._warm_up_ocr()
        threading.Thread(target=_delayed_warmup, daemon=True).start()

    # ------------------------------------------------------------------
    # Session / 录制 控制
    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        return self._running

    def start(self, frame=None):
        """开始执行：创建 Session + 启动视频录制 + 启动场景识别循环线程。"""
        if self._running:
            return

        def _exec():
            try:
                session_id = self.dm.start_session()
                video_path = self.dm.get_video_path()
                self._record_video_path = video_path
                self._record_started_perf = time.perf_counter()
                self._record_started_ms = int(time.time() * 1000)
                self._record_frame_count = 0
                self._record_last_frame_perf = 0.0

                if frame is not None:
                    import cv2
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    self._video_writer = cv2.VideoWriter(
                        str(video_path), fourcc, self._record_fps, (w, h)
                    )
                    self._current_frame = frame
                self._write_recording_meta(finished=False)

                self._running = True
                self.task_cleared.emit()
                self.task_added.emit("识别场景", True)
                self.status_changed.emit(f"开始执行 Session {session_id}", "#4ec9b0")
                LogManager().append(f"[Engine] 开始执行 Session {session_id}")

                # 启动场景识别循环线程
                self._start_recognize_loop()
            except Exception as e:
                self.status_changed.emit(f"启动失败: {e}", "#f44747")
                LogManager().append(f"[ERROR] ExecutionEngine.start: {e}")

        threading.Thread(target=_exec, daemon=True).start()

    def stop(self):
        """停止执行：结束录制 + 结束 Session + 停止识别循环。
        UnknownFolderProcessor 常驻后台，不随执行状态启停。"""
        if self._video_writer is not None:
            try:
                self._write_recording_meta(finished=True)
                self._video_writer.release()
            except Exception:
                pass
            self._video_writer = None

        self._running = False
        self.dm.end_session()
        self.status_changed.emit("执行已停止", "#ce9178")
        LogManager().append("[Engine] 执行已停止")

    def write_frame(self, frame, rgb_frame=None):
        """写入视频帧并保存最新帧（供 on_frame 调用，线程安全）。
        scrcpy 原始帧是 BGR，保存为 RGB 供后续截图使用。"""
        if rgb_frame is not None:
            self._current_frame = rgb_frame
        elif frame is not None:
            import numpy as np
            # 与 video_widget 保持一致：BGR -> RGB
            self._current_frame = np.ascontiguousarray(frame[..., ::-1])
        if self._video_writer is not None and frame is not None:
            now = time.perf_counter()
            min_interval = 1.0 / max(1, self._record_fps)
            if self._record_last_frame_perf and now - self._record_last_frame_perf < min_interval:
                return
            try:
                # 确保帧尺寸与录制器一致
                if hasattr(self._video_writer, '_width') and hasattr(self._video_writer, '_height'):
                    h, w = frame.shape[:2]
                    if w != self._video_writer._width or h != self._video_writer._height:
                        import cv2
                        frame = cv2.resize(frame, (self._video_writer._width, self._video_writer._height))
                self._video_writer.write(frame)
                self._record_frame_count += 1
                self._record_last_frame_perf = now
            except Exception as e:
                LogManager().append(f"[WARN] 录制写入失败: {e}")

    def get_recording_context(self) -> dict:
        if self._video_writer is None or not self._record_started_perf:
            return {}
        offset_ms = max(0, int((time.perf_counter() - self._record_started_perf) * 1000))
        return {
            "kind": "session",
            "video_path": str(self._record_video_path or ""),
            "events_path": str(self.dm.current_session_events_path or ""),
            "meta_path": str(self.dm.current_session_meta_path or ""),
            "video_offset_ms": offset_ms,
            "started_timestamp_ms": self._record_started_ms,
            "frame_count": self._record_frame_count,
            "fps": self._record_fps,
            "session_id": self.dm.current_session_id or "",
        }

    def _write_recording_meta(self, finished: bool = False):
        meta_path = self.dm.current_session_meta_path
        if not meta_path:
            return
        try:
            ctx = self.get_recording_context()
            if not ctx:
                ctx = {
                    "kind": "session",
                    "video_path": str(self._record_video_path or ""),
                    "events_path": str(self.dm.current_session_events_path or ""),
                    "meta_path": str(meta_path),
                    "video_offset_ms": 0,
                    "started_timestamp_ms": self._record_started_ms,
                    "frame_count": self._record_frame_count,
                    "fps": self._record_fps,
                    "session_id": self.dm.current_session_id or "",
                }
            ctx["finished"] = bool(finished)
            if finished:
                ctx["ended_timestamp_ms"] = int(time.time() * 1000)
                ctx["ended_at"] = datetime.now().isoformat()
            meta_path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            LogManager().append(f"[WARN] write session recording meta failed: {e}")

    # ------------------------------------------------------------------
    # 点击事件
    # ------------------------------------------------------------------
    def on_click_down(self, frame, op_dir: Path):
        """点击 DOWN 时保存 before（主线程调用）。"""
        if self.dm.is_session_active():
            self._save_frame("before", op_dir, frame)

    def on_click_up(
        self,
        x: int,
        y: int,
        op_dir: Path,
        frame_provider: Callable,
    ):
        """
        点击 UP 后后台保存 after_300ms / after_800ms 并入库。
        frame_provider: 无参函数，返回当前 numpy frame
        """
        if not self.dm.is_session_active():
            LogManager().append("[Click] on_click_up skipped: no active session")
            return

        def _exec():
            try:
                LogManager().append(f"[Click] on_click_up start, op_dir={op_dir}")
                time.sleep(0.3)
                frame_300 = frame_provider()
                self._save_frame("after_300ms", op_dir, frame_300)

                time.sleep(0.5)
                frame_800 = frame_provider()
                self._save_frame("after_800ms", op_dir, frame_800)

                before_path = op_dir / "before.png" if op_dir else None
                after300_path = op_dir / "after_300ms.png" if op_dir else None
                after800_path = op_dir / "after_800ms.png" if op_dir else None
                LogManager().append(f"[Click] record_click paths: before={before_path}, after300={after300_path}, after800={after800_path}")
                self.dm.record_click(
                    x=x,
                    y=y,
                    before_image=before_path,
                    after_300ms_image=after300_path,
                    after_800ms_image=after800_path,
                )
                LogManager().append(
                    f"[Click] 已记录 click #{self.dm.click_counter} -> {op_dir.name}"
                )
            except Exception as e:
                LogManager().append(f"[WARN] on_click_up failed: {e}")

        threading.Thread(target=_exec, daemon=True).start()

    # ------------------------------------------------------------------
    # 场景识别循环线程（持续取帧 → hash查找 → 找不到保存到unknown）
    # ------------------------------------------------------------------
    def _start_recognize_loop(self):
        """启动场景识别循环线程。"""
        if self._recognize_thread is not None and self._recognize_thread.is_alive():
            return
        self._recognize_thread = threading.Thread(target=self._recognize_loop, daemon=True)
        self._recognize_thread.start()
        LogManager().append("[Scene] 场景识别循环线程已启动")

    def _recognize_loop(self):
        """每隔 _recognize_interval 秒取当前帧做一次 hash 识别。"""
        while self._running:
            frame = self._current_frame
            if frame is not None:
                try:
                    self._run_recognize_scene(frame)
                except Exception as e:
                    LogManager().append(f"[WARN] 识别循环异常: {e}")
            time.sleep(self._recognize_interval)
        LogManager().append("[Scene] 场景识别循环线程已停止")

    # ------------------------------------------------------------------
    # 识别场景（单次）
    # ------------------------------------------------------------------
    @staticmethod
    def _set_low_priority():
        """降低当前线程优先级并绑定到单核，避免 CPU 密集型任务影响系统响应（Windows）。"""
        try:
            import ctypes
            thread = ctypes.windll.kernel32.GetCurrentThread()
            # 绑定到 CPU 0，避免抢满所有核心
            ctypes.windll.kernel32.SetThreadAffinityMask(thread, 1)
            # THREAD_PRIORITY_IDLE = -15（最低优先级，只有空闲时才跑）
            ctypes.windll.kernel32.SetThreadPriority(thread, -15)
        except Exception:
            pass

    def _run_recognize_scene(self, frame):
        """执行识别场景（调用者需确保已在后台线程）。"""
        import time
        t0 = time.perf_counter()
        try:
            # 子任务「场景哈希索引」立即显示
            self.task_subtask_added.emit("识别场景", "场景哈希索引")

            temp_path = self._dump_frame_to_temp(frame)
            if temp_path is None:
                self.status_changed.emit("识别场景: 无视频帧", "#f44747")
                self.task_done.emit("识别场景", False)
                self.task_done.emit("场景哈希索引", False)
                return

            # 1. 先做场景哈希索引
            from scene_index import SceneIndex, image_fingerprint
            si = SceneIndex()
            fp = image_fingerprint(temp_path)
            best = si.find_best(fp)
            threshold = 0.92

            if best and best["confidence"] >= threshold:
                # 匹配到已知场景：画名字 + 增加 hits
                si._record_hit(best["id"])
                # scene_key 已存场景名字，直接显示
                name = best.get("scene_key", "")[:4]
                if not name:
                    name = "已知"
                # 在截图左上角显示名字（不弹标签页）
                try:
                    tagged_path = _draw_name_on_image(temp_path, name)
                    # 清理临时文件（名字已显示在投屏上，不需要保留文件）
                    try:
                        temp_path.unlink(missing_ok=True)
                        tagged_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                except Exception as e:
                    LogManager().append(f"[WARN] 标记名字失败: {e}")

                self.scene_name_changed.emit(name)
                self.task_done.emit("识别场景", True)
                self.task_done.emit("场景哈希索引", True)
                return

            # 2. 未匹配到已知场景：移到 unknown/，等后台 Ollama 8b 识别分类
            unknown_dir = Path("screenshots") / "unknown"
            unknown_dir.mkdir(parents=True, exist_ok=True)
            unknown_path = unknown_dir / temp_path.name
            try:
                import shutil
                shutil.move(str(temp_path), str(unknown_path))
            except Exception as e:
                LogManager().append(f"[WARN] 移动文件失败: {e}")

            self.scene_name_changed.emit("")
            self.task_done.emit("识别场景", True)
            self.task_done.emit("场景哈希索引", True)

        except Exception as e:
            import traceback
            err_msg = f"[ERROR] 识别失败: {e}"
            LogManager().append(err_msg)
            LogManager().append(traceback.format_exc())
            self.status_changed.emit(err_msg, "#f44747")
            self.task_done.emit("识别场景", False)
            self.task_done.emit("场景哈希索引", False)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _save_frame(label: str, op_dir: Path, frame):
        """保存帧到指定目录。"""
        if frame is None:
            return None
        try:
            from PIL import Image

            path = op_dir / f"{label}.png"
            # video_widget._frame 已经是 set_frame() 内 copy() 后的独立数组，
            # 主线程只替换引用不会修改内容，这里无需再 copy()
            Image.fromarray(frame).save(str(path))
            return path
        except Exception as e:
            LogManager().append(f"[WARN] save frame failed: {e}")
            return None

    @staticmethod
    def _dump_frame_to_temp(frame) -> Optional[Path]:
        """将当前帧保存到临时文件，返回路径。临时文件放在 .temp/ 避免污染根目录。"""
        if frame is None:
            return None
        try:
            from PIL import Image

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            temp_dir = Path("screenshots") / ".temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / f"scene_{ts}.png"

            Image.fromarray(frame).save(str(temp_path))
            return temp_path
        except Exception as e:
            LogManager().append(f"[WARN] dump frame failed: {e}")
            return None

    @staticmethod
    def _warm_up_ocr():
        """后台预热 OCR 引擎，避免首次识别时因模型加载造成感知卡顿。"""
        try:
            _ = OCRClient()
            LogManager().append("[Engine] OCR 引擎预热完成")
        except Exception as e:
            LogManager().append(f"[WARN] OCR 预热失败: {e}")
