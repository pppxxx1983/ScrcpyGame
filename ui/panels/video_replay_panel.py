from __future__ import annotations



from ui.dialogs.video_replay import VideoReplayDialog




class VideoReplayPanelMixin:
    def _show_video_replay(self):
        """打开视频回放中心对话框。"""
        dialog = VideoReplayDialog(self)
        dialog.exec()

