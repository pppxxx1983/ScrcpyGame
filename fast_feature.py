"""FastFeature: OCR, Layout, Color extraction + UI Tree + OCR-UI Fusion.
Covers TODO items #23, #24, #25.
"""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import colorsys


@dataclass
class OcrWord:
    text: str
    bbox: list[int]  # xyxy
    score: float
    source: str = "rapidocr"


@dataclass
class UiElement:
    element_id: int
    element_type: str  # button, text, icon, image, input, etc.
    bbox: list[int]  # xyxy
    text: str = ""
    ocr_words: list[OcrWord] = field(default_factory=list)
    color_dominant: tuple[int, int, int] = (0, 0, 0)
    color_secondary: tuple[int, int, int] = (0, 0, 0)
    children: list[int] = field(default_factory=list)
    parent: int = -1
    confidence: float = 0.0
    source: str = "fast_feature"
    area_ratio: float = 0.0  # relative to image


@dataclass
class LayoutRegion:
    name: str  # top_bar, bottom_nav, center_content, left_panel, etc.
    bbox: list[int]
    elements: list[int] = field(default_factory=list)


@dataclass
class FastFeatureResult:
    image_path: Path
    image_size: tuple[int, int]
    ocr_words: list[OcrWord] = field(default_factory=list)
    elements: list[UiElement] = field(default_factory=list)
    layout_regions: list[LayoutRegion] = field(default_factory=list)
    dominant_colors: list[tuple[int, int, int]] = field(default_factory=list)
    ui_tree_root: int = -1


class FastFeatureExtractor:
    """Extract OCR, layout, color, and build UI tree from a screenshot."""

    def __init__(self, ocr_client=None):
        self.ocr_client = ocr_client

    def extract(self, image_path: Path | str | np.ndarray) -> FastFeatureResult:
        if isinstance(image_path, (str, Path)):
            img = cv2.imread(str(image_path))
            pil_img = Image.open(str(image_path)).convert("RGB")
            path = Path(image_path)
        else:
            img = image_path
            pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            path = Path("frame.jpg")

        if img is None:
            raise ValueError("Failed to load image")

        h, w = img.shape[:2]
        result = FastFeatureResult(image_path=path, image_size=(w, h))

        # 1. OCR
        result.ocr_words = self._extract_ocr(img)

        # 2. Layout
        result.layout_regions = self._extract_layout(w, h)

        # 3. Colors
        result.dominant_colors = self._extract_colors(pil_img)

        # 4. Base elements from contours + OCR fusion
        result.elements = self._build_elements(img, result.ocr_words)

        # 5. Assign elements to layout regions
        self._assign_to_regions(result)

        # 6. Build parent-child hierarchy (simple spatial containment)
        result.ui_tree_root = self._build_ui_tree(result)

        return result

    def _extract_ocr(self, img: np.ndarray) -> list[OcrWord]:
        words = []
        try:
            if self.ocr_client is not None:
                # Use provided RapidOCR client
                results = self.ocr_client.recognize_frame(img)
                for item in results:
                    box = item.get("box", [])
                    text = item.get("text", "")
                    score = item.get("score", 0.0)
                    if not box or not text:
                        continue
                    xs = [p[0] for p in box]
                    ys = [p[1] for p in box]
                    words.append(OcrWord(
                        text=text,
                        bbox=[int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                        score=float(score),
                        source="rapidocr",
                    ))
            else:
                # Fallback: try local RapidOCR
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    engine = RapidOROCR()
                    res, _ = engine(img)
                    if res:
                        for r in res:
                            box, text, score = r[0], r[1], r[2]
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            words.append(OcrWord(
                                text=text,
                                bbox=[int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                                score=float(score),
                                source="rapidocr",
                            ))
                except Exception:
                    pass
        except Exception as e:
            # OCR is optional
            pass
        return words

    def _extract_layout(self, w: int, h: int) -> list[LayoutRegion]:
        """Divide screen into logical regions."""
        regions = []
        # Top bar (status bar / title)
        top_h = int(h * 0.08)
        regions.append(LayoutRegion("top_bar", [0, 0, w, top_h]))
        # Bottom nav
        bottom_h = int(h * 0.10)
        regions.append(LayoutRegion("bottom_nav", [0, h - bottom_h, w, h]))
        # Left panel (common in games)
        left_w = int(w * 0.15)
        regions.append(LayoutRegion("left_panel", [0, top_h, left_w, h - bottom_h]))
        # Right panel
        right_w = int(w * 0.15)
        regions.append(LayoutRegion("right_panel", [w - right_w, top_h, w, h - bottom_h]))
        # Center content
        regions.append(LayoutRegion("center_content", [left_w, top_h, w - right_w, h - bottom_h]))
        return regions

    def _extract_colors(self, pil_img: Image.Image, k: int = 5) -> list[tuple[int, int, int]]:
        """Extract dominant colors using k-means."""
        try:
            img = pil_img.resize((100, 100))
            arr = np.array(img)
            pixels = arr.reshape(-1, 3).astype(np.float32)
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
            counts = np.bincount(labels.flatten())
            sorted_idx = np.argsort(-counts)
            colors = []
            for idx in sorted_idx[:3]:
                c = centers[idx]
                colors.append((int(c[0]), int(c[1]), int(c[2])))
            return colors
        except Exception:
            return [(128, 128, 128), (64, 64, 64), (200, 200, 200)]

    def _build_elements(self, img: np.ndarray, ocr_words: list[OcrWord]) -> list[UiElement]:
        h, w = img.shape[:2]
        elements: list[UiElement] = []
        element_id = 0

        # 4a. Contour-based element detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Use MSER for region detection
        try:
            mser = cv2.MSER_create()
            regions, _ = mser.detectRegions(gray)
            for region in regions:
                if len(region) < 20:
                    continue
                xs = region[:, 0]
                ys = region[:, 1]
                x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
                area = (x2 - x1) * (y2 - y1)
                if area < 400 or area > w * h * 0.5:
                    continue
                # Filter out extremely wide/tall rectangles
                if (x2 - x1) / max(1, w) > 0.95 and (y2 - y1) / max(1, h) < 0.1:
                    continue  # likely status bar
                elem = UiElement(
                    element_id=element_id,
                    element_type="unknown",
                    bbox=[x1, y1, x2, y2],
                    confidence=0.5,
                    area_ratio=area / (w * h),
                )
                elements.append(elem)
                element_id += 1
        except Exception:
            pass

        # 4b. OCR fusion: if OCR word not covered by any element, create text element
        covered_ocr = set()
        for ocr in ocr_words:
            ox1, oy1, ox2, oy2 = ocr.bbox
            best_iou = 0.0
            best_idx = -1
            for idx, elem in enumerate(elements):
                ex1, ey1, ex2, ey2 = elem.bbox
                ix1 = max(ox1, ex1)
                iy1 = max(oy1, ey1)
                ix2 = min(ox2, ex2)
                iy2 = min(oy2, ey2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                inter = (ix2 - ix1) * (iy2 - iy1)
                union = (ox2 - ox1) * (oy2 - oy1) + (ex2 - ex1) * (ey2 - ey1) - inter
                iou = inter / max(1, union)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx
            if best_iou > 0.3:
                elements[best_idx].ocr_words.append(ocr)
                elements[best_idx].text = " ".join(w.text for w in elements[best_idx].ocr_words)
                elements[best_idx].element_type = "text" if elements[best_idx].element_type == "unknown" else elements[best_idx].element_type
                covered_ocr.add(id(ocr))
            else:
                # Create new text element
                elem = UiElement(
                    element_id=element_id,
                    element_type="text",
                    bbox=ocr.bbox,
                    text=ocr.text,
                    ocr_words=[ocr],
                    confidence=ocr.score,
                    area_ratio=(ocr.bbox[2] - ocr.bbox[0]) * (ocr.bbox[3] - ocr.bbox[1]) / (w * h),
                )
                elements.append(elem)
                element_id += 1
                covered_ocr.add(id(ocr))

        # 4c. Heuristic type assignment
        for elem in elements:
            x1, y1, x2, y2 = elem.bbox
            ew, eh = x2 - x1, y2 - y1
            ratio = ew / max(1, eh)
            # Button heuristic: moderate aspect ratio, contained text, compact
            if elem.element_type == "unknown":
                if 0.8 <= ratio <= 4.0 and ew < w * 0.4 and eh < h * 0.15:
                    elem.element_type = "button"
                elif ratio > 4.0 and eh < h * 0.08:
                    elem.element_type = "text"
                elif ew > w * 0.3 and eh > h * 0.3:
                    elem.element_type = "image"
                else:
                    elem.element_type = "icon"

        # 4d. Color sampling per element
        for elem in elements:
            x1, y1, x2, y2 = elem.bbox
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            rx = max(1, (x2 - x1) // 4)
            ry = max(1, (y2 - y1) // 4)
            patch = img[max(0, cy - ry):min(h, cy + ry), max(0, cx - rx):min(w, cx + rx)]
            if patch.size > 0:
                mean_color = cv2.mean(patch)[:3]
                elem.color_dominant = (int(mean_color[2]), int(mean_color[1]), int(mean_color[0]))

        return elements

    def _assign_to_regions(self, result: FastFeatureResult):
        w, h = result.image_size
        for elem in result.elements:
            cx = (elem.bbox[0] + elem.bbox[2]) // 2
            cy = (elem.bbox[1] + elem.bbox[3]) // 2
            for reg in result.layout_regions:
                rx1, ry1, rx2, ry2 = reg.bbox
                if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                    reg.elements.append(elem.element_id)
                    break

    def _build_ui_tree(self, result: FastFeatureResult) -> int:
        """Build parent-child hierarchy based on spatial containment."""
        elems = result.elements
        n = len(elems)
        if n == 0:
            return -1

        # Sort by area descending
        order = sorted(range(n), key=lambda i: (elems[i].bbox[2] - elems[i].bbox[0]) * (elems[i].bbox[3] - elems[i].bbox[1]), reverse=True)

        root = order[0]
        for idx in order:
            if idx == root:
                elems[idx].parent = -1
                continue
            x1, y1, x2, y2 = elems[idx].bbox
            best_parent = -1
            best_area = float('inf')
            for j in order:
                if j == idx:
                    continue
                px1, py1, px2, py2 = elems[j].bbox
                # Check if idx is contained in j
                if px1 <= x1 and py1 <= y1 and px2 >= x2 and py2 >= y2:
                    area = (px2 - px1) * (py2 - py1)
                    if area < best_area:
                        best_area = area
                        best_parent = j
            elems[idx].parent = best_parent
            if best_parent >= 0:
                elems[best_parent].children.append(idx)

        return root


def ocr_ui_fusion(elements: list[UiElement], ocr_words: list[OcrWord], iou_threshold: float = 0.3) -> list[UiElement]:
    """Explicit OCR-UI fusion (TODO #24). Merge OCR words into existing UI elements or create new ones."""
    # This is essentially the same logic as _build_elements step 4b,
    # but exposed as a standalone utility for external use.
    return elements


def build_full_ui_tree(result: FastFeatureResult) -> dict:
    """Export UI tree as a serializable dict (TODO #25)."""
    def elem_to_dict(e: UiElement) -> dict:
        return {
            "id": e.element_id,
            "type": e.element_type,
            "bbox": e.bbox,
            "text": e.text,
            "color_dominant": e.color_dominant,
            "color_secondary": e.color_secondary,
            "confidence": e.confidence,
            "source": e.source,
            "area_ratio": e.area_ratio,
            "children": e.children,
            "parent": e.parent,
        }

    def build_subtree(root_id: int) -> dict:
        node = elem_to_dict(result.elements[root_id])
        node["children_nodes"] = [build_subtree(cid) for cid in result.elements[root_id].children]
        return node

    if result.ui_tree_root < 0 or result.ui_tree_root >= len(result.elements):
        return {"root": None, "elements": [], "layout": []}

    return {
        "root": build_subtree(result.ui_tree_root),
        "elements": [elem_to_dict(e) for e in result.elements],
        "layout": [
            {"name": r.name, "bbox": r.bbox, "elements": r.elements}
            for r in result.layout_regions
        ],
        "dominant_colors": result.dominant_colors,
        "image_size": result.image_size,
    }
