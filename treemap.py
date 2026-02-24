from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TreemapNode:
    """用于 UI 渲染的 treemap 节点。"""

    label: str
    size: float
    x: float
    y: float
    width: float
    height: float
    data: object | None = None


def _squarify(sizes: List[float], rect: Tuple[float, float, float, float]) -> List[TreemapNode]:
    """
    一个简化版的 squarified treemap 布局算法。
    参考文档中的 Treemap 概念，这里只实现基础矩形划分。
    """
    x, y, w, h = rect
    if not sizes:
        return []

    total = float(sum(sizes))
    if total <= 0:
        return []

    normalized = [s / total * w * h for s in sizes]

    result: List[TreemapNode] = []

    def layout_row(row: List[float], row_rect: Tuple[float, float, float, float], is_horizontal: bool):
        nonlocal result
        rx, ry, rw, rh = row_rect
        row_sum = sum(row)
        if row_sum <= 0 or rw <= 0 or rh <= 0:
            return
        if is_horizontal:
            row_height = row_sum / rw
            if row_height <= 0:
                return
            cx = rx
            for val in row:
                if row_height <= 0:
                    continue
                node_width = val / row_height if row_height != 0 else 0
                if node_width <= 0:
                    continue
                result.append(
                    TreemapNode(label="", size=val, x=cx, y=ry, width=node_width, height=row_height)
                )
                cx += node_width
            # 返回剩余区域
            return rx, ry + row_height, rw, rh - row_height
        else:
            row_width = row_sum / rh
            if row_width <= 0:
                return
            cy = ry
            for val in row:
                if row_width <= 0:
                    continue
                node_height = val / row_width if row_width != 0 else 0
                if node_height <= 0:
                    continue
                result.append(
                    TreemapNode(label="", size=val, x=rx, y=cy, width=row_width, height=node_height)
                )
                cy += node_height
            return rx + row_width, ry, rw - row_width, rh

    def worst_aspect_ratio(row: List[float], side_length: float) -> float:
        if not row or side_length <= 0:
            return float("inf")
        s = sum(row)
        max_v = max(row)
        min_v = min(row)
        if s <= 0 or max_v <= 0 or min_v <= 0:
            return float("inf")
        s2 = side_length * side_length
        if s2 <= 0:
            return float("inf")
        return max((s2 * max_v) / (s * s), (s * s) / (s2 * min_v))

    remaining = list(normalized)
    row: List[float] = []
    is_horizontal = True
    current_rect = (x, y, w, h)

    while remaining:
        row.append(remaining[0])
        side = current_rect[2] if is_horizontal else current_rect[3]
        # 如果新增后的行更好（或是第一项），就接受；否则布局当前行
        if len(row) == 1 or worst_aspect_ratio(row, side) <= worst_aspect_ratio(row[:-1], side):
            remaining.pop(0)
        else:
            # 回退最后一个
            row.pop()
            new_rect = layout_row(row, current_rect, is_horizontal)
            if new_rect is None:
                break
            current_rect = new_rect  # type: ignore[assignment]
            row = []
            is_horizontal = not is_horizontal

    if row:
        layout_row(row, current_rect, is_horizontal)

    return result


def build_treemap(items: List[Tuple[str, float, object]], width: int, height: int) -> List[TreemapNode]:
    """
    从 (label, size, data) 列表构建 treemap 布局。
    会自动过滤 size <= 0 的项，避免除零错误。
    """
    if not items:
        return []

    # 先过滤掉 size <= 0 的项
    filtered = [(label, float(size), data) for (label, size, data) in items if float(size) > 0]
    if not filtered:
        return []

    sizes = [size for _, size, _ in filtered]
    nodes = _squarify(sizes, (0.0, 0.0, float(width), float(height)))

    # 将 label 和 data 绑定回去
    result_nodes: List[TreemapNode] = []
    for node, (label, size, data) in zip(nodes, filtered):
        node.label = label
        node.size = float(size)
        node.data = data
        result_nodes.append(node)

    return result_nodes

