"""
执行任务管理引擎
- 管理 Session、视频录制、任务队列
- 所有耗时操作在后台线程执行，不阻塞主界面
- 通过 Qt Signal 与 UI 通信
"""

import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from agent_data import AgentDataManager
from ocr_client import OCRClient
from aliyun_ocr_client import AliyunOCRClient
from log_manager import LogManager


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

    def __init__(self):
        super().__init__()
        self.dm = AgentDataManager()
        self._video_writer = None
        self._record_fps = 20
        self._running = False
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
        """开始执行：创建 Session + 启动视频录制（全部在后台线程，不阻塞 UI）。"""
        if self._running:
            return

        def _exec():
            try:
                session_id = self.dm.start_session()
                video_path = self.dm.get_video_path()

                if frame is not None:
                    import cv2
                    h, w = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    self._video_writer = cv2.VideoWriter(
                        str(video_path), fourcc, self._record_fps, (w, h)
                    )

                self._running = True
                self.task_cleared.emit()
                self.task_added.emit("识别场景", True)
                self.status_changed.emit(f"开始执行 Session {session_id}", "#4ec9b0")

                self._run_recognize_scene(frame)
            except Exception as e:
                self.status_changed.emit(f"启动失败: {e}", "#f44747")
                LogManager().append(f"[ERROR] ExecutionEngine.start: {e}")

        threading.Thread(target=_exec, daemon=True).start()

    def stop(self):
        """停止执行：结束录制 + 结束 Session。"""
        if self._video_writer is not None:
            try:
                self._video_writer.release()
            except Exception:
                pass
            self._video_writer = None

        self.dm.end_session()
        self._running = False
        self.status_changed.emit("执行已停止", "#ce9178")

    def write_frame(self, frame):
        """写入视频帧（供 on_frame 调用，线程安全）。"""
        if self._video_writer is not None and frame is not None:
            try:
                self._video_writer.write(frame)
            except Exception as e:
                LogManager().append(f"[WARN] 录制写入失败: {e}")

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
            return

        def _exec():
            try:
                time.sleep(0.3)
                frame_300 = frame_provider()
                self._save_frame("after_300ms", op_dir, frame_300)

                time.sleep(0.5)
                frame_800 = frame_provider()
                self._save_frame("after_800ms", op_dir, frame_800)

                self.dm.record_click(
                    x=x,
                    y=y,
                    before_image=op_dir / "before.png",
                    after_300ms_image=op_dir / "after_300ms.png",
                    after_800ms_image=op_dir / "after_800ms.png",
                )
                LogManager().append(
                    f"[Click] 已记录 click #{self.dm.click_counter} -> {op_dir.name}"
                )
            except Exception as e:
                LogManager().append(f"[WARN] on_click_up failed: {e}")

        threading.Thread(target=_exec, daemon=True).start()

    # ------------------------------------------------------------------
    # 识别场景
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
            t1 = time.perf_counter()
            LogManager().append(f"[Perf] dump frame: {(t1-t0)*1000:.1f}ms")
            if temp_path is None:
                self.status_changed.emit("识别场景: 无视频帧", "#f44747")
                self.task_done.emit("识别场景", False)
                self.task_done.emit("场景哈希索引", False)
                return

            # 通知 UI 创建标签页显示场景截图（已知场景无对象列表）
            self.scene_image_ready.emit("识别场景", temp_path, [])

            # 1. 先做场景哈希索引
            LogManager().append("[Scene] 开始场景哈希索引...")
            from scene_index import SceneIndex, image_fingerprint
            si = SceneIndex()
            fp = image_fingerprint(temp_path)
            LogManager().append(f"[Scene] 图片指纹: ahash={fp['ahash'][:16]}..., dhash={fp['dhash'][:16]}...")
            best = si.find_best(fp)
            LogManager().append(f"[Scene] find_best 返回: {best is not None}")
            if best:
                LogManager().append(
                    f"[Scene] 最佳匹配: key={best['scene_key'][:16]}... "
                    f"confidence={best['confidence']:.2f}"
                )
            threshold = 0.92

            if best and best["confidence"] >= threshold:
                # 匹配到已知场景，跳过 OCR 和视觉描述
                si._record_hit(best["id"])
                desc = best.get("description", "")
                LogManager().append(
                    f"[Scene] 匹配到已知场景: {best['scene_key']} "
                    f"(confidence={best['confidence']:.2f}, hits={best['hits']+1})"
                )
                if desc:
                    LogManager().append(f"[Scene] 场景描述: {desc}")
                self.status_changed.emit(
                    f"识别完成: 已知场景 {best['scene_key'][:16]}...", "#4ec9b0"
                )
                self.task_done.emit("识别场景", True)
                self.task_done.emit("场景哈希索引", True)
                return

            # 2. 未匹配到已知场景，执行 OCR + 大模型场景描述
            LogManager().append("[Scene] 未匹配到已知场景，开始 OCR + 场景描述...")

            # OCR
            ocr = AliyunOCRClient()
            t2 = time.perf_counter()
            result = ocr.recognize(temp_path)
            t3 = time.perf_counter()
            LogManager().append(f"[Perf] AliyunOCR request: {(t3-t2)*1000:.1f}ms")
            text = "\n".join([i["text"] for i in result])

            lines = [f"[OCR] 识别到 {len(result)} 个区域:"]
            for item in result[:10]:
                lines.append(f"  [{item['score']:.2f}] {item['text']}")
            for line in lines:
                LogManager().append(line)

            # 大模型一次性分析：OCR + 场景描述 + 对象检测
            from llm_client import QwenVLClient
            vl = QwenVLClient(api_key="sk-b368216722514ad1956826669fe15b05")

            t4 = time.perf_counter()
            analysis = vl.analyze_scene(temp_path)
            t5 = time.perf_counter()
            LogManager().append(f"[Perf] 大模型分析: {(t5-t4)*1000:.1f}ms")

            scene_desc = analysis.get("scene_description", "")
            ocr_text = analysis.get("ocr_text", [])
            objects = analysis.get("objects", [])

            LogManager().append(f"[Scene] 场景描述: {scene_desc}")
            LogManager().append(f"[OCR] 识别到 {len(ocr_text)} 行文字:")
            for line in ocr_text[:10]:
                LogManager().append(f"  {line}")
            LogManager().append(f"[Obj] 检测到 {len(objects)} 个对象:")
            for obj in objects[:10]:
                LogManager().append(f"  {obj['name']} -> {obj['bbox']}")

            # 分析完成后标记识别场景完成
            self.status_changed.emit(
                f"识别完成: 新场景，{len(ocr_text)} 文字/{len(objects)} 对象", "#4ec9b0"
            )
            self.task_done.emit("识别场景", True)

            # 通知 UI 显示带 bbox 标注的截图
            self.scene_image_ready.emit("识别场景", temp_path, objects)

            # 3. 后台插入新场景到索引（带上描述）
            def _insert_new_scene():
                try:
                    t8 = time.perf_counter()
                    scene_id = si._insert_scene(temp_path, fp, scene_desc)
                    t9 = time.perf_counter()
                    LogManager().append(
                        f"[Scene] 已插入新场景 #{scene_id} "
                        f"(key={fp['dhash'][:16]}..., 耗时{(t9-t8)*1000:.1f}ms)"
                    )
                    self.task_done.emit("场景哈希索引", True)
                except Exception as e:
                    LogManager().append(f"[WARN] 插入新场景失败: {e}")
                    self.task_done.emit("场景哈希索引", False)

            threading.Thread(target=_insert_new_scene, daemon=True).start()

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
        """将当前帧保存到临时文件，返回路径（OCR 用，会降分辨率以减少负载）。"""
        if frame is None:
            return None
        try:
            from PIL import Image

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            temp_path = Path("screenshots") / f"scene_{ts}.png"
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            # 在线 OCR 不消耗本地 CPU，保存原分辨率以保证识别效果
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
