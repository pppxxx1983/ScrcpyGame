from __future__ import annotations







from PySide6.QtWidgets import QVBoxLayout, QWidget
class TabManagerPanelMixin:
    def _get_or_create_single_event_tab(self) -> tuple[QWidget, QVBoxLayout]:
        event_tab = None
        for i in range(self.ui.tabWidget.count()):
            if self.ui.tabWidget.tabText(i) == "事件":
                event_tab = self.ui.tabWidget.widget(i)
                break

        if event_tab is None:
            event_tab = QWidget()
            event_tab.setStyleSheet("background-color: #1e1e1e;")
            self.ui.tabWidget.addTab(event_tab, "事件")
            outer_layout = QVBoxLayout(event_tab)
            outer_layout.setContentsMargins(8, 8, 8, 8)
        else:
            outer_layout = event_tab.layout()
            if outer_layout.count() > 0:
                old_content = outer_layout.itemAt(0).widget()
                if old_content:
                    old_content.deleteLater()
        return event_tab, outer_layout

    def _close_tab(self, index: int):
        widget = self.ui.tabWidget.widget(index)
        if widget is None:
            return
        if widget is self.ui.tab:
            self.ui.tabWidget.setCurrentIndex(index)
            return
        self.ui.tabWidget.removeTab(index)
        widget.deleteLater()

