from __future__ import annotations



from log_manager import LogManager


class StatusPanelMixin:
    def _set_status(self, text, log=True):
        # 根据状态文字判断颜色
        if "连接失败" in text or "失败" in text or "错误" in text:
            color = "#f44747"  # 红色
        elif "已连接" in text:
            color = "#4ec9b0"  # 绿色
        elif "已断开" in text:
            color = "#ce9178"  # 橙色
        else:
            color = "#888888"  # 灰色

        # 发射信号，让主线程更新状态栏
        self._bridge.status_changed.emit(text, color)
        if log:
            LogManager().append(text)

    def _show_touch_feedback_slot(self, points, hold_ms: int):
        if self.video_widget:
            self.video_widget.show_touch_feedback(points, hold_ms=hold_ms)

    def _set_runtime_feedback_slot(self, payload):
        self._last_ui_feedback = payload if isinstance(payload, dict) else {}
        self._update_video_feedback_overlay()

    def _format_seconds(self, ms) -> str:
        try:
            return f"{int(ms) / 1000:.1f}s"
        except Exception:
            return "-"

    def _update_video_feedback_overlay(self):
        if not self.video_widget or not hasattr(self.video_widget, "set_status_lines"):
            return
        lines = []
        ctx = self._active_recording_context() if hasattr(self, "_active_recording_context") else {}
        if ctx:
            kind = "手动" if ctx.get("kind") == "manual" else "Session"
            lines.append(f"录像 {kind} @{self._format_seconds(ctx.get('video_offset_ms'))}")
        feedback = self._last_ui_feedback or {}
        rule = feedback.get("rule") or ""
        if rule:
            lines.append(f"规则 {rule}")
        scene = feedback.get("scene") or ""
        if scene:
            lines.append(f"场景 {scene}")
        status = feedback.get("status") or ""
        if status:
            lines.append(str(status))
        self.video_widget.set_status_lines(lines)
        if getattr(self, "runtime_feedback_label", None):
            text = " | ".join(lines) if lines else "Runtime: waiting"
            self.runtime_feedback_label.setText(text)
            color = "#4ec9b0" if any(line.startswith("规则") for line in lines) else "#9cdcfe"
            self.runtime_feedback_label.setStyleSheet(
                f"background-color: #111111; color: {color}; border: 1px solid #333333; "
                "padding: 6px; font-weight: bold;"
            )

    def _update_status_ui(self, text, color):
        # 状态栏只显示连接状态，防止 FPS 被识别/执行等临时信息覆盖
        if not text.startswith("状态:"):
            return
        if self.lbl_status:
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(f"color: {color}; padding: 5px 10px;")

    def _flush_log(self):
        logs = LogManager().get_and_clear()
        if logs and self.ui.textOutput:
            self.ui.textOutput.append("\n".join(logs))

    def _clear_log(self):
        LogManager().clear()
        self.ui.textOutput.clear()

