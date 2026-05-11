from PySide6.QtWidgets import (
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
)
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PySide6.QtCore import QTimer, Signal, Qt, QPointF
from log_manager import LogManager

class SceneGraphNode(QGraphicsEllipseItem):
    def __init__(self, scene_data: dict, x: float, y: float, radius: float = 36):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self._data = scene_data
        self._radius = radius
        self.setPos(x, y)
        self.setBrush(QColor("#0e639c"))
        self.setPen(QPen(QColor("#40d8ff"), 2))
        self.setFlags(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable | QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self._label = None
        self._click_callback = None
        self._build_label()

    def _build_label(self):
        text = str(self._data.get("scene_key", ""))[:8]
        self._label = QGraphicsTextItem(text, self)
        self._label.setDefaultTextColor(QColor("#ffffff"))
        font = QFont("Microsoft YaHei", 9)
        font.setBold(True)
        self._label.setFont(font)
        fm = self._label.boundingRect()
        self._label.setPos(-fm.width() / 2, -fm.height() / 2)

    def hoverEnterEvent(self, event):
        self.setBrush(QColor("#1177bb"))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QColor("#0e639c"))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self._click_callback:
            self._click_callback(self._data)
        super().mousePressEvent(event)

    def get_data(self) -> dict:
        return self._data


class SceneGraphEdge(QGraphicsLineItem):
    def __init__(self, source_node: SceneGraphNode, target_node: SceneGraphNode, action_data: dict):
        super().__init__()
        self._source = source_node
        self._target = target_node
        self._data = action_data
        self.setPen(QPen(QColor("#888888"), 1.5))
        self.setZValue(1)
        self._arrow = None
        self._label = None
        self._build_label()
        self._update_geometry()

    def _build_label(self):
        name = str(self._data.get("action_name", ""))[:10] or "action"
        self._label = QGraphicsTextItem(name)
        font = QFont("Microsoft YaHei", 8)
        self._label.setFont(font)
        self._label.setDefaultTextColor(QColor("#cccccc"))
        if self.scene():
            self.scene().addItem(self._label)

    def _update_geometry(self):
        p1 = self._source.pos()
        p2 = self._target.pos()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < 0.1:
            return
        # 缩进到圆边界
        r = self._source._radius
        ratio = r / dist
        sx = p1.x() + dx * ratio
        sy = p1.y() + dy * ratio
        tx = p2.x() - dx * ratio
        ty = p2.y() - dy * ratio
        self.setLine(sx, sy, tx, ty)
        # 更新标签位置
        if self._label:
            self._label.setPos((sx + tx) / 2, (sy + ty) / 2 - 10)

    def update_positions(self):
        self._update_geometry()

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        # 画箭头
        line = self.line()
        dx = line.x2() - line.x1()
        dy = line.y2() - line.y1()
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < 1:
            return
        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux
        arrow_size = 8
        tip = QPointF(line.x2(), line.y2())
        base1 = QPointF(tip.x() - arrow_size * ux + arrow_size * 0.5 * px, tip.y() - arrow_size * uy + arrow_size * 0.5 * py)
        base2 = QPointF(tip.x() - arrow_size * ux - arrow_size * 0.5 * px, tip.y() - arrow_size * uy - arrow_size * 0.5 * py)
        painter.setBrush(QColor("#888888"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([tip, base1, base2]))


class SceneGraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333;")
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-600, -400, 1200, 800)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._nodes: dict[int, SceneGraphNode] = {}
        self._edges: list[SceneGraphEdge] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_layout)
        self._timer.start(50)
        self._tick_count = 0

    def build_graph(self, scenes: list[dict], actions: list[dict]):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._tick_count = 0
        if not scenes:
            text = self._scene.addText("暂无场景数据")
            text.setDefaultTextColor(QColor("#888888"))
            return
        # 环形布局初始位置
        count = len(scenes)
        radius = max(180, count * 28)
        for i, sc in enumerate(scenes):
            angle = 2 * 3.14159 * i / count - 3.14159 / 2
            x = radius * __import__("math").cos(angle)
            y = radius * __import__("math").sin(angle)
            node = SceneGraphNode(sc, x, y)
            node._click_callback = self._on_node_clicked
            self._scene.addItem(node)
            self._nodes[sc["id"]] = node
        # 创建边
        for act in actions:
            src_id = act.get("from_scene_id")
            dst_id = act.get("to_scene_id")
            if src_id in self._nodes and dst_id in self._nodes:
                edge = SceneGraphEdge(self._nodes[src_id], self._nodes[dst_id], act)
                self._scene.addItem(edge)
                self._edges.append(edge)

    def _tick_layout(self):
        if not self._nodes:
            return
        if self._tick_count > 80:
            self._timer.stop()
            return
        self._tick_count += 1
        # 简单的力导向：节点间斥力 + 边吸引力
        nodes = list(self._nodes.values())
        for node in nodes:
            fx, fy = 0.0, 0.0
            # 节点间斥力
            for other in nodes:
                if other is node:
                    continue
                dx = node.pos().x() - other.pos().x()
                dy = node.pos().y() - other.pos().y()
                dist = (dx ** 2 + dy ** 2) ** 0.5
                if dist < 1:
                    continue
                force = 1200.0 / max(dist, 10)
                fx += dx / dist * force
                fy += dy / dist * force
            # 边吸引力
            for edge in self._edges:
                if edge._source is node:
                    dx = edge._target.pos().x() - node.pos().x()
                    dy = edge._target.pos().y() - node.pos().y()
                    fx += dx * 0.008
                    fy += dy * 0.008
                elif edge._target is node:
                    dx = edge._source.pos().x() - node.pos().x()
                    dy = edge._source.pos().y() - node.pos().y()
                    fx += dx * 0.008
                    fy += dy * 0.008
            # 中心引力（防止飘太远）
            fx -= node.pos().x() * 0.002
            fy -= node.pos().y() * 0.002
            # 应用力
            new_x = node.pos().x() + fx * 0.3
            new_y = node.pos().y() + fy * 0.3
            node.setPos(new_x, new_y)
        for edge in self._edges:
            edge.update_positions()

    def _on_node_clicked(self, data: dict):
        pass

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        self.scale(factor, factor)


class SceneGraphDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scene Graph 可视化")
        self.resize(960, 720)
        self.setStyleSheet("background-color: #1e1e1e; color: #cccccc;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部统计栏
        self.stats_label = QLabel("加载中...")
        self.stats_label.setStyleSheet(
            "background-color: #111111; color: #9cdcfe; border: 1px solid #333333; padding: 6px; font-weight: bold;"
        )
        layout.addWidget(self.stats_label)

        # 图形容器
        self.graph_view = SceneGraphView(self)
        layout.addWidget(self.graph_view, 1)

        # 底部控制栏
        ctrl = QHBoxLayout()
        btn_refresh = QPushButton("刷新数据")
        btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0e639c; color: white; padding: 6px; }"
            "QPushButton:hover { background-color: #1177bb; }"
        )
        btn_refresh.clicked.connect(self._load_data)
        ctrl.addWidget(btn_refresh)

        btn_reset = QPushButton("重置布局")
        btn_reset.setStyleSheet(
            "QPushButton { background-color: #3c3c3c; color: #cccccc; padding: 6px; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        btn_reset.clicked.connect(self._reset_layout)
        ctrl.addWidget(btn_reset)

        self.detail_label = QLabel("点击场景节点查看详情")
        self.detail_label.setStyleSheet("color: #888888; padding: 4px;")
        self.detail_label.setWordWrap(True)
        ctrl.addWidget(self.detail_label, 1)

        ctrl.addStretch(1)
        layout.addLayout(ctrl)

        self._load_data()

    def _load_data(self):
        try:
            from agent_data import AgentDataManager
            from scene_index import SceneIndex

            scenes = SceneIndex().list_all_scenes()
            actions = AgentDataManager().list_actions()
            stats = AgentDataManager().get_action_stats()

            self.stats_label.setText(
                f"场景 {len(scenes)} | 转移边 {stats['total_actions']} | "
                f"成功 {stats['total_success']} | 失败 {stats['total_fail']} | "
                f"成功率 {stats['success_rate']*100:.1f}%"
            )
            self.graph_view.build_graph(scenes, actions)
            # 连接节点点击回调
            for node in self.graph_view._nodes.values():
                node._click_callback = self._on_node_clicked
        except Exception as e:
            LogManager().append(f"[SceneGraph] 加载数据失败: {e}")
            self.stats_label.setText(f"加载失败: {e}")

    def _reset_layout(self):
        self.graph_view._tick_count = 0
        self.graph_view._timer.start(50)

    def _on_node_clicked(self, data: dict):
        text = (
            f"场景: {data.get('scene_key', '')} | "
            f"命中: {data.get('hits', 0)} | "
            f"描述: {data.get('description', '')[:40]}"
        )
        self.detail_label.setText(text)

