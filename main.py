import pygame
import sys
import copy
import math
import os
import json
import tempfile
import atexit
import tkinter
import tkinter.filedialog
from elements import (Element,
                      ActiveElement,
                      Charge, Magnet, Wire,
                      Power, Resistor, Capacitor, Inductor,
                      Ammeter, Voltmeter, Solenoid,
                      MetalBall, MetalShell, MetalPlate,
                      MotionCharge, RectField, CircField, RectEfield,
                      HorseshoeMagnet, TextBox)
from physics import FieldSystem
from circuit import solve_circuit
from ac_solver import solve_ac

# ---------------------------------------------------------------------------
# Temp file cleanup (for Notepad text editing)
# ---------------------------------------------------------------------------
_temp_files = set()

def _cleanup_temp_files():
    for p in list(_temp_files):
        try:
            os.unlink(p)
        except Exception:
            pass
    _temp_files.clear()

atexit.register(_cleanup_temp_files)

# ---------------------------------------------------------------------------
# Font cache — use a Chinese-capable system font
# ---------------------------------------------------------------------------
_font_cache = {}

def get_font(size, bold=False):
    """Return a cached font of the given size with Chinese support."""
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(
            'simsun,nsimsun,microsoftyahei,simhei', size, bold=bold)
    return _font_cache[key]

# ---------------------------------------------------------------------------
# Constants - auto detect screen resolution
# ---------------------------------------------------------------------------
_root_tk = tkinter.Tk()
_root_tk.withdraw()
SCREEN_W = _root_tk.winfo_screenwidth()
SCREEN_H = _root_tk.winfo_screenheight()
_root_tk.destroy()
del _root_tk
TOP_BAR_H = 44
TOOLBAR_W = 104
CAT_TAB_H = 60  # category tab bar height in the left toolbar

# ── 霓虹玻璃拟态主题 (Neon Glass — 紫主青辅) ─────────────────────────
# 参考现代仪表盘 UI：深黑底 + 角落紫/青光晕 + 圆角玻璃卡片 + 选中青色发光。
# 仅用于 UI 框架（栏/按钮/面板/网格）；物理元素本身的含义色不在此处。
PURPLE       = (139, 92, 246)    # 主强调：霓虹紫
PURPLE_DIM   = (96, 64, 168)     # 紫暗调（边框/未激活描边）
PURPLE_DEEP  = (60, 44, 104)     # 深紫（卡片/激活底）
CYAN         = (45, 212, 191)    # 副强调：青色（发光/选中）
CYAN_DIM     = (32, 140, 130)    # 青暗调
CYAN_GLOW    = (94, 234, 212)    # 青色高亮发光

# 兼容旧引用名 —— 统一指向新色，避免散落处报错
ACCENT       = CYAN              # 主强调发光色
ACCENT_DIM   = PURPLE_DIM        # 暗调边框
ACCENT_GLOW  = CYAN_GLOW         # 高亮发光

BG_CANVAS  = (10, 11, 18)        # 画布近黑底
BG_TOPBAR  = (18, 18, 30)        # 顶栏
BG_TOOLBAR = (15, 15, 26)        # 左侧工具栏
BTN_NORMAL = (30, 28, 48)        # 按钮常态（玻璃紫黑）
BTN_HOVER  = (46, 42, 72)        # 悬停
BTN_ACTIVE = PURPLE_DEEP         # 激活（深紫）
TEXT_COLOR = (224, 224, 240)     # 主文字（冷白）
BORDER     = (54, 50, 84)        # 通用边框（紫灰）
GRID_COLOR = (28, 28, 46)        # 网格线（克制的紫黑）

CARD_BG    = (24, 22, 40)        # 卡片/面板玻璃底
CARD_BORDER = (62, 56, 96)       # 卡片边框
PANEL_RADIUS = 14                # 面板圆角
BTN_RADIUS  = 10                 # 按钮圆角

# ── Global settings ──────────────────────────────────────────────────
settings = {
    'field_density': 1.0,       # 0.25 ~ 3.0
    'fps_target': 60,           # 30/60/120/0(unlimited)
}

def _apply_settings():
    field_system.field_density = settings['field_density']
    field_system.mark_dirty()

# ---------------------------------------------------------------------------
# 霓虹 UI 绘制工具（圆角 / 发光 / 角落光晕背景）
# ---------------------------------------------------------------------------

def draw_round_rect(surface, color, rect, radius=BTN_RADIUS, width=0, border_color=None, bevel=True):
    """画圆角矩形。width>0 为描边；width==0 时默认带半立体质感
    （垂直渐变 + 顶部玻璃高光 + 底部暗边）。bevel=False 则为纯色填充。"""
    rect = pygame.Rect(rect)
    r = max(0, min(radius, rect.w // 2, rect.h // 2))
    if width == 0:
        if bevel and rect.w >= 6 and rect.h >= 6:
            surface.blit(_button_surface(rect.w, rect.h, tuple(color[:3]), r), rect.topleft)
        else:
            pygame.draw.rect(surface, color, rect, border_radius=r)
        if border_color is not None:
            pygame.draw.rect(surface, border_color, rect, 1, border_radius=r)
    else:
        pygame.draw.rect(surface, color, rect, width, border_radius=r)


# 半立体按钮表面缓存：key=(w,h,base,radius) -> Surface
_btn_surf_cache = {}

def _button_surface(w, h, base, radius):
    """生成带垂直渐变(上亮下暗)+顶部玻璃高光+底部暗边的圆角按钮表面。"""
    key = (w, h, base, radius)
    s = _btn_surf_cache.get(key)
    if s is not None:
        return s
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    top = tuple(min(255, int(c + 24)) for c in base)   # 顶部更亮
    bot = tuple(max(0, int(c - 28)) for c in base)      # 底部更暗
    # 垂直渐变
    for yy in range(h):
        t = yy / max(1, h - 1)
        col = tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
        pygame.draw.line(s, col, (0, yy), (w, yy))
    # 顶部玻璃高光（上半部半透明白色光泽）
    gloss = pygame.Surface((w, h), pygame.SRCALPHA)
    gh = max(3, int(h * 0.46))
    pygame.draw.rect(gloss, (255, 255, 255, 30), (2, 1, w - 4, gh),
                     border_radius=radius)
    s.blit(gloss, (0, 0))
    # 顶部一道更亮的高光细线
    pygame.draw.line(s, (255, 255, 255, 60), (radius, 1), (w - radius, 1))
    # 底部暗边（增强立体感）
    pygame.draw.line(s, (0, 0, 0, 70), (radius, h - 2), (w - radius, h - 2))
    # 圆角遮罩
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _btn_surf_cache[key] = s
    return s


# 发光光晕缓存：key=(w,h,color,intensity) -> Surface
_glow_cache = {}

def draw_glow(surface, rect, color, intensity=110, spread=10, radius=BTN_RADIUS):
    """在 rect 周围画一圈柔和发光（多层半透明圆角矩形外扩）。"""
    rect = pygame.Rect(rect)
    key = (rect.w, rect.h, color, intensity, spread, radius)
    glow = _glow_cache.get(key)
    if glow is None:
        pad = spread
        gw, gh = rect.w + pad * 2, rect.h + pad * 2
        glow = pygame.Surface((gw, gh), pygame.SRCALPHA)
        layers = spread
        for i in range(layers, 0, -1):
            a = int(intensity * (i / layers) ** 2 / layers * 2.2)
            a = max(0, min(255, a))
            rr = pygame.Rect(pad - i, pad - i, rect.w + i * 2, rect.h + i * 2)
            pygame.draw.rect(glow, (*color, a), rr,
                             border_radius=radius + i)
        _glow_cache[key] = glow
    surface.blit(glow, (rect.x - spread, rect.y - spread))


# 角落径向光晕背景缓存
_ambient_bg = None
_ambient_size = (0, 0)

def _radial_glow(size, center, color, max_alpha, frac_radius):
    """生成一张径向渐变发光 Surface（中心亮 -> 边缘透明）。"""
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    radius = int(max(w, h) * frac_radius)
    cx, cy = center
    # 用同心圆叠加近似径向渐变（步进以兼顾性能）
    step = 4
    for r in range(radius, 0, -step):
        t = 1.0 - r / radius
        a = int(max_alpha * (t ** 1.8))
        if a <= 0:
            continue
        pygame.draw.circle(surf, (*color, a), (int(cx), int(cy)), r)
    return surf

def build_ambient_bg(w, h):
    """构建角落光晕背景：近黑底 + 右上紫光 + 左下青光。"""
    global _ambient_bg, _ambient_size
    bg = pygame.Surface((w, h))
    bg.fill(BG_CANVAS)
    # 右上紫色光晕
    bg.blit(_radial_glow((w, h), (w * 0.86, h * 0.12),
                         (120, 70, 220), 70, 0.55), (0, 0))
    # 左下青色光晕
    bg.blit(_radial_glow((w, h), (w * 0.10, h * 0.92),
                         (30, 150, 150), 55, 0.5), (0, 0))
    # 左上淡紫，补一点层次
    bg.blit(_radial_glow((w, h), (w * 0.18, h * 0.10),
                         (90, 60, 160), 32, 0.4), (0, 0))
    _ambient_bg = bg
    _ambient_size = (w, h)

def get_ambient_bg(w, h):
    if _ambient_bg is None or _ambient_size != (w, h):
        build_ambient_bg(w, h)
    return _ambient_bg

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
camera = {'x': 0.0, 'y': 0.0, 'zoom': 1.0, 'angle': 0.0}


def world_to_screen(wx, wy):
    cx, cy = camera['x'], camera['y']
    zoom = camera['zoom']
    dx = (wx - cx) * zoom
    dy = (wy - cy) * zoom
    angle = camera.get('angle', 0.0)
    if angle != 0.0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx, dy = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a
    return dx + SCREEN_W / 2, dy + SCREEN_H / 2


def screen_to_world(sx, sy):
    cx, cy = camera['x'], camera['y']
    zoom = camera['zoom']
    angle = camera.get('angle', 0.0)
    # undo screen centering
    dx = (sx - SCREEN_W / 2) / zoom
    dy = (sy - SCREEN_H / 2) / zoom
    if angle != 0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        # undo rotation
        dx, dy = dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a
    return dx + cx, dy + cy


def zoom_at(screen_pos, factor):
    old = camera['zoom']
    new = max(0.1, min(5.0, old * factor))
    if new == old:
        return
    camera['zoom'] = new
    # Camera is locked to (0,0) — zoom always centers on origin


SNAP_THRESHOLD = 15  # world-coord distance for terminal snapping


def snap_to_terminal(wx, wy, elements, wire_points=None):
    """Snap (wx, wy) to the nearest terminal or wire endpoint if close enough.

    wire_points : list | None  — current wire being drawn (to close loops).
    """
    best_d = SNAP_THRESHOLD
    best = (wx, wy)
    for e in elements:
        if isinstance(e, ActiveElement):
            for cx, cy in e.get_connection_points():
                d = math.hypot(wx - cx, wy - cy)
                if d < best_d:
                    best_d = d
                    best = (cx, cy)
        elif isinstance(e, Wire):
            # Snap to wire endpoints (first and last point)
            for pt in (e.points[0], e.points[-1]):
                d = math.hypot(wx - pt[0], wy - pt[1])
                if d < best_d:
                    best_d = d
                    best = (pt[0], pt[1])
    # Also snap to the starting point of the wire being drawn
    if wire_points and len(wire_points) > 0:
        sx, sy = wire_points[0]
        d = math.hypot(wx - sx, wy - sy)
        if d < best_d:
            best_d = d
            best = (sx, sy)
    return best


def ortho_snap(px, py, wx, wy, threshold_deg=20):
    """Snap (wx,wy) to horizontal or vertical relative to (px,py) if close enough."""
    dx = wx - px
    dy = wy - py
    if abs(dx) < 3 and abs(dy) < 3:
        return wx, wy
    angle = math.degrees(math.atan2(abs(dy), abs(dx)))
    if angle < threshold_deg:
        return wx, py
    elif angle > 90 - threshold_deg:
        return px, wy
    return wx, wy


def _update_meter_peaks(currents):
    """Update running peak tracking for AC meters (called each sub-step)."""
    for e in elements:
        if isinstance(e, Ammeter):
            raw = currents.get(e, 0.0)
            e._rms_max = max(e._rms_max, raw)
            e._rms_min = min(e._rms_min, raw)
        elif isinstance(e, Voltmeter):
            I = currents.get(e, 0.0)
            raw = I * Voltmeter.R_METER
            e._rms_max = max(e._rms_max, raw)
            e._rms_min = min(e._rms_min, raw)

def _update_meters(currents):
    """Update ammeter/voltmeter display values after a circuit solve.
    For AC circuits, computes RMS from tracked peak values (converges after ~2 cycles).
    """
    has_ac = any(isinstance(e, Power) and e.mode == 'AC' and e.switched_on
                 for e in elements)
    for e in elements:
        if isinstance(e, Ammeter):
            raw = currents.get(e, 0.0)
            e.is_ac = has_ac
            if has_ac:
                e._rms_max = max(e._rms_max, raw)
                e._rms_min = min(e._rms_min, raw)
                amp = (e._rms_max - e._rms_min) / 2
                e._rms_value = amp / math.sqrt(2) if amp > 1e-12 else 0.0
                e.display_value = e._rms_value
            else:
                e.display_value = raw
        elif isinstance(e, Voltmeter):
            I = currents.get(e, 0.0)
            raw = I * Voltmeter.R_METER
            e.is_ac = has_ac
            if has_ac:
                e._rms_max = max(e._rms_max, raw)
                e._rms_min = min(e._rms_min, raw)
                amp = (e._rms_max - e._rms_min) / 2
                e._rms_value = amp / math.sqrt(2) if amp > 1e-12 else 0.0
                e.display_value = e._rms_value
            else:
                e.display_value = raw

def _is_pure_ac_circuit():
    """Check if all switched-on sources are AC (pure AC steady state)."""
    has_active = False
    ac_freq = None
    for e in elements:
        if isinstance(e, Power) and e.switched_on:
            has_active = True
            if e.mode != 'AC':
                return False, None  # DC source present → not pure AC
            if ac_freq is None:
                ac_freq = e.frequency
            elif abs(e.frequency - ac_freq) > 1e-6:
                return False, None  # mixed frequencies → can't use single-freq phasor
    return has_active, ac_freq


def _has_ac_source():
    """Check if any switched-on AC source exists (suppress B-field if so)."""
    for e in elements:
        if isinstance(e, Power) and e.switched_on and e.mode == 'AC':
            return True
    return False


def _update_meters_phasor(currents, node_v):
    """Update meter display values from phasor results (RMS = abs(phasor))."""
    has_ac = any(isinstance(e, Power) and e.mode == 'AC' and e.switched_on
                 for e in elements)
    for e in elements:
        if isinstance(e, Ammeter):
            e.is_ac = has_ac
            e.display_value = abs(currents.get(e, 0j))
        elif isinstance(e, Voltmeter):
            I = currents.get(e, 0j)
            e.is_ac = has_ac
            e.display_value = abs(I * Voltmeter.R_METER)


def _cap_voltages_from_nodes(node_v):
    """Extract capacitor RMS voltages from phasor node-voltage dict."""
    # Build terminal/node mapping (same logic as ac_solver.py)
    terminals = []
    for e in elements:
        if isinstance(e, Wire):
            for pt in e.points:
                terminals.append((pt[0], pt[1], e))
        elif isinstance(e, ActiveElement):
            a, b = e.get_connection_points()
            terminals.append((a[0], a[1], e))
            terminals.append((b[0], b[1], e))
    if len(terminals) < 2:
        return {}
    parent = list(range(len(terminals)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for i in range(len(terminals)):
        xi, yi = terminals[i][:2]
        for j in range(i + 1, len(terminals)):
            xj, yj = terminals[j][:2]
            if math.hypot(xi - xj, yi - yj) < 15:
                union(i, j)
    root_to_node = {}
    term_node = [-1] * len(terminals)
    for i in range(len(terminals)):
        r = find(i)
        if r not in root_to_node:
            root_to_node[r] = len(root_to_node)
        term_node[i] = root_to_node[r]
    cv = {}
    for e in elements:
        if isinstance(e, Capacitor):
            indices = [i for i, t in enumerate(terminals) if t[2] is e]
            if len(indices) >= 2:
                ni, nj = term_node[indices[0]], term_node[indices[1]]
                cv[e] = abs(node_v.get(ni, 0j) - node_v.get(nj, 0j))
    return cv


def solve_and_update():
    """Run circuit solver (DC transient or AC phasor), write currents back, refresh field."""
    global circuit_errors
    pure_ac, ac_freq = _is_pure_ac_circuit()

    if pure_ac:
        currents, node_v, circuit_errors = solve_ac(elements, frequency=ac_freq)
        for e in elements:
            if isinstance(e, Wire) and e.auto_current:
                e.current = abs(currents.get(e, 0j))
                e.is_ac = True
            elif isinstance(e, ActiveElement):
                e.current = abs(currents.get(e, 0j))
        _update_meters_phasor(currents, node_v)
    else:
        currents, circuit_errors, _, _ = solve_circuit(elements)
        for e in elements:
            if isinstance(e, Wire) and e.auto_current:
                e.current = currents.get(e, 0.0)
                e.is_ac = _has_ac_source()
            elif isinstance(e, ActiveElement):
                e.current = currents.get(e, 0.0)
        _update_meters(currents)
    field_system.mark_dirty()


# ── Faraday's law: electromagnetic induction ──────────────────────────

def _find_wire_loops(elements):
    """Find closed wire loops for flux computation using fundamental cycles.

    Returns list of (points_list, approx_resistance).
    """
    from collections import defaultdict

    graph = defaultdict(set)    # node_key → {neighbor_key, ...}
    edge_map = {}               # (node_a, node_b) → list of elements on that edge

    def node_key(x, y):
        return (round(x, 1), round(y, 1))

    def add_edge(a, b, elem):
        na, nb = node_key(*a), node_key(*b)
        if na == nb:
            return
        graph[na].add(nb)
        graph[nb].add(na)
        ek = (min(na, nb), max(na, nb))
        edge_map.setdefault(ek, []).append(elem)

    for e in elements:
        if isinstance(e, Wire):
            pts = e.points
            for i in range(len(pts) - 1):
                add_edge(pts[i], pts[i+1], e)
            # Close the loop if first and last points are close
            if len(pts) >= 3:
                d = math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
                if d < SNAP_THRESHOLD:
                    add_edge(pts[-1], pts[0], e)
        elif isinstance(e, ActiveElement):
            a, b = e.get_connection_points()
            add_edge(a, b, e)

    if not graph:
        return []

    # ── Find fundamental cycles via DFS spanning tree ──
    parent = {}
    tree_edges = set()
    all_edges = set()
    visited = set()

    def dfs(n, p):
        visited.add(n)
        parent[n] = p
        for nb in graph[n]:
            ek = (min(n, nb), max(n, nb))
            all_edges.add(ek)
            if nb == p:
                continue
            if nb not in visited:
                tree_edges.add(ek)
                dfs(nb, n)

    for n in graph:
        if n not in visited:
            dfs(n, None)

    back_edges = {e for e in all_edges if e not in tree_edges}

    # Reconstruct tree path for each back edge
    def tree_path(u, v):
        """Return list of nodes from u up to v via DFS tree (v inclusive)."""
        # Walk from u up to root, same for v, then find junction
        path_u = []
        while u is not None:
            path_u.append(u)
            if u == v:
                return path_u
            u = parent.get(u)
        path_v = []
        while v is not None:
            path_v.append(v)
            v = parent.get(v)
        # Find junction
        set_u = set(path_u)
        for n in path_v:
            if n in set_u:
                junction = n
                break
        else:
            return []
        # Build path: u → ... → junction → ... → v
        u_to_j = []
        for n in path_u:
            u_to_j.append(n)
            if n == junction:
                break
        v_to_j = []
        for n in path_v:
            if n == junction:
                break
            v_to_j.append(n)
        # v_to_j goes from v upward; reverse to get junction → ... → v
        return u_to_j + list(reversed(v_to_j))

    loops = []
    seen = set()

    for u, v in back_edges:
        path = tree_path(u, v)
        if len(path) < 3:  # need at least 3 nodes for a polygon
            continue
        # Compute area
        area = 0.0
        n = len(path)
        for i in range(n):
            x1, y1 = path[i]
            x2, y2 = path[(i + 1) % n]
            area += x1 * y2 - x2 * y1
        area = area / 2.0
        if abs(area) < 20:  # minimum area threshold (px²)
            continue
        # Deduplicate: use sorted tuple of vertices as key
        key = tuple(sorted(path))
        if key in seen:
            continue
        seen.add(key)
        # Estimate total resistance along the cycle
        total_R = 0.0
        for i in range(len(path) - 1):
            a, b = path[i], path[i+1]
            ek = (min(a, b), max(a, b))
            for elem in edge_map.get(ek, []):
                if isinstance(elem, Wire):
                    seg_len = math.hypot(a[0]-b[0], a[1]-b[1])
                    total_R += 0.01 / max(1, len(elem.points)-1) * seg_len
                elif hasattr(elem, 'resistance'):
                    total_R += elem.resistance
                elif isinstance(elem, (Ammeter, Voltmeter)):
                    total_R += getattr(elem, 'R_METER', 1.0)
        # Collect wire elements on this cycle
        wire_elems = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i+1]
            ek = (min(a, b), max(a, b))
            for elem in edge_map.get(ek, []):
                if isinstance(elem, Wire) and elem not in wire_elems:
                    wire_elems.append(elem)
        loops.append((path, total_R, wire_elems))

    return loops


def _compute_induced_emfs(elements, loops, field_system, dt, faraday_time=0.0):
    """Compute induced EMF for all solenoids and closed wire loops.

    Returns dict:
        Solenoid → induced voltage (V)
        ('loop_current', id) → (pts_list, I_ind, wire_elems)

    Also updates _flux_history for the next timestep.
    """
    global _flux_history, _loop_cache
    induced = {}

    # ── 1. Solenoids ──
    for e in elements:
        if isinstance(e, Solenoid):
            try:
                flux = field_system.compute_solenoid_flux(e, elements)
            except Exception:
                continue
            key = ('sol', id(e))
            flux_prev = _flux_history.get(key, flux)
            _flux_history[key] = flux
            if abs(dt) > 1e-15:
                dflux_dt = (flux - flux_prev) / dt
                # Induced EMF: ε = -N·dΦ/dt (Lenz's law)
                emf = -e.turns * dflux_dt
                induced[e] = emf

    # ── 2. Wire loops ──
    # Build mapping: rounded node_key → actual unrounded coordinates
    # (avoids flux jumps from node_key rounding to 1dp)
    _key_to_actual = {}
    for e in elements:
        if isinstance(e, Wire):
            for pt in e.points:
                _key_to_actual[(round(pt[0], 1), round(pt[1], 1))] = tuple(pt)

    _loop_cache = loops

    for pts_rounded, total_R, wire_elems in loops:
        # Reconstruct polygon with actual coordinates
        pts = [_key_to_actual.get(nk, nk) for nk in pts_rounded]
        flux = field_system.compute_loop_flux(pts, elements, faraday_time)
        # Use stable key from wire element ids (survives coordinate changes)
        wire_key = frozenset(id(w) for w in wire_elems) if wire_elems else frozenset(pts_rounded)
        key = ('loop', wire_key)
        flux_prev = _flux_history.get(key, flux)
        _flux_history[key] = flux
        if abs(dt) > 1e-15 and total_R > 1e-10:
            dflux_dt = (flux - flux_prev) / dt
            emf = -dflux_dt
            I_ind = emf / total_R
            induced[('loop_current', id(pts_rounded))] = (pts, I_ind, wire_elems)

    return induced


def _apply_loop_currents(induced, elements):
    """Apply induced currents from wire loops directly to wire segments."""
    for key, val in list(induced.items()):
        if isinstance(key, tuple) and key[0] == 'loop_current':
            pts, I_ind, wire_elems = val
            for w in wire_elems:
                if w in elements and w.auto_current:
                    w.current = I_ind
categories = ['electrostatic', 'circuit', 'magnetic']
category_labels = {'electrostatic': '静电学', 'circuit': '电流学', 'magnetic': '磁学'}

tools = {
    'electrostatic': [
        {'label': '文本框', 'mode': 'add_textbox',    'icon': 'T'},
        {'label': '正电荷', 'mode': 'add_charge_pos', 'icon': '+'},
        {'label': '负电荷', 'mode': 'add_charge_neg', 'icon': '-'},
        {'label': '金属球', 'mode': 'add_metal_ball', 'icon': '●'},
        {'label': '球壳', 'mode': 'add_metal_shell', 'icon': '○'},
        {'label': '金属板', 'mode': 'add_metal_plate', 'icon': '■'},
        {'label': '运动电荷', 'mode': 'add_motion_charge', 'icon': '⊙'},
    ],
    'circuit': [
        {'label': '文本框',  'mode': 'add_textbox',    'icon': 'T'},
        {'label': '导线',  'mode': 'add_wire',       'icon': '≈'},
        {'label': '电源',  'mode': 'add_power',      'icon': '≡'},
        {'label': '电阻',  'mode': 'add_resistor',   'icon': 'Ω'},
        {'label': '电容',  'mode': 'add_capacitor',  'icon': '‖'},
        {'label': '电感',  'mode': 'add_inductor',   'icon': 'L'},
        {'label': '螺线管', 'mode': 'add_solenoid',  'icon': '◎'},
        {'label': '电流表', 'mode': 'add_ammeter',   'icon': 'A'},
        {'label': '电压表', 'mode': 'add_voltmeter', 'icon': 'V'},
    ],
    'magnetic': [
        {'label': '文本框',     'mode': 'add_textbox',         'icon': 'T'},
        {'label': '磁铁',     'mode': 'add_magnet',          'icon': 'M'},
        {'label': '马蹄磁铁',  'mode': 'add_horseshoe_magnet','icon': 'Ω'},
        {'label': '矩形磁场',  'mode': 'add_rect_field',     'icon': '□'},
        {'label': '圆形磁场',  'mode': 'add_circ_field',     'icon': '○'},
        {'label': '平行电场',  'mode': 'add_rect_efield',    'icon': '→'},
        {'label': '自由电荷',  'mode': 'add_motion_charge',  'icon': '⊙'},
    ],
}

# Field-line toggle buttons (drawn in the toolbar area after the tools)
field_toggles = [
    {'label': 'E 线', 'key': 'show_efield', 'color': (255, 180, 50)},
    {'label': 'B 线', 'key': 'show_bfield', 'color': (80, 200, 255)},
]

phase7_toggles = [
    {'label': '法拉第', 'key': 'faraday_active', 'color': (255, 100, 255)},
]

top_buttons = [
    {'label': '新建', 'action': 'new'},
    {'label': '打开', 'action': 'open'},
    {'label': '保存', 'action': 'save'},
    {'label': '播放', 'action': 'play'},
    {'label': '暂停', 'action': 'pause'},
    {'label': '还原', 'action': 'revert'},
    {'label': '退出', 'action': 'exit'},
]


def get_tool_rects():
    """Compute rects for left-toolbar tool buttons of the current category.
    自适应：保证所有工具按钮落在底部 toggle 区(SCREEN_H-128)上方，不重叠。"""
    rects = []
    cat_tools = tools[current_category]
    # Start tools below the vertical category tabs
    n_cats = len(categories)
    tab_h = 32
    gap = 4
    tabs_bottom = TOP_BAR_H + 6 + n_cats * tab_h + (n_cats - 1) * gap + 10
    n = len(cat_tools)
    # 底部 toggle 区上沿（与 draw/hit-test 中的 SCREEN_H-128 一致）留 8px 安全边距
    avail = (SCREEN_H - 128) - 8 - tabs_bottom
    ideal_step = 58
    if n > 0 and avail > 0:
        step = max(38, min(ideal_step, avail // n))
    else:
        step = ideal_step
    btn_h = max(30, min(48, step - 8))
    for i in range(n):
        y = tabs_bottom + i * step
        rects.append(pygame.Rect(12, y, TOOLBAR_W - 24, btn_h))
    return rects


def get_cat_tab_rects():
    """Precompute vertical category tab button rects in the left toolbar."""
    rects = []
    tab_y = TOP_BAR_H + 6
    tab_h = 32
    tab_w = TOOLBAR_W - 10
    gap = 4
    for i, _ in enumerate(categories):
        rects.append(pygame.Rect(5, tab_y + i * (tab_h + gap), tab_w, tab_h))
    return rects


def get_top_button_rects():
    """Compute rects for top-bar buttons."""
    rects = []
    x = 12
    for btn in top_buttons:
        w = max(18 * len(btn['label']) + 18, 56)
        rects.append(pygame.Rect(x, 5, w, TOP_BAR_H - 10))
        x += w + 6
    return rects


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_pool = []  # single shared list for all categories
_saved_elements = {'electrostatic': _pool, 'circuit': _pool, 'magnetic': _pool}
current_category = 'electrostatic'
elements = _saved_elements['electrostatic']  # alias to the shared pool
selected = None
mode = 'select'

dragging = False
drag_start_mouse = None
drag_start_pos = None

tool_rects = get_tool_rects()
top_btn_rects = get_top_button_rects()
cat_tab_rects = get_cat_tab_rects()

clock = pygame.time.Clock()
running = True
fps = 0

# Context menu & editing state
context_menu = None   # {'pos': (x,y), 'target': elem, 'items': [...]}
editing_element = None
_edit_buttons = []     # [(rect, callback), ...]
_edit_fields = []      # [(rect, elem, attr, min_val, max_val, is_angle)]
_scrub_target = None   # {'elem','attr','start_x','start_val','min_val','max_val','is_angle'}

# Right-click resize state (RectField / CircField edge drag)
_resize_target = None
_resize_handle = None
_resize_start_mouse = None
_resize_start_vals = None

# Field system
field_system = FieldSystem()
show_efield = True
show_bfield = True

# Phase 7 state
simulation_playing = False
faraday_active = False
faraday_time = 0.0
sim_time = 0.0

# Transient circuit state (capacitor voltages, inductor currents)
cap_voltages = {}
ind_currents = {}

# Faraday's law: flux tracking for electromagnetic induction
_flux_history = {}       # {id(loop/solenoid): previous_flux}
_loop_cache = []
_induced_display = []    # [(center_x, center_y, emf, current, resistance), ...]         # cached list of (points, resistance, element) for each found loop

# Simulation speed
sim_speed = 1.0

# Copy/paste clipboard
_clipboard = None

# Text input state (for edit panel number input)
_active_input = None  # {'elem','attr','text','min_val','max_val','also_initial'}
_speed_rect = None

# Trail recording toggle
record_trail = True
_trail_rect = None
_clear_trail_rect = None
_undo_btn_rect = None

# Rotation slider
_rotation_slider_rect = None
_rotation_track_rect = None
_slider_last_click = 0   # last MOUSEBUTTONDOWN timestamp on slider handle
_skip_slider_poll = False  # set when double-click resets angle, cleared after one frame

# Global settings panel
_gs_sliders = []
_gs_close_rect = None
_gs_fps_btns = []

# Circuit solver status
circuit_errors = []

# Canvas right-click menu & measurement
canvas_menu = None   # {'pos':(x,y), 'rect': Rect, 'items': [...]}
measuring = False
measure_text = ""

# Wire drawing state
wire_points = []
last_click_time = 0
DOUBLE_CLICK_MS = 300

# Global design panel
global_panel_open = False
GLOBAL_PANEL_W = 250

# Undo stack & pre-play snapshot
_undo_dir = None      # temp directory for multi-step undo stack
_undo_stack = []      # list of (.json) filenames in the undo directory, oldest first
_undo_limit = 50      # max undo steps
_presnap_elements = None  # serialized pre-play snapshot (list of dicts)

# ---------------------------------------------------------------------------
# Study mode state
# ---------------------------------------------------------------------------
study_mode = False
study_projects = []
study_project_index = 0
study_project_name = ""
_study_next_rect = None       # "后一个" button rect
_study_prev_rect = None       # "前一个" button rect
_exit_to_home = False         # signal to return to home screen

STUDY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'study')

# ---------------------------------------------------------------------------
# Undo / Pre-play snapshot helpers
# ---------------------------------------------------------------------------

def _serialize_elements(elems):
    """Return a list of dicts describing each element's type and parameters."""
    data = []
    for e in elems:
        if isinstance(e, Charge):
            data.append({'type': 'Charge', 'x': e.x, 'y': e.y, 'q': e.q,
                         'radius': e.radius})
        elif isinstance(e, Magnet):
            data.append({'type': 'Magnet', 'x': e.x, 'y': e.y,
                         'strength': e.strength, 'angle': e.angle,
                         'length': e.length, 'height': e.height})
        elif isinstance(e, HorseshoeMagnet):
            data.append({'type': 'HorseshoeMagnet', 'x': e.x, 'y': e.y,
                         'strength': e.strength, 'angle': e.angle,
                         'gap': e.gap, 'arm_length': e.arm_length,
                         'thickness': e.thickness})
        elif isinstance(e, Wire):
            data.append({'type': 'Wire', 'points': e.points, 'current': e.current,
                         'auto_current': e.auto_current,
                         'vx': e.vx, 'vy': e.vy})
        elif isinstance(e, Power):
            data.append({'type': 'Power', 'x': e.x, 'y': e.y,
                         'ptype': e.ptype, 'value': e.value,
                         'angle': e.angle, 'mode': e.mode,
                         'switched_on': e.switched_on})
        elif isinstance(e, Resistor):
            data.append({'type': 'Resistor', 'x': e.x, 'y': e.y,
                         'resistance': e.resistance, 'angle': e.angle})
        elif isinstance(e, Capacitor):
            data.append({'type': 'Capacitor', 'x': e.x, 'y': e.y,
                         'capacitance': e.capacitance, 'angle': e.angle})
        elif isinstance(e, Inductor):
            data.append({'type': 'Inductor', 'x': e.x, 'y': e.y,
                         'inductance': e.inductance, 'angle': e.angle})
        elif isinstance(e, MetalBall):
            data.append({'type': 'MetalBall', 'x': e.x, 'y': e.y,
                         'r_outer': e.r_outer, 'r_inner': e.r_inner})
        elif isinstance(e, MetalShell):
            data.append({'type': 'MetalShell', 'x': e.x, 'y': e.y,
                         'inner_radius': e.inner_radius, 'thickness': e.thickness})
        elif isinstance(e, MetalPlate):
            data.append({'type': 'MetalPlate', 'x': e.x, 'y': e.y,
                         'thickness': e.thickness, 'angle': e.angle})
        elif isinstance(e, MotionCharge):
            data.append({'type': 'MotionCharge', 'x': e.x, 'y': e.y,
                         'q': e.q, 'mass': e.mass, 'vx': e.vx, 'vy': e.vy,
                         'radius': e.radius, 'fixed': e.fixed})
        elif isinstance(e, RectField):
            data.append({'type': 'RectField', 'x': e.x, 'y': e.y,
                         'width': e.width, 'height': e.height,
                         'B_mag': e.B_mag, 'direction': e.direction})
        elif isinstance(e, CircField):
            data.append({'type': 'CircField', 'x': e.x, 'y': e.y,
                         'radius': e.radius, 'B_mag': e.B_mag,
                         'direction': e.direction})
        elif isinstance(e, RectEfield):
            data.append({'type': 'RectEfield', 'x': e.x, 'y': e.y,
                         'width': e.width, 'height': e.height,
                         'E_mag': e.E_mag, 'direction': e.direction,
                         'angle': e.angle})
        elif isinstance(e, Solenoid):
            data.append({'type': 'Solenoid', 'x': e.x, 'y': e.y,
                         'coil_length': e.coil_length, 'coil_radius': e.coil_radius,
                         'turns': e.turns, 'angle': e.angle,
                         'winding_clockwise': e.winding_clockwise})
        elif isinstance(e, TextBox):
            data.append({'type': 'TextBox', 'x': e.x, 'y': e.y,
                         'text': e.text,
                         'box_width': e.box_width, 'box_height': e.box_height,
                         'font_size': e.font_size})
    return data


def _deserialize_elements(data):
    """Reconstruct element objects from a list of dicts (inverse of _serialize_elements)."""
    elems = []
    for d in data:
        typ = d['type']
        try:
            if typ == 'Charge':
                e = Charge(d['x'], d['y'], q=d['q'])
                if 'radius' in d:
                    e.radius = d['radius']
            elif typ == 'Magnet':
                e = Magnet(d['x'], d['y'], strength=d['strength'],
                           angle=d['angle'], length=d['length'], height=d['height'])
            elif typ == 'HorseshoeMagnet':
                e = HorseshoeMagnet(d['x'], d['y'], strength=d['strength'],
                                    angle=d['angle'], gap=d.get('gap', 50),
                                    arm_length=d.get('arm_length', 80),
                                    thickness=d.get('thickness', 20))
            elif typ == 'Wire':
                e = Wire(d['points'], current=d['current'])
                e.auto_current = d.get('auto_current', True)
                e.vx = d.get('vx', 0.0)
                e.vy = d.get('vy', 0.0)
            elif typ == 'Power':
                e = Power(d['x'], d['y'], ptype=d['ptype'], value=d['value'],
                          angle=d['angle'], mode=d.get('mode', 'DC'))
                e.switched_on = d.get('switched_on', False)
            elif typ == 'Resistor':
                e = Resistor(d['x'], d['y'], resistance=d['resistance'],
                             angle=d.get('angle', 0))
            elif typ == 'Capacitor':
                e = Capacitor(d['x'], d['y'], capacitance=d['capacitance'],
                              angle=d.get('angle', 0))
            elif typ == 'Inductor':
                e = Inductor(d['x'], d['y'], inductance=d['inductance'],
                             angle=d.get('angle', 0))
            elif typ == 'Solenoid':
                e = Solenoid(d['x'], d['y'],
                             coil_length=d.get('coil_length', 140),
                             coil_radius=d.get('coil_radius', 25),
                             turns=d.get('turns', 30),
                             angle=d.get('angle', 0.0))
                e.winding_clockwise = d.get('winding_clockwise', True)
            elif typ == 'TextBox':
                e = TextBox(d['x'], d['y'],
                            text=d.get('text', '备注'),
                            box_width=d.get('box_width', 160),
                            box_height=d.get('box_height', 60),
                            font_size=d.get('font_size', 18))
            elif typ == 'MetalBall':
                e = MetalBall(d['x'], d['y'], r_outer=d['r_outer'],
                              r_inner=d.get('r_inner', 0))
            elif typ == 'MetalShell':
                e = MetalShell(d['x'], d['y'], inner_radius=d['inner_radius'],
                               thickness=d['thickness'])
            elif typ == 'MetalPlate':
                e = MetalPlate(d['x'], d['y'], thickness=d['thickness'],
                               angle=d.get('angle', 0))
            elif typ == 'MotionCharge':
                e = MotionCharge(d['x'], d['y'], q=d['q'], mass=d['mass'],
                                 vx=d.get('vx', 0), vy=d.get('vy', 0))
                if 'radius' in d:
                    e.radius = d['radius']
                e.fixed = d.get('fixed', False)
            elif typ == 'RectField':
                e = RectField(d['x'], d['y'], width=d.get('width', 200),
                              height=d.get('height', 150), B_mag=d.get('B_mag', 50),
                              direction=d.get('direction', 1))
            elif typ == 'CircField':
                e = CircField(d['x'], d['y'], radius=d.get('radius', 100),
                              B_mag=d.get('B_mag', 50), direction=d.get('direction', 1))
            elif typ == 'RectEfield':
                e = RectEfield(d['x'], d['y'], width=d.get('width', 200),
                               height=d.get('height', 150), E_mag=d.get('E_mag', 500),
                               direction=d.get('direction', 1),
                               angle=d.get('angle', 0.0))
            else:
                continue
            elems.append(e)
        except Exception as ex:
            print(f"Deserialize error for {typ}: {ex}")
    return elems


def _save_undo_snapshot():
    """Push current element state onto the undo stack (temp directory)."""
    global _undo_dir, _undo_stack
    try:
        data = _serialize_elements(elements)
        if _undo_dir is None:
            _undo_dir = tempfile.mkdtemp(prefix='emag_undo_')
            _undo_stack = []
        idx = len(_undo_stack)
        path = os.path.join(_undo_dir, f'{idx:04d}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        _undo_stack.append(path)
        # Keep within limit
        while len(_undo_stack) > _undo_limit:
            old = _undo_stack.pop(0)
            try:
                os.remove(old)
            except Exception:
                pass
    except Exception as ex:
        print(f"Undo save error: {ex}")


def _do_undo():
    """Step back one undo level (pop the latest snapshot)."""
    global _undo_dir, _undo_stack, elements, selected
    global cap_voltages, ind_currents, sim_time, _flux_history
    if not _undo_stack:
        return
    try:
        path = _undo_stack.pop()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        os.remove(path)
        new_elems = _deserialize_elements(data)
        elements[:] = new_elems
        selected = None
        cap_voltages = {}
        ind_currents = {}
        _flux_history.clear()
        sim_time = 0.0
        field_system.mark_dirty()
        solve_and_update()
    except Exception as ex:
        print(f"Undo load error: {ex}")


def _save_preplay_snapshot():
    """Save snapshot of current state when play starts (for revert)."""
    global _presnap_elements
    _presnap_elements = _serialize_elements(elements)


def _do_revert():
    """Restore to the pre-play snapshot."""
    global _presnap_elements, elements, selected, simulation_playing, faraday_time
    global cap_voltages, ind_currents, sim_time
    if _presnap_elements is None:
        return
    simulation_playing = False
    faraday_time = 0.0
    cap_voltages = {}
    ind_currents = {}
    sim_time = 0.0
    try:
        new_elems = _deserialize_elements(_presnap_elements)
        elements[:] = new_elems
        selected = None
        field_system.mark_dirty()
        solve_and_update()
    except Exception as ex:
        print(f"Revert error: {ex}")


def _cleanup_temp_files():
    """Delete undo temp directory and all files on exit."""
    global _undo_dir
    if _undo_dir and os.path.isdir(_undo_dir):
        try:
            import shutil
            shutil.rmtree(_undo_dir)
        except Exception:
            pass
    _undo_dir = None
    _undo_stack.clear()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_grid(surface):
    """Faint grid on the canvas area."""
    zoom = camera['zoom']
    # Determine grid spacing (keep it near 60 px at current zoom)
    raw_spacing = 60 / zoom
    exp = 10 ** math.floor(math.log10(raw_spacing))
    spacing = exp * round(raw_spacing / exp)
    if spacing <= 0:
        spacing = 60 / zoom

    # Visible extent in world coords
    left = (TOOLBAR_W - SCREEN_W / 2) / zoom + camera['x']
    top_ = (TOP_BAR_H - SCREEN_H / 2) / zoom + camera['y']
    right = (SCREEN_W - SCREEN_W / 2) / zoom + camera['x']
    bottom = (SCREEN_H - SCREEN_H / 2) / zoom + camera['y']

    # Snap to spacing
    gx = math.floor(left / spacing) * spacing
    gy = math.floor(top_ / spacing) * spacing

    lines = []
    x = gx
    while x <= right:
        p1 = world_to_screen(x, top_)
        p2 = world_to_screen(x, bottom)
        lines.append((p1, p2))
        x += spacing
    y = gy
    while y <= bottom:
        p1 = world_to_screen(left, y)
        p2 = world_to_screen(right, y)
        lines.append((p1, p2))
        y += spacing

    for start, end in lines:
        # Clip to visible area roughly (skip lines entirely off-canvas)
        sx, sy = start
        ex, ey = end
        if (sx < TOOLBAR_W and ex < TOOLBAR_W) or (sy < TOP_BAR_H and ey < TOP_BAR_H):
            continue
        if (sx < 0 and ex < 0) or (sx > SCREEN_W and ex > SCREEN_W):
            continue
        if (sy < TOP_BAR_H and ey < TOP_BAR_H) or (sy > SCREEN_H and ey > SCREEN_H):
            continue
        pygame.draw.line(surface, GRID_COLOR, start, end, 1)

    # ── 主轴高亮：世界坐标原点的 x/y 轴,像坐标系/示波器中心线 ──
    axis_col = (48, 42, 78)
    # 纵轴 (world x = 0)
    if left <= 0 <= right:
        ax1 = world_to_screen(0, top_)
        ax2 = world_to_screen(0, bottom)
        if not (ax1[0] < TOOLBAR_W and ax2[0] < TOOLBAR_W):
            pygame.draw.line(surface, axis_col, ax1, ax2, 1)
    # 横轴 (world y = 0)
    if top_ <= 0 <= bottom:
        ay1 = world_to_screen(left, 0)
        ay2 = world_to_screen(right, 0)
        if not (ay1[1] < TOP_BAR_H and ay2[1] < TOP_BAR_H):
            pygame.draw.line(surface, axis_col, ay1, ay2, 1)


def _draw_scene(surface, _, elements, field_system, camera, mode, wire_points,
                faraday_active, faraday_time, dt, show_efield, show_bfield):
    """Draw the simulation scene (grid + elements + field lines + wire preview)."""
    global _induced_display
    draw_grid(surface)
    # Elements (non-Charge first)
    for e in elements:
        if not isinstance(e, Charge):
            e.draw(surface, camera, (SCREEN_W, SCREEN_H))
    # Suppress B-field display if any AC source is active (direction oscillates)
    if _has_ac_source():
        show_bfield = False
    # Field lines
    if field_system.dirty or field_system._cam_changed(camera) or simulation_playing:
        field_system.generate(elements, camera, (SCREEN_W, SCREEN_H))
    field_system.draw(surface, camera, (SCREEN_W, SCREEN_H), show_efield, show_bfield, elements)
    # Faraday induced E-field overlay
    if faraday_active:
        arrows = field_system.compute_induced_efield_grid(elements, camera, (SCREEN_W, SCREEN_H), {}, faraday_time, dt)
        FieldSystem.draw_induced_efield(surface, (SCREEN_W, SCREEN_H), arrows)
    # Charges on top
    for e in elements:
        if isinstance(e, Charge):
            e.draw(surface, camera, (SCREEN_W, SCREEN_H))
    # Wire drawing preview
    _draw_wire_preview(surface, camera, mode, wire_points, elements)

    # Induced EMF / current labels
    if _induced_display:
        zoom = camera['zoom']
        try:
            font = pygame.font.Font(None, max(18, int(20 * zoom)))
        except Exception:
            font = None
        for cx, cy, emf, I_ind, total_R in _induced_display:
            sp = world_to_screen(cx, cy)
            sp = (int(sp[0]), int(sp[1] - 20 * zoom))
            abs_I = abs(I_ind)
            if abs_I > 0.1:
                label = f"ε={emf:.3f}V  I={abs_I:.2f}A"
            elif abs_I > 0.001:
                label = f"ε={emf:.4f}V  I={abs_I:.3f}A"
            else:
                label = f"ε={emf:.4f}V  I={abs_I:.4f}A"
            if font:
                txt = font.render(label, True, (255, 255, 200))
                tw, th = txt.get_size()
                pad = 4
                bx = sp[0] - tw // 2 - pad
                by = sp[1] - th // 2 - pad
                lbl_bg = pygame.Surface((tw + pad * 2, th + pad * 2))
                lbl_bg.set_alpha(200)
                lbl_bg.fill((20, 20, 40))
                surface.blit(lbl_bg, (bx, by))
                if abs_I > 0.001:
                    pygame.draw.rect(surface, (100, 255, 100), (bx, by, tw + pad * 2, th + pad * 2), 1)
                surface.blit(txt, (sp[0] - tw // 2, sp[1] - th // 2))


def _draw_wire_preview(surface, camera, mode, wire_points, elements):
    """Wire terminal points + drawing preview."""
    if mode == 'add_wire':
        for e in elements:
            if isinstance(e, ActiveElement):
                for tx, ty in e.get_connection_points():
                    tsp = world_to_screen(tx, ty)
                    tsp = (int(tsp[0]), int(tsp[1]))
                    pygame.draw.circle(surface, (100, 255, 100), tsp, max(3, int(3 * camera['zoom'])))
            elif isinstance(e, Wire):
                for tx, ty in e.points:
                    tsp = world_to_screen(tx, ty)
                    tsp = (int(tsp[0]), int(tsp[1]))
                    pygame.draw.circle(surface, (100, 255, 100), tsp, max(3, int(3 * camera['zoom'])))
    if wire_points:
        zoom = camera['zoom']
        pts = [(int(p[0]), int(p[1])) for p in [world_to_screen(wx, wy) for wx, wy in wire_points]]
        # Green dot at the start point (valid connection target to close the loop)
        pygame.draw.circle(surface, (100, 255, 100), pts[0], max(3, int(3 * zoom)))
        if len(pts) > 1:
            pygame.draw.lines(surface, (200, 150, 50), False, pts, 2)
            mx, my = pygame.mouse.get_pos()
            if mx >= TOOLBAR_W and my >= TOP_BAR_H:
                wx, wy = screen_to_world(mx, my)
                sx, sy = snap_to_terminal(wx, wy, elements, wire_points)
                lx, ly = wire_points[-1]
                ox, oy = ortho_snap(lx, ly, sx, sy)
                sp = world_to_screen(sx, sy)
                sp = (int(sp[0]), int(sp[1]))
                op = world_to_screen(ox, oy)
                op = (int(op[0]), int(op[1]))
                pygame.draw.line(surface, (200, 150, 50, 40), pts[-1], sp, 1)
                pygame.draw.line(surface, (255, 200, 80), pts[-1], op, 2)
                if (sx, sy) != (wx, wy):
                    pygame.draw.circle(surface, (100, 255, 100), sp, max(5, int(5 * zoom)), 2)
                    pygame.draw.circle(surface, (100, 255, 100), sp, max(2, int(3 * zoom)))
                if (ox, oy) != (sx, sy):
                    pygame.draw.circle(surface, (255, 200, 80), op, max(4, int(4 * zoom)), 1)
        for pt in pts:
            pygame.draw.circle(surface, (180, 140, 60), pt, 4)


def _set_angle_from_mouse(mx):
    """Update camera angle from mouse x-coordinate, mapped to the visual track."""
    global _rotation_track_rect
    if not _rotation_track_rect:
        return
    tr = _rotation_track_rect
    frac = (mx - tr.x) / tr.w
    frac = max(0.0, min(1.0, frac))
    camera['angle'] = -math.pi + frac * (2 * math.pi)


def _draw_rotation_slider(surface):
    """Draw a horizontal rotation slider at the top-right, below the top bar."""
    global _rotation_slider_rect, _rotation_track_rect
    sw, sh = SCREEN_W, SCREEN_H
    slider_w = 160
    slider_h = 14
    handle_r = 11
    x = sw - slider_w - 20
    y = TOP_BAR_H + 18
    track_rect = pygame.Rect(x, y, slider_w, slider_h)
    # Detection area larger than visual track for easier clicking
    detect_rect = pygame.Rect(x, y - 8, slider_w, slider_h + 16)
    _rotation_slider_rect = detect_rect
    _rotation_track_rect = track_rect

    angle = camera.get('angle', 0.0)
    frac = (angle + math.pi) / (2 * math.pi)

    # Track background
    draw_round_rect(surface, (26, 24, 44), track_rect, slider_h // 2, border_color=BORDER)

    # Center marker
    cx = track_rect.x + int(0.5 * slider_w)
    pygame.draw.line(surface, (90, 80, 130), (cx, track_rect.y), (cx, track_rect.bottom), 1)

    # Fill from left to handle
    hx = track_rect.x + int(frac * slider_w)
    hy = track_rect.centery
    if hx > track_rect.x:
        fill = pygame.Rect(track_rect.x, track_rect.y, hx - track_rect.x, slider_h)
        t = frac
        draw_round_rect(surface, (int(120+10*t), int(80+90*t), int(200-10*t)), fill, slider_h // 2)

    # Handle
    pygame.draw.circle(surface, PURPLE, (hx, hy), handle_r)
    pygame.draw.circle(surface, CYAN_GLOW, (hx, hy), handle_r - 3)

    # Label
    lbl = get_font(13).render(f"视角 {math.degrees(angle):+.0f}°", True, (170, 160, 210))
    surface.blit(lbl, (track_rect.x + slider_w // 2 - lbl.get_width() // 2, track_rect.y - 20))


def draw_top_bar(surface):
    pygame.draw.rect(surface, BG_TOPBAR, (0, 0, SCREEN_W, TOP_BAR_H))
    pygame.draw.line(surface, BORDER, (0, TOP_BAR_H), (SCREEN_W, TOP_BAR_H))

    font = get_font(19, bold=True)
    for i, btn in enumerate(top_buttons):
        rect = top_btn_rects[i]
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if btn['action'] == 'exit':
            color = (160, 50, 50) if hover else (100, 35, 35)
            border = (220, 80, 80) if hover else (140, 50, 50)
        else:
            color = BTN_HOVER if hover else BTN_NORMAL
            border = PURPLE_DIM if hover else BORDER
        draw_round_rect(surface, color, rect, 9, border_color=border)

        text = font.render(btn['label'], True, TEXT_COLOR)
        tr = text.get_rect(center=rect.center)
        surface.blit(text, tr)

    # Speed control
    global _speed_rect
    sp_lbl = font.render("速度:", True, TEXT_COLOR)
    sp_editing = (_active_input is not None and _active_input['attr'] == 'sim_speed')
    if sp_editing:
        sp_text = _active_input['text'] + '|'
        sp_bg = PURPLE_DEEP
    else:
        sp_text = f"{sim_speed:.2f}x"
        sp_bg = BTN_NORMAL
    sp_lbl_x = top_btn_rects[-1].right + 20
    surface.blit(sp_lbl, (sp_lbl_x, TOP_BAR_H // 2 - sp_lbl.get_height() // 2))
    sp_box = pygame.Rect(sp_lbl_x + sp_lbl.get_width() + 6, 5, 74, TOP_BAR_H - 10)
    draw_round_rect(surface, sp_bg, sp_box, 9, border_color=BORDER)
    sp_display = font.render(sp_text, True, TEXT_COLOR)
    surface.blit(sp_display, (sp_box.x + 6, sp_box.centery - sp_display.get_height() // 2))
    _speed_rect = sp_box

    # Trail recording toggle
    global _trail_rect, _clear_trail_rect
    trail_lbl = "轨迹:开" if record_trail else "轨迹:关"
    trail_bg = (24, 120, 110) if record_trail else BTN_NORMAL
    _trail_rect = pygame.Rect(sp_box.right + 12, 5, 76, TOP_BAR_H - 10)
    draw_round_rect(surface, trail_bg, _trail_rect, 9,
                    border_color=CYAN_DIM if record_trail else BORDER)
    trail_disp = font.render(trail_lbl, True, TEXT_COLOR)
    surface.blit(trail_disp, trail_disp.get_rect(center=_trail_rect.center))
    # Clear trail button — right of the toggle
    _clear_trail_rect = pygame.Rect(_trail_rect.right + 6, 5, 56, TOP_BAR_H - 10)
    clr_hover = _clear_trail_rect.collidepoint(pygame.mouse.get_pos())
    clr_bg = BTN_HOVER if clr_hover else BTN_NORMAL
    draw_round_rect(surface, clr_bg, _clear_trail_rect, 9, border_color=BORDER)
    clr_disp = font.render("清除", True, TEXT_COLOR)
    surface.blit(clr_disp, clr_disp.get_rect(center=_clear_trail_rect.center))

    # FPS info
    info_font = get_font(16, bold=True)
    fps_text = info_font.render(f"FPS:{fps:02d}  步数:{len(elements):04d}", True, (150, 140, 195))
    fps_x = SCREEN_W - fps_text.get_width() - 14
    surface.blit(fps_text, (fps_x, TOP_BAR_H // 2 - fps_text.get_height() // 2))

    # Undo button – just left of FPS
    global _undo_btn_rect
    undo_font = get_font(19, bold=True)
    undo_lbl = "恢复"
    undo_size = undo_font.render(undo_lbl, True, TEXT_COLOR)
    uw = undo_size.get_width() + 16
    _undo_btn_rect = pygame.Rect(fps_x - uw - 8, 5, uw, TOP_BAR_H - 10)
    undo_hover = _undo_btn_rect.collidepoint(pygame.mouse.get_pos())
    undo_bg = BTN_HOVER if undo_hover else BTN_NORMAL
    draw_round_rect(surface, undo_bg, _undo_btn_rect, 9, border_color=BORDER)
    surface.blit(undo_size, undo_size.get_rect(center=_undo_btn_rect.center))

    # ── Study mode: project name + "前一个" / "后一个" buttons ──────
    global _study_next_rect, _study_prev_rect
    if study_mode:
        btn_font = get_font(18, bold=True)
        # "后一个" button
        next_lbl = "后一个 ▶"
        next_size = btn_font.render(next_lbl, True, TEXT_COLOR)
        nw = next_size.get_width() + 20
        _study_next_rect = pygame.Rect(_undo_btn_rect.left - nw - 6, 5, nw, TOP_BAR_H - 10)
        next_hover = _study_next_rect.collidepoint(pygame.mouse.get_pos())
        next_bg = (24, 90, 120) if next_hover else (20, 60, 80)
        draw_glow(surface, _study_next_rect, CYAN, intensity=50, spread=5, radius=9)
        draw_round_rect(surface, next_bg, _study_next_rect, 9,
                        border_color=CYAN_DIM if next_hover else BORDER)
        surface.blit(next_size, next_size.get_rect(center=_study_next_rect.center))
        # "前一个" button – to the left of "后一个"
        prev_lbl = "◀ 前一个"
        prev_size = btn_font.render(prev_lbl, True, TEXT_COLOR)
        pw = prev_size.get_width() + 20
        _study_prev_rect = pygame.Rect(_study_next_rect.left - pw - 6, 5, pw, TOP_BAR_H - 10)
        prev_hover = _study_prev_rect.collidepoint(pygame.mouse.get_pos())
        prev_bg = (24, 90, 120) if prev_hover else (20, 60, 80)
        draw_glow(surface, _study_prev_rect, CYAN, intensity=50, spread=5, radius=9)
        draw_round_rect(surface, prev_bg, _study_prev_rect, 9,
                        border_color=CYAN_DIM if prev_hover else BORDER)
        surface.blit(prev_size, prev_size.get_rect(center=_study_prev_rect.center))
    else:
        _study_next_rect = None
        _study_prev_rect = None


def draw_left_toolbar(surface):
    """Draw the left-side component toolbar with category tabs."""
    # Background
    pygame.draw.rect(surface, BG_TOOLBAR, (0, TOP_BAR_H, TOOLBAR_W, SCREEN_H - TOP_BAR_H))
    pygame.draw.line(surface, BORDER, (TOOLBAR_W, TOP_BAR_H), (TOOLBAR_W, SCREEN_H))

    # ── Category tabs ───────────────────────────────────────────
    tab_h = 24
    font = get_font(16, bold=True)
    for i, cat in enumerate(categories):
        tr = cat_tab_rects[i]
        is_active = (cat == current_category)
        if is_active:
            bg = BTN_ACTIVE
        elif tr.collidepoint(pygame.mouse.get_pos()):
            bg = BTN_HOVER
        else:
            bg = BTN_NORMAL
        if is_active:
            draw_glow(surface, tr, CYAN, intensity=80, spread=7, radius=9)
        draw_round_rect(surface, bg, tr, 9,
                        border_color=CYAN if is_active else BORDER)
        txt = font.render(category_labels[cat], True,
                          CYAN_GLOW if is_active else TEXT_COLOR)
        surface.blit(txt, txt.get_rect(center=tr.center))

    # ── Current category tool buttons ───────────────────────────
    cat_tools = tools[current_category]
    font = get_font(16, bold=True)
    for i, tool in enumerate(cat_tools):
        rect = tool_rects[i]
        hover = rect.collidepoint(pygame.mouse.get_pos())
        active = mode == tool['mode']

        if active:
            color = BTN_ACTIVE
        elif hover:
            color = BTN_HOVER
        else:
            color = BTN_NORMAL

        if active:
            draw_glow(surface, rect, CYAN, intensity=95, spread=8, radius=BTN_RADIUS)
        draw_round_rect(surface, color, rect, BTN_RADIUS,
                        border_color=CYAN if active else BORDER)

        # Two-line label: icon on top, text below（字号随按钮高度自适应）
        icon_sz = max(16, min(26, int(rect.h * 0.50)))
        lbl_sz = max(12, min(16, int(rect.h * 0.33)))
        icon_font = get_font(icon_sz, bold=True)
        icon_col = CYAN_GLOW if active else TEXT_COLOR
        icon_text = icon_font.render(tool['icon'], True, icon_col)
        icon_rect = icon_text.get_rect(center=(rect.centerx, rect.top + int(rect.h * 0.34)))
        surface.blit(icon_text, icon_rect)

        label_font = get_font(lbl_sz, bold=True)
        label_text = label_font.render(tool['label'], True, TEXT_COLOR)
        label_rect = label_text.get_rect(center=(rect.centerx, rect.bottom - int(rect.h * 0.27)))
        surface.blit(label_text, label_rect)

    # ── Field-line toggles (bottom of left toolbar) ────────────────
    toggle_font = get_font(15, bold=True)
    toggle_start_y = SCREEN_H - 128
    for i, t in enumerate(field_toggles):
        tr = pygame.Rect(12, toggle_start_y + i * 36, TOOLBAR_W - 24, 30)
        is_on = globals()[t['key']]
        bg = (24, 90, 78) if is_on else BTN_NORMAL
        if is_on:
            draw_glow(surface, tr, t['color'], intensity=60, spread=6, radius=8)
        draw_round_rect(surface, bg, tr, 8, border_color=t['color'])

        txt = toggle_font.render(t['label'], True, t['color'])
        tr_txt = txt.get_rect(center=tr.center)
        surface.blit(txt, tr_txt)

    # ── Phase 7 toggles ──────────────────────────────────────────
    ty2 = toggle_start_y + len(field_toggles) * 36 + 6
    for i, t in enumerate(phase7_toggles):
        tr = pygame.Rect(12, ty2 + i * 36, TOOLBAR_W - 24, 30)
        is_on = globals()[t['key']]
        bg = (44, 36, 86) if is_on else BTN_NORMAL
        if is_on:
            draw_glow(surface, tr, t['color'], intensity=60, spread=6, radius=8)
        draw_round_rect(surface, bg, tr, 8, border_color=t['color'])
        txt = toggle_font.render(t['label'], True, t['color'])
        tr_txt = txt.get_rect(center=tr.center)
        surface.blit(txt, tr_txt)


def draw_study_title(surface):
    """Draw the study project name centered below the top bar in the canvas area."""
    if not study_mode or not study_project_name:
        return
    font = get_font(22, bold=True)
    name_display = f"【 {study_project_name} 】"
    name_surf = font.render(name_display, True, CYAN_GLOW)
    # Center horizontally in the canvas area (between toolbar right edge and screen right edge)
    canvas_center_x = TOOLBAR_W + (SCREEN_W - TOOLBAR_W) // 2
    y = TOP_BAR_H + 8  # just below the top bar
    # Draw with a subtle background card
    pad_x, pad_y = 20, 6
    card_rect = pygame.Rect(canvas_center_x - name_surf.get_width() // 2 - pad_x,
                            y, name_surf.get_width() + pad_x * 2,
                            name_surf.get_height() + pad_y * 2)
    draw_round_rect(surface, (20, 18, 36, 200), card_rect, 12, border_color=CYAN_DIM)
    # Thin glow under the card
    draw_glow(surface, card_rect, CYAN, intensity=30, spread=4, radius=12)
    surface.blit(name_surf, name_surf.get_rect(center=(canvas_center_x, card_rect.centery)))


def draw_mode_hint(surface):
    """Show a hint about the current mode or study project description."""
    # Study mode description (shown when no tool is active)
    if study_mode and mode == 'select':
        font = get_font(18)
        # Load description from current project data
        desc = ""
        if study_project_index < len(study_projects):
            try:
                with open(study_projects[study_project_index], 'r', encoding='utf-8') as _f:
                    _data = json.load(_f)
                desc = _data.get('description', '')
            except Exception:
                pass
        if desc:
            # Draw study description in a glass card below top bar
            text_surf = font.render(desc, True, (180, 200, 220))
            pad_x, pad_y = 14, 8
            card_w = text_surf.get_width() + pad_x * 2
            card_h = text_surf.get_height() + pad_y * 2
            card_x = TOOLBAR_W + 16
            card_y = TOP_BAR_H + 12
            card_rect = pygame.Rect(card_x, card_y, card_w, card_h)
            draw_round_rect(surface, CARD_BG, card_rect, 10, border_color=CYAN_DIM)
            surface.blit(text_surf, (card_x + pad_x, card_y + pad_y))
        return

    if mode == 'select':
        return
    font = get_font(22)
    label = {'add_charge_pos': '点击画布放置正电荷 (ESC 取消)',
             'add_charge_neg': '点击画布放置负电荷 (ESC 取消)',
             'add_wire': '点击添加节点，右键完成导线 (ESC 取消)',
             'add_magnet': '点击画布放置磁铁 (ESC 取消)',
             'add_horseshoe_magnet': '点击画布放置马蹄形磁铁 (ESC 取消)',
             'add_power': '点击画布放置电源 (ESC 取消)',
             'add_resistor': '点击画布放置电阻 (ESC 取消)',
             'add_capacitor': '点击画布放置电容 (ESC 取消)',
             'add_inductor': '点击画布放置电感 (ESC 取消)',
             'add_ammeter': '点击画布放置电流表 (ESC 取消)',
             'add_voltmeter': '点击画布放置电压表 (ESC 取消)',
             'add_solenoid': '点击画布放置螺线管 (ESC 取消)',
             'add_textbox': '点击画布放置文本框 (ESC 取消)',
             'add_metal_ball': '点击画布放置金属球 (ESC 取消)',
             'add_metal_shell': '点击画布放置球壳 (ESC 取消)',
             'add_metal_plate': '点击画布放置金属板 (ESC 取消)',
             'add_motion_charge': '点击画布放置自由电荷 (ESC 取消)',
             'add_rect_field': '点击画布放置矩形磁场 (ESC 取消)',
             'add_circ_field': '点击画布放置圆形磁场 (ESC 取消)',
             'add_rect_efield': '点击画布放置平行平面电场 (ESC 取消)'}
    text = font.render(label.get(mode, ''), True, ACCENT_GLOW)
    surface.blit(text, (TOOLBAR_W + 12, TOP_BAR_H + 12))


def draw_selected_info(surface):
    """Show info of the selected element in a bottom panel area."""
    if not selected or editing_element:
        return
    font = get_font(18)
    text = font.render(selected.get_info(), True, (180, 200, 220))
    y = SCREEN_H - 30
    surface.blit(text, (TOOLBAR_W + 12, y))


def draw_circuit_warnings(surface):
    """Draw circuit solver warnings/errors at bottom of canvas."""
    if current_category != 'circuit' or not circuit_errors:
        return
    font = get_font(16)
    y = SCREEN_H - 30
    for err in circuit_errors:
        text = font.render("⚠ " + err, True, (255, 200, 100))
        surface.blit(text, (TOOLBAR_W + 12, y))
        y -= 24


def draw_measurement(surface):
    """Draw field measurement readout below the rotation slider."""
    global measuring, measure_text
    if not measuring or not measure_text:
        return
    font = get_font(15)
    x = SCREEN_W - 180
    y = TOP_BAR_H + 18 + 14 + 24
    lines = measure_text.split('\n')
    box_h = 16 + len(lines) * 20
    box = pygame.Rect(x - 4, y - 2, 184, box_h)
    draw_round_rect(surface, CARD_BG, box, 10, border_color=CYAN_DIM)
    for i, line in enumerate(lines):
        text = font.render(line, True, (140, 230, 215))
        surface.blit(text, (x, y + i * 20))


def draw_global_panel(surface):
    """Draw the global settings panel on the right side of the window."""
    global global_panel_open, _gs_sliders, _gs_close_rect, _gs_fps_btns
    if not global_panel_open:
        return
    pw = GLOBAL_PANEL_W
    px = SCREEN_W - pw
    panel_rect = pygame.Rect(px, 0, pw, SCREEN_H)
    # Background — 玻璃卡片感，左缘紫色描边
    pygame.draw.rect(surface, CARD_BG, panel_rect)
    pygame.draw.line(surface, PURPLE_DIM, (panel_rect.left, 0),
                     (panel_rect.left, SCREEN_H), 2)
    # Title
    font = get_font(20)
    title = font.render("全局设置", True, TEXT_COLOR)
    surface.blit(title, (px + 12, 12))
    # Close button
    close_rect = pygame.Rect(panel_rect.right - 56, 8, 48, 24)
    _gs_close_rect = close_rect
    draw_round_rect(surface, BTN_NORMAL, close_rect, 7, border_color=BORDER)
    close_font = get_font(15)
    cx = close_font.render("关闭", True, TEXT_COLOR)
    surface.blit(cx, cx.get_rect(center=close_rect.center))

    # ── Slider helpers ──────────────────────────────────────────────
    font_sm = get_font(14)
    font_val = get_font(15)
    sliders = []
    y0 = 52
    slider_w = pw - 40
    track_h = 12
    handle_r = 8

    def _slider(label, y, val, vmin, vmax, vstep, fmt):
        """Draw a labeled slider track+handle, return slider info dict."""
        full_label = "%s（%s）" % (label, fmt % val)
        lsurf = font_sm.render(full_label, True, TEXT_COLOR)
        surface.blit(lsurf, (px + 12, y))
        track_y_off = 18
        # Track
        track_x = px + 12
        track_y = y + track_y_off
        track_rect = pygame.Rect(track_x, track_y, slider_w, track_h)
        # Detection area
        detect_rect = pygame.Rect(track_x, track_y - 4, slider_w, track_h + 8)
        # Fill (left portion)
        frac = (val - vmin) / (vmax - vmin) if vmax > vmin else 0.0
        fill_w = int(slider_w * frac)
        # Track base
        draw_round_rect(surface, (26, 24, 44), track_rect, track_h // 2, border_color=BORDER)
        # Fill (left portion)
        if fill_w > 0:
            fill_rect = pygame.Rect(track_x, track_y, fill_w, track_h)
            draw_round_rect(surface, PURPLE, fill_rect, track_h // 2)
        # Handle
        hx = track_x + int(slider_w * frac)
        hy = track_y + track_h // 2
        pygame.draw.circle(surface, PURPLE, (hx, hy), handle_r)
        pygame.draw.circle(surface, CYAN_GLOW, (hx, hy), handle_r - 3)
        return {
            'detect_rect': detect_rect,
            'track_x': track_x, 'track_w': slider_w,
            'vmin': vmin, 'vmax': vmax, 'vstep': vstep,
            'val': val, 'key': None,
        }

    # ── 1. Field density ──
    y = y0
    s = _slider("场线密度", y, settings['field_density'], 0.25, 3.0, 0.25, "%.2f")
    s['key'] = 'field_density'
    sliders.append(s)

    # ── 2. FPS ──
    y += 52
    fps_label = font_sm.render("帧率 (FPS)", True, TEXT_COLOR)
    surface.blit(fps_label, (px + 12, y))
    fps_y = y + 18
    fps_opts = [('30', 30), ('60', 60), ('120', 120), ('无限制', 0)]
    _gs_fps_btns = []
    bw = 48
    gap = 6
    total_w = len(fps_opts) * bw + (len(fps_opts) - 1) * gap
    fx = px + 12 + (slider_w + 40 - total_w) // 2
    for label, val in fps_opts:
        r = pygame.Rect(fx, fps_y, bw, 24)
        active = settings['fps_target'] == val
        col = PURPLE_DEEP if active else BTN_NORMAL
        if active:
            draw_glow(surface, r, CYAN, intensity=55, spread=5, radius=7)
        draw_round_rect(surface, col, r, 7, border_color=CYAN if active else BORDER)
        t = font_sm.render(label, True, CYAN_GLOW if active else TEXT_COLOR)
        surface.blit(t, (fx + (bw - t.get_width()) // 2, fps_y + 4))
        _gs_fps_btns.append(('fps', val, r))
        fx += bw + gap

    _gs_sliders = sliders


# ---------------------------------------------------------------------------
# Context menu
# ---------------------------------------------------------------------------

_CONTEXT_MENU_W = 110
_CONTEXT_MENU_ITEM_H = 28
_CONTEXT_MENU_PAD = 2

def open_context_menu(mouse_pos, target):
    global context_menu
    mx, my = mouse_pos
    items = [
        {'label': '调整参数', 'action': 'edit'},
        {'label': '复制',    'action': 'copy'},
        {'label': '删除',    'action': 'delete'},
    ]
    menu_h = len(items) * _CONTEXT_MENU_ITEM_H + _CONTEXT_MENU_PAD * 2
    # Clamp to screen
    mx = max(TOOLBAR_W + 4, min(mx, SCREEN_W - _CONTEXT_MENU_W - 4))
    my = max(TOP_BAR_H + 4, min(my, SCREEN_H - menu_h - 4))
    context_menu = {
        'pos': (mx, my),
        'rect': pygame.Rect(mx, my, _CONTEXT_MENU_W, menu_h),
        'target': target,
        'items': items,
    }


def close_context_menu():
    global context_menu, canvas_menu
    context_menu = None
    canvas_menu = None


def draw_context_menu(surface):
    cm = context_menu
    if not cm:
        return
    mx, my = cm['pos']
    w, h = cm['rect'].size
    pad = _CONTEXT_MENU_PAD
    item_h = _CONTEXT_MENU_ITEM_H

    # Background
    draw_round_rect(surface, CARD_BG, (mx, my, w, h), 10, border_color=PURPLE_DIM)

    font = get_font(15)
    for i, item in enumerate(cm['items']):
        r = pygame.Rect(mx + pad, my + pad + i * item_h, w - pad * 2, item_h)
        if r.collidepoint(pygame.mouse.get_pos()):
            draw_round_rect(surface, BTN_HOVER, r, 7)
        text = font.render(item['label'], True, TEXT_COLOR)
        tr = text.get_rect(midleft=(r.left + 8, r.centery))
        surface.blit(text, tr)


def open_canvas_menu(mouse_pos):
    """Open the right-click menu for empty canvas space."""
    global canvas_menu, context_menu, _clipboard
    context_menu = None
    mx, my = mouse_pos
    w = 110
    items = [
        {'label': '全局设计', 'action': 'global'},
        {'label': '测量关闭' if measuring else '测量', 'action': 'measure'},
    ]
    if _clipboard is not None:
        items.append({'label': '粘贴', 'action': 'paste'})
    item_h = _CONTEXT_MENU_ITEM_H
    pad = _CONTEXT_MENU_PAD
    menu_h = len(items) * item_h + pad * 2
    mx = max(TOOLBAR_W + 4, min(mx, SCREEN_W - w - 4))
    my = max(TOP_BAR_H + 4, min(my, SCREEN_H - menu_h - 4))
    canvas_menu = {
        'pos': (mx, my),
        'rect': pygame.Rect(mx, my, w, menu_h),
        'items': items,
        'world_pos': screen_to_world(*mouse_pos),
    }


def draw_canvas_menu(surface):
    cm = canvas_menu
    if not cm:
        return
    mx, my = cm['pos']
    w, h = cm['rect'].size
    pad = _CONTEXT_MENU_PAD
    item_h = _CONTEXT_MENU_ITEM_H

    draw_round_rect(surface, CARD_BG, (mx, my, w, h), 10, border_color=PURPLE_DIM)

    font = get_font(15)
    for i, item in enumerate(cm['items']):
        r = pygame.Rect(mx + pad, my + pad + i * item_h, w - pad * 2, item_h)
        if r.collidepoint(pygame.mouse.get_pos()):
            draw_round_rect(surface, BTN_HOVER, r, 7)
        text = font.render(item['label'], True, TEXT_COLOR)
        tr = text.get_rect(midleft=(r.left + 8, r.centery))
        surface.blit(text, tr)


# ---------------------------------------------------------------------------
# Edit panel
# ---------------------------------------------------------------------------

def close_edit_panel():
    global editing_element, _edit_buttons, selected
    if editing_element:
        editing_element.is_selected = False
    editing_element = None
    _edit_buttons = []
    selected = None


def draw_edit_panel(surface):
    global _edit_buttons, _edit_fields
    e = editing_element
    if not e:
        _edit_buttons = []
        _edit_fields = []
        return

    _edit_buttons = []
    _edit_fields = []
    font = get_font(16)
    row_h = 38
    margin_x = TOOLBAR_W + 14
    margin_right = 14
    max_x = SCREEN_W - margin_right
    gap = 8

    # Estimate rows needed: render info + params in virtual pass
    x_est = margin_x
    row_count = 1
    first_row_items = []

    def _est_input(label, w=55):
        nonlocal x_est, row_count
        lw = font.size(label)[0]
        need = lw + 4 + w + gap
        if x_est + need > max_x:
            row_count += 1
            x_est = margin_x
        x_est += need
        first_row_items.append(('input', label, w))

    def _est_btn(w=36):
        nonlocal x_est, row_count
        need = w + gap
        if x_est + need > max_x:
            row_count += 1
            x_est = margin_x
        x_est += need
        first_row_items.append(('btn', w))

    def _est_label(text):
        nonlocal x_est, row_count
        lw = font.size(text)[0]
        need = lw + gap
        if x_est + need > max_x:
            row_count += 1
            x_est = margin_x
        x_est += need
        first_row_items.append(('label', text))

    # Info text estimation
    info = e.get_info()
    info_w = font.size(info)[0]
    x_est = margin_x + info_w + 24

    # Estimate parameters based on element type
    if isinstance(e, Charge):
        _est_input("q (C) =", 85); _est_input("r =", 40)
    elif isinstance(e, MotionCharge):
        _est_input("q (C) =", 85); _est_input("m (kg) =", 70);
        _est_input("vx =", 55); _est_input("vy =", 55); _est_btn(36)
    elif isinstance(e, Magnet):
        _est_input("强度 =", 50); _est_input("角度 =", 55)
    elif isinstance(e, HorseshoeMagnet):
        _est_input("强度 =", 50); _est_input("角度 =", 55)
    elif isinstance(e, Wire):
        _est_input("x速度 =", 55)
        _est_input("y速度 =", 55)
        if e.auto_current:
            _est_label(f"I = {e.current:+.2f} A (自动)")
            _est_btn()
        else:
            _est_label("I ="); _est_input("", 55); _est_btn()
    elif isinstance(e, Power):
        _est_input(f"{e.ptype} =", 50); _est_btn(52)
        if e.mode == 'AC':
            _est_input("f =", 45)
    elif isinstance(e, Resistor):
        _est_input("R =", 55); _est_input("角度 =", 55)
    elif isinstance(e, Capacitor):
        _est_input("C =", 50); _est_input("角度 =", 55)
        _est_label(f"V={e.voltage:.2f}V")
    elif isinstance(e, Inductor):
        _est_input("L =", 50); _est_input("角度 =", 55)
    elif isinstance(e, Solenoid):
        _est_label(f"I={e.current:+.2f}A")
        _est_input("匝数 =", 50)
        _est_input("角度 =", 55)
    elif isinstance(e, TextBox):
        _est_label(f"{e.text[:12]}")
        _est_btn(70)
        _est_input("宽度 =", 45)
        _est_input("高度 =", 45)
        _est_input("字号 =", 35)
    elif isinstance(e, Ammeter):
        _est_label(f"I={e.display_value:.4f}A")
    elif isinstance(e, Voltmeter):
        _est_label(f"V={e.display_value:.2f}V")
    elif isinstance(e, MetalBall):
        _est_input("r =", 55)
    elif isinstance(e, MetalShell):
        _est_input("内径 =", 55); _est_input("壁厚 =", 55)
    elif isinstance(e, MetalPlate):
        _est_input("厚度 =", 55); _est_input("角度 =", 55)
    elif isinstance(e, RectField):
        _est_input("B (T) =", 55); _est_input("宽度 =", 55); _est_input("高度 =", 55); _est_input("方向 =", 40)
    elif isinstance(e, CircField):
        _est_input("B (T) =", 55); _est_input("半径 =", 55); _est_input("方向 =", 40)
    elif isinstance(e, RectEfield):
        _est_input("E (N/C) =", 55); _est_input("宽度 =", 55); _est_input("高度 =", 55); _est_input("方向 =", 40)

    # Build panel with correct height
    rows = max(row_count, 2)
    panel_h = 50 + (rows - 1) * row_h
    py = SCREEN_H - panel_h - 8
    panel_rect = (TOOLBAR_W, py, SCREEN_W - TOOLBAR_W, panel_h)
    pygame.draw.rect(surface, CARD_BG, panel_rect)
    pygame.draw.line(surface, PURPLE_DIM, (panel_rect[0], py), (panel_rect[0] + panel_rect[2], py), 2)

    x = margin_x
    current_row = 0

    def _row_y():
        return py + 10 + current_row * row_h

    def _check_wrap(need):
        nonlocal current_row, x
        if current_row == 0:
            if x + need > margin_x + info_w + 24 + 10:
                pass  # first row shares space with info
        if x + need > max_x:
            current_row += 1
            x = margin_x

    def _input(label, attr, fmt='.2f', w=55, min_val=None, max_val=None, also_initial=False):
        nonlocal x, current_row
        lw = font.size(label)[0]
        need = lw + 4 + w + gap
        _check_wrap(need)
        ry = _row_y()
        lbl = font.render(label, True, TEXT_COLOR)
        surface.blit(lbl, (x, ry + 4))
        x += lw + 4
        is_editing = (_active_input is not None and
                      _active_input['attr'] == attr and
                      _active_input['elem'] is e)
        box = pygame.Rect(x, ry, w, 28)
        if is_editing:
            display = _active_input['text'] + '|'
            bg = PURPLE_DEEP
        else:
            val = getattr(e, attr)
            display = f"{math.degrees(val):.0f}°" if attr == 'angle' else format(val, fmt)
            bg = BTN_NORMAL
        draw_round_rect(surface, bg, box, 7,
                        border_color=CYAN if is_editing else BORDER)
        dtxt = font.render(str(display), True, TEXT_COLOR)
        surface.blit(dtxt, (box.x + 5, box.centery - dtxt.get_height() // 2))
        if not is_editing:
            sv = math.degrees(getattr(e, attr)) if attr == 'angle' else getattr(e, attr)
            _edit_buttons.append(
                (box, lambda v=sv: _start_input(e, attr, v, min_val, max_val, also_initial)))
            _edit_fields.append((box, e, attr, min_val, max_val, attr == 'angle'))
        x = box.right + gap

    def _btn(label, cb, w=None):
        nonlocal x, current_row
        if w is None:
            w = max(28, font.size(label)[0] + 16)
        need = w + gap
        _check_wrap(need)
        ry = _row_y()
        br = pygame.Rect(x, ry, w, 28)
        draw_round_rect(surface, BTN_NORMAL, br, 7, border_color=PURPLE_DIM)
        t = font.render(label, True, (190, 175, 235))
        surface.blit(t, t.get_rect(center=br.center))
        _edit_buttons.append((br, cb))
        x = br.right + gap

    def _static_label(text):
        nonlocal x, current_row
        lw = font.size(text)[0]
        need = lw + gap
        _check_wrap(need)
        ry = _row_y()
        lbl = font.render(text, True, TEXT_COLOR)
        surface.blit(lbl, (x, ry + 4))
        x += lw + gap

    # ── Element info ──
    info_surf = font.render(info, True, (160, 195, 230))
    y_center = py + panel_h // 2
    # If only one row, center; otherwise align to first row
    info_y = py + 10 + 4 if row_count > 1 else y_center - info_surf.get_height() // 2
    surface.blit(info_surf, (margin_x, info_y))
    x = margin_x + info_w + 24

    if isinstance(e, Charge):
        _input("q (C) =", 'q', '.2e', 85)
        _input("r =", 'radius', '.0f', 40)

    elif isinstance(e, MotionCharge):
        _input("q (C) =", 'q', '.2e', 85)
        _input("m (kg) =", 'mass', '.2e', 70)
        _input("r =", 'radius', '.0f', 40)
        _input("vx =", 'vx', '.1f', 55)
        _input("vy =", 'vy', '.1f', 55)
        _btn("固定" if e.fixed else "可动", lambda: setattr(e, 'fixed', not e.fixed), 36)

    elif isinstance(e, Magnet):
        _input("强度 =", 'strength', '.1f', 50)
        _input("角度 =", 'angle', None, 55)

    elif isinstance(e, HorseshoeMagnet):
        _input("强度 =", 'strength', '.1f', 50)
        _input("角度 =", 'angle', None, 55)

    elif isinstance(e, Wire):
        _input("x速度 =", 'vx', '.1f', 55)
        _input("y速度 =", 'vy', '.1f', 55)
        if e.auto_current:
            lbl = font.render(f"I = {e.current:+.2f} A (自动)", True, TEXT_COLOR)
            surface.blit(lbl, (x, py + 11))
            x += lbl.get_width() + 8
            _btn("手动", lambda: (_save_undo_snapshot(), setattr(e, 'auto_current', False)))
        else:
            lbl = font.render("I =", True, TEXT_COLOR)
            surface.blit(lbl, (x, py + 11))
            x += lbl.get_width() + 4
            _input("", 'current', '.2f', 55)
            _btn("自动", lambda: (_save_undo_snapshot(), setattr(e, 'auto_current', True),
                                 field_system.mark_dirty(), solve_and_update()))

    elif isinstance(e, Power):
        _input(f"{e.ptype} =", 'value', '.1f', 50)
        _btn("→ 交流" if e.mode == 'DC' else "→ 直流",
             lambda: (_save_undo_snapshot(),
                      setattr(e, 'mode', 'AC' if e.mode == 'DC' else 'DC'),
                      field_system.mark_dirty()))
        if e.mode == 'AC':
            _input("f =", 'frequency', '.1f', 45)

    elif isinstance(e, Resistor):
        _input("R =", 'resistance', '.0f', 55)
        _input("角度 =", 'angle', None, 55)

    elif isinstance(e, Capacitor):
        _input("C =", 'capacitance', '.1f', 50)
        _input("角度 =", 'angle', None, 55)
        _static_label(f"V = {e.voltage:.2f} V")

    elif isinstance(e, Inductor):
        _input("L =", 'inductance', '.1f', 50)
        _input("角度 =", 'angle', None, 55)

    elif isinstance(e, Solenoid):
        _static_label(f"I = {e.current:+.2f} A")
        _input("长度 =", 'coil_length', '.0f', 45)
        _input("直径 =", 'diameter', '.0f', 45)
        _input("匝数 =", 'turns', '.0f', 50, min_val=1, max_val=200)
        _input("角度 =", 'angle', None, 55)
        _btn("绕向: 顺时针" if e.winding_clockwise else "绕向: 逆时针",
             lambda: (_save_undo_snapshot(),
                      setattr(e, 'winding_clockwise', not e.winding_clockwise),
                      field_system.mark_dirty()))

    elif isinstance(e, TextBox):
        _btn("编辑文字",
             lambda: (_save_undo_snapshot(),
                      _edit_text_content(e)))
        _input("宽度 =", 'box_width', '.0f', 45)
        _input("高度 =", 'box_height', '.0f', 45)
        _input("字号 =", 'font_size', '.0f', 35)

    elif isinstance(e, Ammeter):
        _static_label(f"I = {e.display_value:.4f} A")
    elif isinstance(e, Voltmeter):
        _static_label(f"V = {e.display_value:.2f} V")

    elif isinstance(e, MetalBall):
        _input("r =", 'r_outer', '.0f', 55)

    elif isinstance(e, MetalShell):
        _input("内径 =", 'inner_radius', '.0f', 55)
        _input("壁厚 =", 'thickness', '.0f', 55)

    elif isinstance(e, MetalPlate):
        _input("厚度 =", 'thickness', '.0f', 55)
        _input("角度 =", 'angle', None, 55)

    elif isinstance(e, RectField):
        _input("B (T) =", 'B_mag', '.0f', 55)
        _input("宽度 =", 'width', '.0f', 55)
        _input("高度 =", 'height', '.0f', 55)
        _btn("出纸面 ⊙" if e.direction > 0 else "入纸面 ⊗",
             lambda: (_save_undo_snapshot(),
                      setattr(e, 'direction', -e.direction),
                      field_system.mark_dirty()))
    elif isinstance(e, CircField):
        _input("B (T) =", 'B_mag', '.0f', 55)
        _input("半径 =", 'radius', '.0f', 55)
        _btn("出纸面 ⊙" if e.direction > 0 else "入纸面 ⊗",
             lambda: (_save_undo_snapshot(),
                      setattr(e, 'direction', -e.direction),
                      field_system.mark_dirty()))
    elif isinstance(e, RectEfield):
        _input("E (N/C) =", 'E_mag', '.0f', 55)
        _input("宽度 =", 'width', '.0f', 55)
        _input("高度 =", 'height', '.0f', 55)
        _input("角度 =", 'angle', None, 55)
        _btn("→ 向右" if e.direction > 0 else "← 向左",
             lambda: (_save_undo_snapshot(),
                      setattr(e, 'direction', -e.direction),
                      field_system.mark_dirty()))

    # Done button (right-aligned)
    done_x = SCREEN_W - 70
    done_br = pygame.Rect(done_x, py + 9, 56, 24)
    pygame.draw.rect(surface, BTN_ACTIVE, done_br)
    pygame.draw.rect(surface, BORDER, done_br, 1)
    done_t = font.render("完成", True, TEXT_COLOR)
    surface.blit(done_t, done_t.get_rect(center=done_br.center))
    _edit_buttons.append((done_br, lambda: (_confirm_input(), close_edit_panel())))


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def handle_mousedown(btn, pos):
    global mode, elements, selected, dragging, drag_start_mouse, drag_start_pos
    global context_menu, faraday_active, record_trail, current_category, editing_element, measuring, global_panel_open
    global _resize_target, _resize_handle, _resize_start_mouse, _resize_start_vals, _scrub_target

    # Confirm any pending text input on click
    _confirm_input()

    # === Global panel: click on canvas → close ===
    if global_panel_open and pos[0] < SCREEN_W - GLOBAL_PANEL_W:
        global_panel_open = False
        # don't return — let the click fall through to canvas handlers

    # === Context / Canvas menu click ===
    if context_menu or canvas_menu:
        is_context = context_menu is not None
        menu = context_menu or canvas_menu
        if menu['rect'].collidepoint(pos):
            local_y = pos[1] - (menu['pos'][1] + _CONTEXT_MENU_PAD)
            idx = local_y // _CONTEXT_MENU_ITEM_H
            if 0 <= idx < len(menu['items']):
                item = menu['items'][idx]
                close_context_menu()
                if is_context:
                    target = menu['target']
                    if item['action'] == 'delete':
                        _delete_element(target)
                    elif item['action'] == 'edit':
                        global editing_element
                        selected = target
                        target.is_selected = True
                        editing_element = target
                    elif item['action'] == 'copy':
                        global _clipboard
                        _clipboard = copy.deepcopy(target)
                else:  # canvas_menu
                    if item['action'] == 'measure':
                        measuring = not measuring
                        if measuring:
                            mx, my = pygame.mouse.get_pos()
                            _update_measurement((mx, my))
                    elif item['action'] == 'global':
                        global_panel_open = not global_panel_open
                    elif item['action'] == 'paste':
                        wx, wy = menu.get('world_pos', screen_to_world(*pos))
                        pasted = copy.deepcopy(_clipboard)
                        pasted.x = wx
                        pasted.y = wy
                        Element._id_counter += 1
                        pasted.id = Element._id_counter
                        elements.append(pasted)
                        field_system.mark_dirty()
                        solve_and_update()
            return
        else:
            close_context_menu()

    # === Rotation slider: handled in main loop via mouse.get_pressed() ===

    # === Edit panel click ===
    if editing_element:
        for rect, cb in _edit_buttons:
            if rect.collidepoint(pos):
                _confirm_input()
                cb()
                return
        # Click elsewhere → close edit panel
        _confirm_input()
        close_edit_panel()
        # Continue to handle the click for selection etc.

    # === Global panel buttons ===
    if global_panel_open and btn == 1:
        if _gs_close_rect and _gs_close_rect.collidepoint(pos):
            global_panel_open = False
            return
        for _, val, r in _gs_fps_btns:
            if r.collidepoint(pos):
                settings['fps_target'] = val
                return
        # Click in global panel area but not on a button → ignore
        if pos[0] > SCREEN_W - GLOBAL_PANEL_W:
            return

    # === Top bar clicks ===
    if pos[1] < TOP_BAR_H:
        # Study mode "后一个" / "前一个" buttons (renders above toolbar buttons)
        if study_mode and _study_next_rect and _study_next_rect.collidepoint(pos):
            handle_top_action('study_next')
            return
        if study_mode and _study_prev_rect and _study_prev_rect.collidepoint(pos):
            handle_top_action('study_prev')
            return
        for i, btn_def in enumerate(top_buttons):
            if top_btn_rects[i].collidepoint(pos):
                handle_top_action(btn_def['action'])
                return
        # Speed control click
        if _speed_rect and _speed_rect.collidepoint(pos):
            _start_input(None, 'sim_speed', f"{sim_speed:.2f}", 0.1, 100.0)
            return
        # Trail toggle click
        if _trail_rect and _trail_rect.collidepoint(pos):
            global record_trail
            record_trail = not record_trail
            return
        # Clear trail button click
        if _clear_trail_rect and _clear_trail_rect.collidepoint(pos):
            for ce in elements:
                if isinstance(ce, MotionCharge):
                    ce.trail.clear()
            return
        # Undo button click (right side of top bar)
        if _undo_btn_rect and _undo_btn_rect.collidepoint(pos):
            _do_undo()
            return
        return

    # === Toolbar clicks ===
    if pos[0] < TOOLBAR_W:
        # Category tabs
        global current_category
        for i, cat in enumerate(categories):
            if cat_tab_rects and i < len(cat_tab_rects) and cat_tab_rects[i].collidepoint(pos):
                if cat != current_category:
                    current_category = cat
                    wire_points.clear()
                    mode = 'select'
                    selected = None
                    if editing_element:
                        editing_element.is_selected = False
                        editing_element = None
                        _edit_buttons.clear()
                    tool_rects.clear()
                    tool_rects.extend(get_tool_rects())
                    # Reset transient circuit state on category switch
                    global cap_voltages, ind_currents, sim_time
                    cap_voltages = {}
                    ind_currents = {}
                    sim_time = 0.0
                    field_system.mark_dirty()
                return
        # Tool buttons
        cat_tools = tools[current_category]
        for i, tool in enumerate(cat_tools):
            if tool_rects[i].collidepoint(pos):
                if mode != tool['mode']:
                    wire_points.clear()
                if mode == tool['mode']:
                    mode = 'select'
                else:
                    mode = tool['mode']
                return
        # Toggle buttons (bottom of left toolbar)
        toggle_start_y = SCREEN_H - 128
        for i, t in enumerate(field_toggles):
            tr = pygame.Rect(12, toggle_start_y + i * 36, TOOLBAR_W - 24, 30)
            if tr.collidepoint(pos):
                globals()[t['key']] = not globals()[t['key']]
                return
        # Phase 7 toggles
        ty1 = toggle_start_y + len(field_toggles) * 36 + 6
        for i, t in enumerate(phase7_toggles):
            tr = pygame.Rect(12, ty1 + i * 36, TOOLBAR_W - 24, 30)
            if tr.collidepoint(pos):
                globals()[t['key']] = not globals()[t['key']]
                return
        # Click on empty toolbar space → deselect
        if mode != 'select':
            mode = 'select'
            wire_points.clear()
        if selected:
            selected.is_selected = False
            selected = None
        return

    # === Canvas area ===
    if btn == 1:  # Left click
        # Double-click on rotation slider handle → reset angle to 0°
        if _rotation_slider_rect and _rotation_track_rect:
            global _slider_last_click, _skip_slider_poll, last_click_time
            frac = (camera['angle'] + math.pi) / (2 * math.pi)
            hx = _rotation_track_rect.x + int(frac * _rotation_track_rect.w)
            hy = _rotation_track_rect.centery
            if math.hypot(pos[0] - hx, pos[1] - hy) < 14:
                now = pygame.time.get_ticks()
                if now - _slider_last_click < DOUBLE_CLICK_MS:
                    camera['angle'] = 0.0
                    _slider_last_click = 0
                    _skip_slider_poll = True
                    # Move cursor to center of track so polling keeps angle at 0
                    cx = _rotation_track_rect.x + _rotation_track_rect.w // 2
                    cy = _rotation_track_rect.centery
                    pygame.mouse.set_pos(cx, cy)
                    return
                _slider_last_click = now
        # Close canvas menu on any left-click in canvas area
        if canvas_menu:
            close_context_menu()
        if mode == 'add_wire':
            wx, wy = screen_to_world(pos[0], pos[1])
            wx, wy = snap_to_terminal(wx, wy, elements, wire_points)
            if wire_points:
                lx, ly = wire_points[-1]
                wx, wy = ortho_snap(lx, ly, wx, wy)
            wire_points.append((wx, wy))
            return

        if mode != 'select':
            wx, wy = screen_to_world(pos[0], pos[1])
            _place_element(wx, wy)
            mode = 'select'
            return

        # Try to select element
        elem = _get_element_at(pos)
        if elem:
            # Check if clicking on a Power switch button
            if isinstance(elem, Power) and elem.is_switch_click(pos, camera, (SCREEN_W, SCREEN_H)):
                _save_undo_snapshot()
                elem.toggle_switch()
                solve_and_update()
                return
            selected = elem
            elem.is_selected = True
            _save_undo_snapshot()
            dragging = True
            drag_start_mouse = pos
            drag_start_pos = (elem.x, elem.y)
            # Also set editing target if panel is open
            if editing_element:
                editing_element = elem
        else:
            if selected:
                selected.is_selected = False
                selected = None
            # Left-drag on empty canvas — no panning (camera locked to center)
            pass

    elif btn == 2:  # Middle click — no panning (camera locked to center)
        pass

    elif btn == 3:  # Right click
        if mode == 'add_wire':
            # Right-click — finish wire
            if len(wire_points) >= 2:
                _save_undo_snapshot()
                elements.append(Wire(wire_points[:]))
                field_system.mark_dirty()
                solve_and_update()
            wire_points.clear()
            mode = 'select'
            return
        # Close canvas menu on right-click elsewhere (reopens below if on empty space)
        if canvas_menu:
            if canvas_menu['rect'].collidepoint(pos):
                return  # right-click on menu does nothing; use left-click to select
            else:
                close_context_menu()
        elem = _get_element_at(pos)
        if elem:
            # Check for edge resize (RectField / CircField)
            handle = None
            if hasattr(elem, 'check_edge'):
                handle = elem.check_edge(pos, camera, (SCREEN_W, SCREEN_H))
            if handle:
                _resize_target = elem
                _resize_handle = handle
                _resize_start_mouse = pos
                if hasattr(elem, 'width'):
                    _resize_start_vals = (elem.width, elem.height)
                elif hasattr(elem, 'radius'):
                    _resize_start_vals = (elem.radius,)
            else:
                open_context_menu(pos, elem)
        else:
            open_canvas_menu(pos)


def handle_mousemotion(pos, rel):
    global dragging, drag_start_mouse, measure_text, measuring
    global _resize_target, _resize_start_mouse, _scrub_target

    # Drag scrub: click an input field then drag to adjust
    if _scrub_target and pygame.mouse.get_pressed()[0]:
        st = _scrub_target
        dx = pos[0] - st['start_x']
        if st['is_angle']:
            start_deg = math.degrees(st['start_val'])
            v = start_deg + dx * 0.2
            if st['min_val'] is not None:
                v = max(st['min_val'], v)
            if st['max_val'] is not None:
                v = min(st['max_val'], v)
            v = math.radians(v)
        else:
            scale = 0.005 * abs(st['start_val'] or 1)
            v = st['start_val'] + dx * scale
            if st['min_val'] is not None:
                v = max(st['min_val'], v)
            if st['max_val'] is not None:
                v = min(st['max_val'], v)
        setattr(st['elem'], st['attr'], v)
        field_system.mark_dirty()
        return

    # Clicked on input → drag → switch to scrub
    if _active_input and pygame.mouse.get_pressed()[0]:
        dx, dy = rel
        if abs(dx) > 3 or abs(dy) > 3:
            ai = _active_input
            _confirm_input()
            _scrub_target = {
                'elem': ai['elem'], 'attr': ai['attr'],
                'start_x': pos[0] - dx,
                'start_val': getattr(ai['elem'], ai['attr']),
                'min_val': ai.get('min_val'), 'max_val': ai.get('max_val'),
                'is_angle': ai['attr'] == 'angle',
            }
            return

    if measuring:
        _update_measurement(pos)

    # Panning removed — camera is locked to center

    # Right-click resize drag (RectField / CircField)
    if _resize_target and _resize_start_mouse:
        _do_resize_drag(pos)
        return

    if dragging and selected and drag_start_mouse:
        dx = pos[0] - drag_start_mouse[0]
        dy = pos[1] - drag_start_mouse[1]
        angle = camera.get('angle', 0.0)
        if angle != 0:
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            dx, dy = dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a
        target_x = drag_start_pos[0] + dx / camera['zoom']
        target_y = drag_start_pos[1] + dy / camera['zoom']
        selected.move_by(target_x - selected.x, target_y - selected.y)
        field_system.mark_dirty()
        solve_and_update()


def handle_mouseup(btn, pos):
    global dragging, _resize_target, _resize_handle, _resize_start_mouse, _resize_start_vals, _scrub_target

    if btn == 1:
        if _scrub_target:
            _scrub_target = None
        if dragging:
            field_system.mark_dirty()
            solve_and_update()
        dragging = False
        drag_start_mouse = None
        drag_start_pos = None
    elif btn == 3:
        if _resize_target:
            field_system.mark_dirty()
            solve_and_update()
        _resize_target = None
        _resize_handle = None
        _resize_start_mouse = None
        _resize_start_vals = None


def handle_scroll(y, pos):
    if global_panel_open and pos[0] > SCREEN_W - GLOBAL_PANEL_W:
        return
    if y > 0:
        zoom_at(pos, 1.1)
    else:
        zoom_at(pos, 1 / 1.1)


def handle_keydown(key):
    global mode, simulation_playing, _active_input, measuring, global_panel_open, selected
    global sim_time, cap_voltages, ind_currents
    # Text input keys
    if _active_input is not None:
        if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
            _confirm_input()
        elif key == pygame.K_ESCAPE:
            _active_input = None
        elif key == pygame.K_BACKSPACE:
            _active_input['text'] = _active_input['text'][:-1]
        return
    if key == pygame.K_SPACE:
        simulation_playing = not simulation_playing
        if simulation_playing:
            cap_voltages = {}
            ind_currents = {}
            sim_time = 0.0
            for e in elements:
                if isinstance(e, Capacitor):
                    e.voltage = 0.0
                if isinstance(e, (Ammeter, Voltmeter)):
                    e._rms_max = -1e30
                    e._rms_min = 1e30
        return
    if key == pygame.K_ESCAPE:
        if global_panel_open:
            global_panel_open = False
        elif context_menu or canvas_menu:
            close_context_menu()
        elif editing_element:
            close_edit_panel()
        elif mode == 'add_wire' and wire_points:
            wire_points.clear()
            mode = 'select'
        elif measuring:
            measuring = False
        elif mode != 'select':
            mode = 'select'
        elif selected:
            selected.is_selected = False
            selected = None


# ---------------------------------------------------------------------------
# Study mode helpers
# ---------------------------------------------------------------------------

def _save_study_file(path):
    """Save current elements to a study .txt file."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('# ELECTRO_MAGNETIC_SIMULATION_SAVEFILE_V1\n')
            f.write(f'# CATEGORY | {current_category}\n')
            f.write(f'# CAMERA | 0.0 | 0.0 | {camera["zoom"]}\n')
            f.write(f'# FARADAY | {int(faraday_active)}\n')
            for e in elements:
                if isinstance(e, Charge):
                    f.write(f'CHARGE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.q}\n')
                elif isinstance(e, Magnet):
                    f.write(f'MAGNET | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.strength} | {math.degrees(e.angle):.1f} | {e.length} | {e.height}\n')
                elif isinstance(e, HorseshoeMagnet):
                    f.write(f'HORSESHOE_MAGNET | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.strength} | {math.degrees(e.angle):.1f} | {e.gap} | {e.arm_length} | {e.thickness}\n')
                elif isinstance(e, Wire):
                    pts = ';'.join(f'{p[0]:.1f},{p[1]:.1f}' for p in e.points)
                    f.write(f'WIRE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.current} | {int(e.auto_current)} | {e.vx} | {e.vy} | {pts}\n')
                elif isinstance(e, Power):
                    f.write(f'POWER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.ptype} | {e.value} | {math.degrees(e.angle):.1f} | {e.mode} | {int(e.switched_on)} | {e.frequency}\n')
                elif isinstance(e, Resistor):
                    f.write(f'RESISTOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.resistance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Capacitor):
                    f.write(f'CAPACITOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.capacitance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Inductor):
                    f.write(f'INDUCTOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.inductance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Ammeter):
                    f.write(f'AMMETER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Solenoid):
                    f.write(f'SOLENOID | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.coil_length} | {e.coil_radius} | {e.turns} | {math.degrees(e.angle):.1f} | {int(e.winding_clockwise)}\n')
                elif isinstance(e, TextBox):
                    safe_text = e.text.replace('|', '｜').replace('\n', '¶')
                    f.write(f'TEXTBOX | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {safe_text} | {e.box_width} | {e.box_height} | {e.font_size}\n')
                elif isinstance(e, Voltmeter):
                    f.write(f'VOLTMETER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, MetalBall):
                    f.write(f'METAL_BALL | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.r_outer} | {e.r_inner}\n')
                elif isinstance(e, MetalShell):
                    f.write(f'METAL_SHELL | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.inner_radius} | {e.thickness}\n')
                elif isinstance(e, MetalPlate):
                    f.write(f'METAL_PLATE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.thickness} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, MotionCharge):
                    f.write(f'MOTION_CHARGE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.q} | {e.mass} | {e.vx} | {e.vy} | {int(e.fixed)}\n')
                elif isinstance(e, RectField):
                    f.write(f'RECT_FIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.width:.1f} | {e.height:.1f} | {e.B_mag} | {e.direction}\n')
                elif isinstance(e, CircField):
                    f.write(f'CIRC_FIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.radius:.1f} | {e.B_mag} | {e.direction}\n')
                elif isinstance(e, RectEfield):
                    f.write(f'RECT_EFIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.width:.1f} | {e.height:.1f} | {e.E_mag} | {e.direction}\n')
        print(f"Study saved to {path}")
    except Exception as ex:
        print(f"Save study file error: {ex}")


def _save_current_study():
    """Save current study project if in study mode."""
    if not study_mode or not study_projects or study_project_index >= len(study_projects):
        return
    path = study_projects[study_project_index]
    if path.endswith('.txt'):
        _save_study_file(path)


def load_study_project(index):
    """Load a study project by its index in the study_projects list."""
    global study_project_index, study_project_name, elements, current_category
    global mode, selected, editing_element, cap_voltages, ind_currents, sim_time
    global faraday_active, faraday_time, wire_points, simulation_playing
    global circuit_errors, _edit_buttons, context_menu, canvas_menu, measuring
    global _flux_history, _induced_display

    if index < 0 or index >= len(study_projects):
        return False

    _undo_stack.clear()
    _flux_history.clear()
    _induced_display.clear()

    path = study_projects[index]
    study_project_index = index

    if path.endswith('.txt'):
        # Parse .txt save file format
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as ex:
            print(f"Load study project error: {ex}")
            return False

        cat = 'electrostatic'
        new_elements = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                if line.startswith('# CATEGORY'):
                    parts = line.split('|')
                    if len(parts) >= 2:
                        cat = parts[1].strip()
                continue
            parts = [p.strip() for p in line.split('|')]
            if not parts:
                continue
            etype = parts[0]
            try:
                if etype == 'CHARGE' and len(parts) >= 6:
                    x, y = float(parts[2]), float(parts[3])
                    q = float(parts[5])
                    if abs(q) > 1e-3:
                        q *= 1e-6
                    c = Charge(x, y, q=q)
                    if len(parts) >= 5:
                        rgb = parts[4].split(',')
                        if len(rgb) == 3:
                            c.color = tuple(int(v) for v in rgb)
                    new_elements.append(c)
                elif etype == 'MAGNET' and len(parts) >= 8:
                    x, y = float(parts[2]), float(parts[3])
                    strength = float(parts[5])
                    angle = math.radians(float(parts[6]))
                    length = float(parts[7]) if len(parts) >= 8 else 100
                    height = float(parts[8]) if len(parts) >= 9 else 32
                    m = Magnet(x, y, strength=strength, angle=angle, length=length, height=height)
                    new_elements.append(m)
                elif etype == 'HORSESHOE_MAGNET' and len(parts) >= 8:
                    x, y = float(parts[2]), float(parts[3])
                    strength = float(parts[5])
                    angle = math.radians(float(parts[6]))
                    gap = float(parts[7]) if len(parts) >= 8 else 50
                    arm_length = float(parts[8]) if len(parts) >= 9 else 80
                    thickness = float(parts[9]) if len(parts) >= 10 else 20
                    hm = HorseshoeMagnet(x, y, strength=strength, angle=angle, gap=gap, arm_length=arm_length, thickness=thickness)
                    new_elements.append(hm)
                elif etype == 'WIRE' and len(parts) >= 7:
                    current = float(parts[5])
                    auto = True
                    vx = 0.0
                    vy = 0.0
                    if len(parts) >= 10:
                        # New format: has vx/vy
                        auto = bool(int(parts[6]))
                        vx = float(parts[7])
                        vy = float(parts[8])
                        pts_str = parts[9]
                    elif len(parts) >= 8:
                        auto = bool(int(parts[6]))
                        pts_str = parts[7]
                    else:
                        pts_str = parts[6]
                    points = []
                    for pair in pts_str.split(';'):
                        xy = pair.split(',')
                        if len(xy) == 2:
                            points.append((float(xy[0]), float(xy[1])))
                    if len(points) >= 2:
                        w = Wire(points, current=current)
                        w.auto_current = auto
                        w.vx = vx
                        w.vy = vy
                        new_elements.append(w)
                elif etype == 'POWER' and len(parts) >= 8:
                    x, y = float(parts[2]), float(parts[3])
                    ptype = parts[5]
                    value = float(parts[6])
                    angle = math.radians(float(parts[7]))
                    mode = parts[8] if len(parts) >= 9 else 'DC'
                    frequency = float(parts[10]) if len(parts) >= 11 else 50.0
                    p = Power(x, y, ptype=ptype, value=value, angle=angle, mode=mode, frequency=frequency)
                    p.switched_on = bool(int(parts[9])) if len(parts) >= 10 else True
                    new_elements.append(p)
                elif etype == 'RESISTOR' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    res = float(parts[5])
                    angle = math.radians(float(parts[6]))
                    new_elements.append(Resistor(x, y, resistance=res, angle=angle))
                elif etype == 'CAPACITOR' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    cap = float(parts[5])
                    angle = math.radians(float(parts[6]))
                    new_elements.append(Capacitor(x, y, capacitance=cap, angle=angle))
                elif etype == 'INDUCTOR' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    ind = float(parts[5])
                    angle = math.radians(float(parts[6]))
                    new_elements.append(Inductor(x, y, inductance=ind, angle=angle))
                elif etype == 'AMMETER' and len(parts) >= 6:
                    x, y = float(parts[2]), float(parts[3])
                    angle = math.radians(float(parts[5])) if len(parts) >= 6 else 0.0
                    new_elements.append(Ammeter(x, y, angle=angle))
                elif etype == 'SOLENOID' and len(parts) >= 9:
                    x, y = float(parts[2]), float(parts[3])
                    coil_length = float(parts[5])
                    coil_radius = float(parts[6])
                    turns = int(parts[7])
                    angle = math.radians(float(parts[8])) if len(parts) >= 9 else 0.0
                    s = Solenoid(x, y, coil_length=coil_length, coil_radius=coil_radius, turns=turns, angle=angle)
                    if len(parts) >= 10:
                        s.winding_clockwise = bool(int(parts[9]))
                    new_elements.append(s)
                elif etype == 'TEXTBOX' and len(parts) >= 8:
                    x, y = float(parts[2]), float(parts[3])
                    text = parts[5] if len(parts) >= 6 else '备注'
                    text = text.replace('¶', '\n').replace('｜', '|')
                    box_w = float(parts[6]) if len(parts) >= 7 else 160
                    box_h = float(parts[7]) if len(parts) >= 8 else 60
                    fs = int(float(parts[8])) if len(parts) >= 9 else 18
                    new_elements.append(TextBox(x, y, text=text, box_width=box_w, box_height=box_h, font_size=fs))
                elif etype == 'VOLTMETER' and len(parts) >= 6:
                    x, y = float(parts[2]), float(parts[3])
                    angle = math.radians(float(parts[5])) if len(parts) >= 6 else 0.0
                    new_elements.append(Voltmeter(x, y, angle=angle))
                elif etype == 'METAL_BALL' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    r_outer = float(parts[5])
                    r_inner = float(parts[6]) if len(parts) >= 7 else 0
                    new_elements.append(MetalBall(x, y, r_outer=r_outer, r_inner=r_inner))
                elif etype == 'METAL_SHELL' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    inner_radius = float(parts[5])
                    thickness = float(parts[6])
                    new_elements.append(MetalShell(x, y, inner_radius=inner_radius, thickness=thickness))
                elif etype == 'METAL_PLATE' and len(parts) >= 7:
                    x, y = float(parts[2]), float(parts[3])
                    if len(parts) >= 8 and parts[7] in ('0', '1'):
                        pw = float(parts[5])
                        ph = float(parts[6])
                        new_elements.append(MetalPlate(x, y, thickness=ph))
                    elif len(parts) >= 8:
                        new_elements.append(MetalPlate(x, y, thickness=float(parts[5]),
                                                       angle=math.radians(float(parts[6]))))
                    else:
                        new_elements.append(MetalPlate(x, y, thickness=float(parts[5]),
                                                       angle=math.radians(float(parts[6]))))
                elif etype == 'MOTION_CHARGE' and len(parts) >= 10:
                    x, y = float(parts[2]), float(parts[3])
                    q = float(parts[5])
                    mass = float(parts[6])
                    vx = float(parts[7])
                    vy = float(parts[8])
                    if abs(q) > 1e-3:
                        q *= 1e-6
                    if mass > 0.1:
                        mass *= 0.001
                    mc = MotionCharge(x, y, q=q, mass=mass, vx=vx, vy=vy)
                    if len(parts) >= 10:
                        mc.fixed = bool(int(parts[9]))
                    new_elements.append(mc)
                elif etype == 'RECT_FIELD' and len(parts) >= 9:
                    x, y = float(parts[2]), float(parts[3])
                    width = float(parts[5])
                    height = float(parts[6])
                    B_mag = float(parts[7])
                    raw_dir = parts[8].strip().lower()
                    if raw_dir in ('into', 'in'):
                        direction = -1
                    elif raw_dir in ('out', 'out of page'):
                        direction = 1
                    else:
                        direction = int(parts[8]) if len(parts) >= 9 else 1
                    new_elements.append(RectField(x, y, width=width, height=height, B_mag=B_mag, direction=direction))
                elif etype == 'CIRC_FIELD' and len(parts) >= 8:
                    x, y = float(parts[2]), float(parts[3])
                    radius = float(parts[5])
                    B_mag = float(parts[6])
                    direction = int(parts[7]) if len(parts) >= 8 else 1
                    new_elements.append(CircField(x, y, radius=radius, B_mag=B_mag, direction=direction))
                elif etype == 'RECT_EFIELD' and len(parts) >= 9:
                    x, y = float(parts[2]), float(parts[3])
                    width = float(parts[5])
                    height = float(parts[6])
                    E_mag = float(parts[7])
                    direction = int(parts[8]) if len(parts) >= 9 else 1
                    new_elements.append(RectEfield(x, y, width=width, height=height, E_mag=E_mag, direction=direction))
            except (ValueError, IndexError) as ex:
                print(f"Skipping bad line in study file: {line} — {ex}")

        # Derive name from filename (e.g. "1. 磁铁插入线圈.txt" → "磁铁插入线圈")
        base = os.path.splitext(os.path.basename(path))[0]
        name = base.split('.', 1)[-1].strip() if '.' in base else base
        study_project_name = name

        # Reset state and load elements directly
        simulation_playing = False
        faraday_active = False
        faraday_time = 0.0
        cap_voltages = {}
        ind_currents = {}
        sim_time = 0.0
        mode = 'select'
        selected = None
        editing_element = None
        context_menu = None
        canvas_menu = None
        measuring = False
        _edit_buttons.clear()
        wire_points.clear()
        circuit_errors.clear()

        current_category = cat
        elements[:] = new_elements
        camera['x'] = camera['y'] = 0.0
        camera['zoom'] = 1.0
        camera['angle'] = 0.0
        tool_rects.clear()
        tool_rects.extend(get_tool_rects())
        field_system.mark_dirty()
        solve_and_update()
        return True

    # .json path (existing logic)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as ex:
        print(f"Load study project error: {ex}")
        return False

    study_project_name = data.get('name', '未命名')

    # Reset all simulation state
    simulation_playing = False
    faraday_active = False
    faraday_time = 0.0
    cap_voltages = {}
    ind_currents = {}
    sim_time = 0.0
    mode = 'select'
    selected = None
    editing_element = None
    context_menu = None
    canvas_menu = None
    measuring = False
    _edit_buttons.clear()
    wire_points.clear()
    circuit_errors.clear()

    cat = data.get('category', 'electrostatic')
    current_category = cat
    elements[:] = _deserialize_elements(data.get('elements', []))

    # Reset camera
    camera['x'] = camera['y'] = 0.0
    camera['zoom'] = 1.0
    camera['angle'] = 0.0

    # Recalculate tool rects for the new category
    tool_rects.clear()
    tool_rects.extend(get_tool_rects())

    field_system.mark_dirty()
    solve_and_update()
    return True


def scan_study_projects():
    """Scan the study/ directory for numbered JSON/TXT project files."""
    global study_projects
    study_projects = []
    if not os.path.isdir(STUDY_DIR):
        return
    try:
        files = [f for f in os.listdir(STUDY_DIR)
                 if f[0].isdigit() and (f.endswith('.json') or f.endswith('.txt'))]
        files.sort(key=lambda x: int(x.split('.')[0]) if x[0].isdigit() else 999)
        study_projects = [os.path.join(STUDY_DIR, f) for f in files]
    except Exception as ex:
        print(f"Scan study projects error: {ex}")


def run_study_end_screen(screen):
    """Show end-of-study screen with '重新学习' and '退出学习' options."""
    w, h = screen.get_size()
    font_large = get_font(42, bold=True)
    font_btn = get_font(26, bold=True)
    font_sub = get_font(20)

    btn_w, btn_h, gap = 360, 80, 30
    total_h = 2 * btn_h + gap
    base_y = int(h * 0.48)

    clock_end = pygame.time.Clock()

    while True:
        mouse = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 'quit'
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return 'quit'
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                bx = (w - btn_w) // 2
                y1 = base_y
                r1 = pygame.Rect(bx, y1, btn_w, btn_h)
                y2 = y1 + btn_h + gap
                r2 = pygame.Rect(bx, y2, btn_w, btn_h)
                if r1.collidepoint(event.pos):
                    return 'restart'
                if r2.collidepoint(event.pos):
                    return 'home'

        screen.blit(get_ambient_bg(w, h), (0, 0))

        # Congratulations text
        title = font_large.render('全部项目学习完毕！', True, TEXT_COLOR)
        screen.blit(title, title.get_rect(center=(w // 2, int(h * 0.30))))

        sub = font_sub.render('你已经完成了所有学习项目，接下来要做什么？', True, (170, 172, 196))
        screen.blit(sub, sub.get_rect(center=(w // 2, int(h * 0.38))))

        # Button 1: 重新学习
        bx = (w - btn_w) // 2
        y1 = base_y
        r1 = pygame.Rect(bx, y1, btn_w, btn_h)
        h1 = r1.collidepoint(mouse)
        if h1:
            draw_glow(screen, r1, CYAN, intensity=120, spread=14, radius=BTN_RADIUS)
        draw_round_rect(screen, BTN_HOVER if h1 else BTN_NORMAL, r1, BTN_RADIUS,
                        border_color=CYAN if h1 else BORDER)
        t1 = font_btn.render('重新学习', True, CYAN_GLOW if h1 else TEXT_COLOR)
        screen.blit(t1, t1.get_rect(center=r1.center))

        # Button 2: 退出学习
        y2 = y1 + btn_h + gap
        r2 = pygame.Rect(bx, y2, btn_w, btn_h)
        h2 = r2.collidepoint(mouse)
        if h2:
            draw_glow(screen, r2, PURPLE, intensity=120, spread=14, radius=BTN_RADIUS)
        draw_round_rect(screen, BTN_HOVER if h2 else BTN_NORMAL, r2, BTN_RADIUS,
                        border_color=PURPLE if h2 else BORDER)
        t2 = font_btn.render('退出学习', True, PURPLE if h2 else TEXT_COLOR)
        screen.blit(t2, t2.get_rect(center=r2.center))

        foot = get_font(16).render('ESC 退出程序', True, (110, 112, 140))
        screen.blit(foot, foot.get_rect(center=(w // 2, h - 30)))

        pygame.display.flip()
        clock_end.tick(60)


def handle_top_action(action):
    global mode, elements, selected, simulation_playing, faraday_time, faraday_active
    global sim_time, cap_voltages, ind_currents, running, _exit_to_home, _flux_history
    if action == 'new':
        _save_undo_snapshot()
        simulation_playing = False
        faraday_active = False
        faraday_time = 0.0
        cap_voltages = {}
        ind_currents = {}
        _flux_history.clear()
        sim_time = 0.0
        elements.clear()
        selected = None
        camera['x'] = camera['y'] = 0.0
        camera['zoom'] = 1.0
        field_system.mark_dirty()
        solve_and_update()
    elif action == 'save':
        _save_file()
    elif action == 'open':
        _save_undo_snapshot()
        _open_file()
    elif action == 'play':
        if not simulation_playing:
            _save_preplay_snapshot()
            # Reset transient circuit state
            cap_voltages = {}
            ind_currents = {}
            _flux_history.clear()
            sim_time = 0.0
            for e in elements:
                if isinstance(e, Capacitor):
                    e.voltage = 0.0
                if isinstance(e, (Ammeter, Voltmeter)):
                    e._rms_max = -1e30
                    e._rms_min = 1e30
        simulation_playing = True
    elif action == 'pause':
        simulation_playing = False
    elif action == 'undo':
        _do_undo()
    elif action == 'revert':
        _do_revert()
    elif action == 'exit':
        if study_mode:
            _exit_to_home = True
        else:
            _exit_to_home = True
        running = False
    elif action == 'study_prev':
        if study_mode:
            prev_idx = study_project_index - 1
            if prev_idx >= 0:
                load_study_project(prev_idx)
    elif action == 'study_next':
        if study_mode:
            next_idx = study_project_index + 1
            if next_idx < len(study_projects):
                load_study_project(next_idx)
            else:
                # All projects done → show end screen
                result = run_study_end_screen(screen)
                if result == 'restart':
                    scan_study_projects()
                    if study_projects:
                        load_study_project(0)
                    else:
                        _exit_to_home = True
                        running = False
                elif result == 'home':
                    _exit_to_home = True
                    running = False
                else:  # quit
                    running = False


# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------

def _confirm_input():
    global _active_input
    if _active_input is None:
        return
    try:
        v = float(_active_input['text'])
        if _active_input.get('min_val') is not None:
            v = max(_active_input['min_val'], v)
        if _active_input.get('max_val') is not None:
            v = min(_active_input['max_val'], v)
        elem = _active_input['elem']
        attr = _active_input['attr']
        # Angle stored in radians, typed in degrees
        if attr == 'angle':
            v = math.radians(v)
        if elem is None:
            globals()[attr] = v
        else:
            old = getattr(elem, attr, None)
            if old != v:
                _save_undo_snapshot()
                setattr(elem, attr, v)
                field_system.mark_dirty()
                solve_and_update()
    except (ValueError, AttributeError):
        pass
    _active_input = None


def _start_input(elem, attr, text, min_val=None, max_val=None, also_initial=False):
    global _active_input
    _confirm_input()
    _active_input = {
        'elem': elem,
        'attr': attr,
        'text': str(text),
        'min_val': min_val,
        'max_val': max_val,
        'also_initial': also_initial,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _do_resize_drag(mouse_pos):
    """Handle right-click drag resize for RectField / CircField."""
    global _resize_start_vals
    target = _resize_target
    if not target or not _resize_start_mouse or not _resize_start_vals:
        return
    sw, sh = SCREEN_W, SCREEN_H
    zoom = camera['zoom']
    # Current mouse in world coords
    wx, wy = screen_to_world(mouse_pos[0], mouse_pos[1])
    # Starting mouse in world coords
    sx, sy = screen_to_world(_resize_start_mouse[0], _resize_start_mouse[1])
    dwx = wx - sx
    dwy = wy - sy

    if hasattr(target, 'width'):
        # RectField resize
        h = _resize_handle
        w0, h0 = _resize_start_vals
        min_s = 40  # minimum size
        if h == 'e':
            target.width = max(min_s, w0 + dwx)
        elif h == 'w':
            target.width = max(min_s, w0 - dwx)
        elif h == 's':
            target.height = max(min_s, h0 + dwy)
        elif h == 'n':
            target.height = max(min_s, h0 - dwy)
        elif h == 'ne':
            target.width = max(min_s, w0 + dwx)
            target.height = max(min_s, h0 - dwy)
        elif h == 'nw':
            target.width = max(min_s, w0 - dwx)
            target.height = max(min_s, h0 - dwy)
        elif h == 'se':
            target.width = max(min_s, w0 + dwx)
            target.height = max(min_s, h0 + dwy)
        elif h == 'sw':
            target.width = max(min_s, w0 - dwx)
            target.height = max(min_s, h0 + dwy)
    elif hasattr(target, 'radius'):
        # CircField resize
        r0 = _resize_start_vals[0]
        dr = math.hypot(wx - target.x, wy - target.y) - math.hypot(sx - target.x, sy - target.y)
        target.radius = max(20, r0 + dr)


def _place_element(wx, wy):
    _save_undo_snapshot()
    if mode == 'add_charge_pos':
        elements.append(Charge(wx, wy, q=1e-6))
    elif mode == 'add_charge_neg':
        elements.append(Charge(wx, wy, q=-1e-6))
    elif mode == 'add_magnet':
        elements.append(Magnet(wx, wy))
    elif mode == 'add_horseshoe_magnet':
        elements.append(HorseshoeMagnet(wx, wy))
    elif mode == 'add_power':
        elements.append(Power(wx, wy))
    elif mode == 'add_resistor':
        elements.append(Resistor(wx, wy))
    elif mode == 'add_capacitor':
        elements.append(Capacitor(wx, wy))
    elif mode == 'add_inductor':
        elements.append(Inductor(wx, wy))
    elif mode == 'add_ammeter':
        elements.append(Ammeter(wx, wy))
    elif mode == 'add_solenoid':
        elements.append(Solenoid(wx, wy))
    elif mode == 'add_voltmeter':
        elements.append(Voltmeter(wx, wy))
    elif mode == 'add_metal_ball':
        elements.append(MetalBall(wx, wy))
    elif mode == 'add_metal_shell':
        elements.append(MetalShell(wx, wy))
    elif mode == 'add_metal_plate':
        elements.append(MetalPlate(wx, wy))
    elif mode == 'add_motion_charge':
        elements.append(MotionCharge(wx, wy))
    elif mode == 'add_rect_field':
        elements.append(RectField(wx, wy))
    elif mode == 'add_circ_field':
        elements.append(CircField(wx, wy))
    elif mode == 'add_rect_efield':
        elements.append(RectEfield(wx, wy))
    elif mode == 'add_textbox':
        elements.append(TextBox(wx, wy))
    field_system.mark_dirty()
    solve_and_update()
    # Stay in same mode — user can keep placing


def _get_element_at(pos):
    # Priority 1: point-like elements (Charge, MotionCharge) — check first
    for e in reversed(elements):
        if isinstance(e, (Charge, MotionCharge)) and e.check_click(pos, camera, (SCREEN_W, SCREEN_H)):
            return e
    # Priority 2: area/line elements
    for e in reversed(elements):
        if not isinstance(e, (Charge, MotionCharge)) and e.check_click(pos, camera, (SCREEN_W, SCREEN_H)):
            return e
    return None


def _update_measurement(mouse_pos):
    """Compute E, V or B field at mouse position and update measure_text."""
    global measure_text
    mx, my = mouse_pos
    if mx < TOOLBAR_W or my < TOP_BAR_H:
        return
    wx, wy = screen_to_world(mx, my)
    if current_category == 'electrostatic':
        Ex, Ey = field_system.get_efield(wx, wy, elements)
        E = math.hypot(Ex, Ey)
        V = field_system.get_potential(wx, wy, elements)
        measure_text = f"E = {E:.1f} N/C\nV = {V:+.2f} V"
    else:
        Ex, Ey = field_system.get_efield(wx, wy, elements)
        E = math.hypot(Ex, Ey)

        # Check for solenoids with current → use Biot-Savart for accurate measurement
        solenoid_elems = [e for e in elements if isinstance(e, Solenoid) and abs(e.current) >= 1e-10]

        if solenoid_elems:
            # Compute B from non-solenoid sources
            non_sol_elems = [e for e in elements if not isinstance(e, Solenoid)]
            Bx, By = field_system._bfield(wx, wy, non_sol_elems)
            Bz = (field_system._wire_bfield_at(wx, wy, elements) +
                  field_system._bounded_bfield_bz(wx, wy, elements))
            # Add solenoid Biot-Savart contributions
            for e in solenoid_elems:
                bx, by, bz = FieldSystem._solenoid_bfield_biotsavart(e, wx, wy)
                Bx += bx
                By += by
                Bz += bz
            B_para = math.hypot(Bx, By)  # in-plane magnitude
            B_total = math.hypot(Bz, B_para)  # vector sum ⊥ + ∥
            measure_text = (f"E = {E:.1f} N/C\n"
                            f"B⊥ = {Bz:+.6f} T\n"
                            f"B∥ = {B_para:.6f} T\n"
                            f"B = {B_total:.6f} T")
        else:
            Bx, By, Bz = field_system.get_total_bfield(wx, wy, elements)
            measure_text = f"E = {E:.1f} N/C\nBz = {Bz:+.6f} T"


def _edit_text_content(elem):
    """Edit text via Notepad (reliable Chinese input on Windows)."""
    import subprocess
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                      delete=False, encoding='utf-8')
    _temp_files.add(tmp.name)
    tmp.write(elem.text)
    tmp.close()
    subprocess.run(['notepad.exe', tmp.name])
    with open(tmp.name, 'r', encoding='utf-8') as f:
        content = f.read()
    # Strip trailing newline added by Notepad save
    if content.endswith('\r\n'):
        content = content[:-2]
    elif content.endswith('\n'):
        content = content[:-1]
    elem.text = content
    try:
        os.unlink(tmp.name)
        _temp_files.discard(tmp.name)
    except Exception:
        pass
    field_system.mark_dirty()


def _delete_element(elem):
    global selected
    _save_undo_snapshot()
    if selected is elem:
        selected = None
    elem.is_selected = False
    elements.remove(elem)
    field_system.mark_dirty()
    solve_and_update()


def _save_file():
    root = tkinter.Tk()
    root.withdraw()
    path = tkinter.filedialog.asksaveasfilename(
        defaultextension='.txt',
        filetypes=[('Simulation files', '*.txt'), ('All files', '*.*')],
        title='保存仿真'
    )
    root.destroy()
    if not path:
        return
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('# ELECTRO_MAGNETIC_SIMULATION_SAVEFILE_V1\n')
            f.write(f'# CATEGORY | {current_category}\n')
            f.write(f'# CAMERA | 0.0 | 0.0 | {camera["zoom"]}\n')
            f.write(f'# FARADAY | {int(faraday_active)}\n')
            for e in elements:
                if isinstance(e, Charge):
                    f.write(f'CHARGE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.q}\n')
                elif isinstance(e, Magnet):
                    f.write(f'MAGNET | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.strength} | {math.degrees(e.angle):.1f} | {e.length} | {e.height}\n')
                elif isinstance(e, HorseshoeMagnet):
                    f.write(f'HORSESHOE_MAGNET | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.strength} | {math.degrees(e.angle):.1f} | {e.gap} | {e.arm_length} | {e.thickness}\n')
                elif isinstance(e, Wire):
                    pts = ';'.join(f'{p[0]:.1f},{p[1]:.1f}' for p in e.points)
                    f.write(f'WIRE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.current} | {int(e.auto_current)} | {e.vx} | {e.vy} | {pts}\n')
                elif isinstance(e, Power):
                    f.write(f'POWER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.ptype} | {e.value} | {math.degrees(e.angle):.1f} | {e.mode} | {int(e.switched_on)} | {e.frequency}\n')
                elif isinstance(e, Resistor):
                    f.write(f'RESISTOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.resistance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Capacitor):
                    f.write(f'CAPACITOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.capacitance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Inductor):
                    f.write(f'INDUCTOR | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.inductance} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Ammeter):
                    f.write(f'AMMETER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, Solenoid):
                    f.write(f'SOLENOID | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.coil_length} | {e.coil_radius} | {e.turns} | {math.degrees(e.angle):.1f} | {int(e.winding_clockwise)}\n')
                elif isinstance(e, TextBox):
                    safe_text = e.text.replace('|', '｜').replace('\n', '¶')
                    f.write(f'TEXTBOX | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {safe_text} | {e.box_width} | {e.box_height} | {e.font_size}\n')
                elif isinstance(e, Voltmeter):
                    f.write(f'VOLTMETER | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, MetalBall):
                    f.write(f'METAL_BALL | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.r_outer} | {e.r_inner}\n')
                elif isinstance(e, MetalShell):
                    f.write(f'METAL_SHELL | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.inner_radius} | {e.thickness}\n')
                elif isinstance(e, MetalPlate):
                    f.write(f'METAL_PLATE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.thickness} | {math.degrees(e.angle):.1f}\n')
                elif isinstance(e, MotionCharge):
                    f.write(f'MOTION_CHARGE | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.q} | {e.mass} | {e.vx} | {e.vy} | {int(e.fixed)}\n')
                elif isinstance(e, RectField):
                    f.write(f'RECT_FIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.width:.1f} | {e.height:.1f} | {e.B_mag} | {e.direction}\n')
                elif isinstance(e, CircField):
                    f.write(f'CIRC_FIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.radius:.1f} | {e.B_mag} | {e.direction}\n')
                elif isinstance(e, RectEfield):
                    f.write(f'RECT_EFIELD | {e.id} | {e.x:.1f} | {e.y:.1f} | {e.color[0]},{e.color[1]},{e.color[2]} | {e.width:.1f} | {e.height:.1f} | {e.E_mag} | {e.direction}\n')
        print(f"Saved to {path}")
    except Exception as ex:
        print(f"Save error: {ex}")


def _open_file():
    global mode, selected, elements, faraday_active, current_category
    root = tkinter.Tk()
    root.withdraw()
    path = tkinter.filedialog.askopenfilename(
        defaultextension='.txt',
        filetypes=[('Simulation files', '*.txt'), ('All files', '*.*')],
        title='打开仿真'
    )
    root.destroy()
    if not path:
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as ex:
        print(f"Open error: {ex}")
        return

    new_elements = []
    cat = 'electrostatic'  # default for backward compatibility
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            # Check for metadata lines
            if line.startswith('# CATEGORY'):
                parts = line.split('|')
                if len(parts) >= 2:
                    cat = parts[1].strip()
            elif line.startswith('# CAMERA'):
                parts = line.split('|')
                if len(parts) >= 4:
                    try:
                        # camera x,y locked to 0,0 — only restore zoom
                        camera['zoom'] = float(parts[3].strip())
                    except ValueError:
                        pass
            elif line.startswith('# FARADAY'):
                parts = line.split('|')
                try:
                    faraday_active = bool(int(parts[1].strip()))
                except (IndexError, ValueError):
                    pass
            continue
        parts = [p.strip() for p in line.split('|')]
        if not parts:
            continue
        etype = parts[0]
        try:
            if etype == 'CHARGE' and len(parts) >= 6:
                x, y = float(parts[2]), float(parts[3])
                q = float(parts[5])
                # Migrate old files (pre-V2, q ~ 1.0 in abstract units)
                if abs(q) > 1e-3:
                    q *= 1e-6
                    print(f"  Migrated old Charge q from {q/1e-6:.0f} → {q:.2e} C")
                c = Charge(x, y, q=q)
                if len(parts) >= 5:
                    rgb = parts[4].split(',')
                    if len(rgb) == 3:
                        c.color = tuple(int(v) for v in rgb)
                new_elements.append(c)
            elif etype == 'MAGNET' and len(parts) >= 8:
                x, y = float(parts[2]), float(parts[3])
                strength = float(parts[5])
                angle = math.radians(float(parts[6]))
                length = float(parts[7]) if len(parts) >= 8 else 100
                height = float(parts[8]) if len(parts) >= 9 else 32
                m = Magnet(x, y, strength=strength, angle=angle, length=length, height=height)
                new_elements.append(m)
            elif etype == 'HORSESHOE_MAGNET' and len(parts) >= 8:
                x, y = float(parts[2]), float(parts[3])
                strength = float(parts[5])
                angle = math.radians(float(parts[6]))
                gap = float(parts[7]) if len(parts) >= 8 else 50
                arm_length = float(parts[8]) if len(parts) >= 9 else 80
                thickness = float(parts[9]) if len(parts) >= 10 else 20
                hm = HorseshoeMagnet(x, y, strength=strength, angle=angle, gap=gap, arm_length=arm_length, thickness=thickness)
                new_elements.append(hm)
            elif etype == 'WIRE' and len(parts) >= 7:
                current = float(parts[5])
                if len(parts) >= 8:
                    auto = bool(int(parts[6]))
                    pts_str = parts[7]
                else:
                    auto = True   # legacy file
                    pts_str = parts[6]
                points = []
                for pair in pts_str.split(';'):
                    xy = pair.split(',')
                    if len(xy) == 2:
                        points.append((float(xy[0]), float(xy[1])))
                if len(points) >= 2:
                    w = Wire(points, current=current)
                    w.auto_current = auto
                    new_elements.append(w)
            elif etype == 'POWER' and len(parts) >= 8:
                x, y = float(parts[2]), float(parts[3])
                ptype = parts[5]
                value = float(parts[6])
                angle = math.radians(float(parts[7]))
                mode = parts[8] if len(parts) >= 9 else 'DC'
                frequency = float(parts[10]) if len(parts) >= 11 else 50.0
                p = Power(x, y, ptype=ptype, value=value, angle=angle, mode=mode, frequency=frequency)
                p.switched_on = bool(int(parts[9])) if len(parts) >= 10 else True
                new_elements.append(p)
            elif etype == 'RESISTOR' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                res = float(parts[5])
                angle = math.radians(float(parts[6]))
                new_elements.append(Resistor(x, y, resistance=res, angle=angle))
            elif etype == 'CAPACITOR' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                cap = float(parts[5])
                angle = math.radians(float(parts[6]))
                new_elements.append(Capacitor(x, y, capacitance=cap, angle=angle))
            elif etype == 'INDUCTOR' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                ind = float(parts[5])
                angle = math.radians(float(parts[6]))
                new_elements.append(Inductor(x, y, inductance=ind, angle=angle))
            elif etype == 'AMMETER' and len(parts) >= 6:
                x, y = float(parts[2]), float(parts[3])
                angle = math.radians(float(parts[5])) if len(parts) >= 6 else 0.0
                new_elements.append(Ammeter(x, y, angle=angle))
            elif etype == 'SOLENOID' and len(parts) >= 9:
                x, y = float(parts[2]), float(parts[3])
                coil_length = float(parts[5])
                coil_radius = float(parts[6])
                turns = int(parts[7])
                angle = math.radians(float(parts[8])) if len(parts) >= 9 else 0.0
                s = Solenoid(x, y, coil_length=coil_length, coil_radius=coil_radius, turns=turns, angle=angle)
                if len(parts) >= 10:
                    s.winding_clockwise = bool(int(parts[9]))
                new_elements.append(s)
            elif etype == 'TEXTBOX' and len(parts) >= 8:
                x, y = float(parts[2]), float(parts[3])
                text = parts[5] if len(parts) >= 6 else '备注'
                text = text.replace('¶', '\n').replace('｜', '|')
                box_w = float(parts[6]) if len(parts) >= 7 else 160
                box_h = float(parts[7]) if len(parts) >= 8 else 60
                fs = int(parts[8]) if len(parts) >= 9 else 18
                new_elements.append(TextBox(x, y, text=text, box_width=box_w, box_height=box_h, font_size=fs))
            elif etype == 'VOLTMETER' and len(parts) >= 6:
                x, y = float(parts[2]), float(parts[3])
                angle = math.radians(float(parts[5])) if len(parts) >= 6 else 0.0
                new_elements.append(Voltmeter(x, y, angle=angle))
            elif etype == 'METAL_BALL' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                r_outer = float(parts[5])
                r_inner = float(parts[6]) if len(parts) >= 7 else 0
                new_elements.append(MetalBall(x, y, r_outer=r_outer, r_inner=r_inner))
            elif etype == 'METAL_SHELL' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                inner_radius = float(parts[5])
                thickness = float(parts[6])
                new_elements.append(MetalShell(x, y, inner_radius=inner_radius, thickness=thickness))
            elif etype == 'METAL_PLATE' and len(parts) >= 7:
                x, y = float(parts[2]), float(parts[3])
                if len(parts) >= 8 and parts[7] in ('0', '1'):
                    # Old format (8 parts): plate_width | plate_height | is_infinite(0/1)
                    pw = float(parts[5])
                    ph = float(parts[6])
                    new_elements.append(MetalPlate(x, y, thickness=ph))
                elif len(parts) >= 8:
                    # V2 format (8 parts): thickness | angle_deg | draw_length
                    new_elements.append(MetalPlate(x, y, thickness=float(parts[5]),
                                                   angle=math.radians(float(parts[6]))))
                else:
                    # Current format (7 parts): thickness | angle_deg
                    new_elements.append(MetalPlate(x, y, thickness=float(parts[5]),
                                                   angle=math.radians(float(parts[6]))))
            elif etype == 'MOTION_CHARGE' and len(parts) >= 10:
                x, y = float(parts[2]), float(parts[3])
                q = float(parts[5])
                mass = float(parts[6])
                vx = float(parts[7])
                vy = float(parts[8])
                # Migrate old files (pre-V2)
                if abs(q) > 1e-3:
                    q *= 1e-6
                if mass > 0.1:
                    mass *= 0.001
                mc = MotionCharge(x, y, q=q, mass=mass, vx=vx, vy=vy)
                if len(parts) >= 10:
                    mc.fixed = bool(int(parts[9]))
                new_elements.append(mc)
            elif etype == 'RECT_FIELD' and len(parts) >= 9:
                x, y = float(parts[2]), float(parts[3])
                width = float(parts[5])
                height = float(parts[6])
                B_mag = float(parts[7])
                raw_dir = parts[8].strip().lower()
                if raw_dir in ('into', 'in'):
                    direction = -1
                elif raw_dir in ('out', 'out of page'):
                    direction = 1
                else:
                    direction = int(parts[8]) if len(parts) >= 9 else 1
                new_elements.append(RectField(x, y, width=width, height=height,
                                              B_mag=B_mag, direction=direction))
            elif etype == 'CIRC_FIELD' and len(parts) >= 8:
                x, y = float(parts[2]), float(parts[3])
                radius = float(parts[5])
                B_mag = float(parts[6])
                direction = int(parts[7]) if len(parts) >= 8 else 1
                new_elements.append(CircField(x, y, radius=radius, B_mag=B_mag, direction=direction))
            elif etype == 'RECT_EFIELD' and len(parts) >= 9:
                x, y = float(parts[2]), float(parts[3])
                width = float(parts[5])
                height = float(parts[6])
                E_mag = float(parts[7])
                direction = int(parts[8]) if len(parts) >= 9 else 1
                new_elements.append(RectEfield(x, y, width=width, height=height,
                                               E_mag=E_mag, direction=direction))
        except (ValueError, IndexError) as ex:
            print(f"Skipping bad line: {line} — {ex}")

    for e in elements:
        e.is_selected = False
    # Load elements into the shared list
    elements[:] = new_elements
    # Switch to that category
    global current_category, cap_voltages, ind_currents, sim_time
    cap_voltages = {}
    ind_currents = {}
    sim_time = 0.0
    if cat != current_category:
        current_category = cat
        tool_rects.clear()
        tool_rects.extend(get_tool_rects())
    selected = None
    field_system.mark_dirty()
    solve_and_update()
    print(f"Loaded {len(new_elements)} elements into {cat} category from {path}")


# ---------------------------------------------------------------------------
# Home screen（主页面 —— 霓虹玻璃风格,与编辑器一致）
# ---------------------------------------------------------------------------

def run_home_screen(screen):
    """显示主页面，返回用户选择:

    - 'free'  —— 进入自由模式（现有编辑器）
    - 'quit'  —— 关闭窗口

    学习模式本期为占位：点击仅在页内弹「开发中」提示，不退出本循环。
    """
    w, h = screen.get_size()

    # 两个入口按钮的描述（含副标题说明）
    options = [
        {'key': 'free',  'title': '自由模式', 'sub': '自由搭建电路与电磁场，随心实验',
         'icon': '✦', 'accent': CYAN_GLOW},
        {'key': 'learn', 'title': '学习模式', 'sub': '按项目循序学习电磁学知识',
         'icon': '✎', 'accent': PURPLE},
    ]

    BTN_W, BTN_H, GAP = 440, 104, 30

    def layout(w, h):
        """按当前尺寸计算两个按钮矩形（垂直居中排列）。"""
        total_h = len(options) * BTN_H + (len(options) - 1) * GAP
        top = int(h * 0.46)
        rects = []
        for i in range(len(options)):
            x = (w - BTN_W) // 2
            y = top + i * (BTN_H + GAP)
            rects.append(pygame.Rect(x, y, BTN_W, BTN_H))
        return rects

    toast_until = 0   # 「开发中」提示的失效时间戳(ms)，0=不显示
    # 退出按钮（右下角）
    quit_btn_w, quit_btn_h = 80, 36

    while True:
        now = pygame.time.get_ticks()
        mouse = pygame.mouse.get_pos()
        rects = layout(w, h)
        quit_rect = pygame.Rect(w - quit_btn_w - 16, h - quit_btn_h - 16, quit_btn_w, quit_btn_h)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return 'quit'
            elif event.type == pygame.VIDEORESIZE:
                w, h = event.w, event.h
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return 'quit'
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if quit_rect.collidepoint(event.pos):
                    return 'quit'
                for opt, r in zip(options, rects):
                    if r.collidepoint(event.pos):
                        if opt['key'] == 'free':
                            return 'free'
                        else:
                            return 'learn'

        # ── 绘制 ──
        screen.blit(get_ambient_bg(w, h), (0, 0))

        # 标题
        title_font = get_font(60, bold=True)
        title = '电磁学仿真演示程序'
        # 阴影 + 主体（克制的立体感）
        sh = title_font.render(title, True, (8, 8, 16))
        tx = title_font.render(title, True, TEXT_COLOR)
        title_rect = tx.get_rect(center=(w // 2, int(h * 0.24)))
        screen.blit(sh, sh.get_rect(center=(title_rect.centerx + 2, title_rect.centery + 2)))
        screen.blit(tx, title_rect)

        # 标题下青色分隔光条
        bar_w = title_rect.w + 40
        bar = pygame.Rect(0, 0, bar_w, 3)
        bar.center = (w // 2, title_rect.bottom + 18)
        draw_glow(screen, bar, CYAN, intensity=90, spread=8, radius=2)
        pygame.draw.rect(screen, CYAN_GLOW, bar, border_radius=2)

        # 副标题
        sub_font = get_font(22)
        subtitle = sub_font.render('Electromagnetics Simulation', True, PURPLE)
        screen.blit(subtitle, subtitle.get_rect(center=(w // 2, title_rect.bottom + 46)))

        # 按钮
        for opt, r in zip(options, rects):
            hover = r.collidepoint(mouse)
            if hover:
                draw_glow(screen, r, opt['accent'], intensity=120, spread=14,
                          radius=BTN_RADIUS)
            base = BTN_HOVER if hover else BTN_NORMAL
            border = opt['accent'] if hover else BORDER
            draw_round_rect(screen, base, r, radius=BTN_RADIUS,
                            border_color=border)
            draw_round_rect(screen, opt['accent'], r, radius=BTN_RADIUS,
                            width=2 if hover else 1, border_color=opt['accent'])

            # 图标圆牌（左侧）
            badge_r = 30
            bcx = r.x + 44
            bcy = r.centery
            pygame.draw.circle(screen, PURPLE_DEEP, (bcx, bcy), badge_r)
            pygame.draw.circle(screen, opt['accent'], (bcx, bcy), badge_r, 2)
            icon_font = get_font(34, bold=True)
            icon = icon_font.render(opt['icon'], True, opt['accent'])
            screen.blit(icon, icon.get_rect(center=(bcx, bcy)))

            # 标题 + 副标题（图标右侧，左对齐）
            text_x = bcx + badge_r + 20
            t_font = get_font(30, bold=True)
            t_col = CYAN_GLOW if hover else TEXT_COLOR
            t_surf = t_font.render(opt['title'], True, t_col)
            screen.blit(t_surf, (text_x, r.y + 26))
            s_font = get_font(17)
            s_surf = s_font.render(opt['sub'], True, (170, 172, 196))
            screen.blit(s_surf, (text_x, r.y + 62))

        # 「开发中」占位提示
        if toast_until and now < toast_until:
            tip_font = get_font(22, bold=True)
            tip = tip_font.render('学习模式开发中，敬请期待', True, CYAN_GLOW)
            tip_rect = tip.get_rect(center=(w // 2, int(h * 0.86)))
            pad = pygame.Rect(tip_rect.x - 22, tip_rect.y - 12,
                              tip_rect.w + 44, tip_rect.h + 24)
            draw_round_rect(screen, CARD_BG, pad, radius=12, border_color=CYAN_DIM)
            screen.blit(tip, tip_rect)
        elif toast_until and now >= toast_until:
            toast_until = 0

        # 退出按钮
        q_hover = quit_rect.collidepoint(mouse)
        if q_hover:
            draw_glow(screen, quit_rect, (200, 60, 60), intensity=80, spread=8, radius=BTN_RADIUS)
        q_base = (60, 30, 36) if q_hover else (40, 20, 26)
        q_border = (240, 100, 100) if q_hover else (160, 60, 60)
        draw_round_rect(screen, q_base, quit_rect, radius=BTN_RADIUS, border_color=q_border)
        q_font = get_font(18, bold=True)
        q_lbl = q_font.render('退出', True, (255, 200, 200) if q_hover else (220, 160, 160))
        screen.blit(q_lbl, q_lbl.get_rect(center=quit_rect.center))

        # 底部版权/提示
        foot_font = get_font(16)
        foot = foot_font.render('ESC 退出  ·  点击卡片选择模式', True, (110, 112, 140))
        screen.blit(foot, foot.get_rect(center=(w // 2, h - 30)))

        pygame.display.flip()
        clock.tick(60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global running, fps, faraday_time, SCREEN_W, SCREEN_H, screen, tool_rects, cat_tab_rects
    global study_mode, _exit_to_home

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE | pygame.SCALED)
    pygame.display.set_caption("电磁学仿真演示程序")

    # ── 外层循环：学习模式结束后可返回主页面 ──
    while True:
        study_mode = False
        _exit_to_home = False
        choice = run_home_screen(screen)
        if choice == 'quit':
            pygame.quit()
            sys.exit()

        SCREEN_W, SCREEN_H = screen.get_size()
        tool_rects.clear()
        tool_rects.extend(get_tool_rects())
        cat_tab_rects.clear()
        cat_tab_rects.extend(get_cat_tab_rects())

        if choice == 'learn':
            study_mode = True
            scan_study_projects()
            if study_projects:
                load_study_project(0)
            else:
                study_mode = False

        running = True
        pygame.key.start_text_input()
        _apply_settings()

        while running:
            clock.tick(settings['fps_target'])
            fps = int(clock.get_fps())

            # --- Events ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.VIDEORESIZE:
                    SCREEN_W, SCREEN_H = event.w, event.h
                    tool_rects.clear()
                    tool_rects.extend(get_tool_rects())
                    cat_tab_rects.clear()
                    cat_tab_rects.extend(get_cat_tab_rects())
                    field_system.mark_dirty()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    handle_mousedown(event.button, event.pos)

                elif event.type == pygame.MOUSEBUTTONUP:
                    handle_mouseup(event.button, event.pos)

                elif event.type == pygame.MOUSEMOTION:
                    handle_mousemotion(event.pos, event.rel)

                elif event.type == pygame.MOUSEWHEEL:
                    mx, my = pygame.mouse.get_pos()
                    if mx >= TOOLBAR_W and my >= TOP_BAR_H:
                        handle_scroll(event.y, (mx, my))

                elif event.type == pygame.KEYDOWN:
                    handle_keydown(event.key)

                elif event.type == pygame.TEXTINPUT:
                    if _active_input is not None:
                        _active_input['text'] += event.text

            # --- Physics update ---
            dt = 1.0 / 60

            if simulation_playing:
                global sim_time, cap_voltages, ind_currents
                sim_dt = dt * sim_speed
                # Wire particle animation (charge dots along the wire)
                for e in elements:
                    if isinstance(e, Wire):
                        e.update_particles(dt)
                # Auto-movement for wires with vx/vy set (respects sim_speed)
                for e2 in elements:
                    if isinstance(e2, Wire) and (e2.vx != 0.0 or e2.vy != 0.0):
                        e2.move_by(e2.vx * sim_dt, e2.vy * sim_dt)
                        field_system.mark_dirty()

            # ── Faraday induction (every frame — captures dragged wires + circuit currents) ──
            # Reset auto wire currents before induction (only during play, since
            # circuit solver runs after and restores correct values).
            if simulation_playing:
                for e in elements:
                    if isinstance(e, Wire) and e.auto_current:
                        e.current = 0.0
            loops = _find_wire_loops(elements)
            induced = _compute_induced_emfs(elements, loops, field_system, dt, faraday_time)
            _apply_loop_currents(induced, elements)

            # Update display info for induced EMF/current labels
            _induced_display.clear()
            for key, val in list(induced.items()):
                if isinstance(key, tuple) and key[0] == 'loop_current':
                    pts, I_ind, wire_elems = val
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    total_R = 0.0
                    for w in wire_elems:
                        if hasattr(w, 'resistance'):
                            total_R += w.resistance
                        else:
                            seg_len = 0.0
                            for i in range(len(w.points) - 1):
                                seg_len += math.hypot(w.points[i+1][0] - w.points[i][0],
                                                      w.points[i+1][1] - w.points[i][1])
                            total_R += 0.01 / max(1, len(w.points) - 1) * seg_len
                    emf = I_ind * total_R if total_R > 0 else 0.0
                    _induced_display.append((cx, cy, emf, I_ind, total_R))

            if simulation_playing:
                global sim_time, cap_voltages, ind_currents
                sim_dt = dt * sim_speed
                pure_ac, ac_freq = _is_pure_ac_circuit()
                induced_voltages = {e: v for e, v in induced.items()
                                    if isinstance(e, Solenoid)}
                if pure_ac:
                    currents, node_v, circuit_errors = solve_ac(elements, frequency=ac_freq)
                    sim_time += sim_dt
                    for e in elements:
                        if isinstance(e, Wire) and e.auto_current:
                            e.current = abs(currents.get(e, 0j))
                            e.is_ac = True
                        elif isinstance(e, ActiveElement):
                            e.current = abs(currents.get(e, 0j))
                    cv = _cap_voltages_from_nodes(node_v)
                    for e in elements:
                        if isinstance(e, Capacitor):
                            e.voltage = cv.get(e, 0.0)
                    _update_meters_phasor(currents, node_v)
                else:
                    n_sub = max(1, min(50, int(sim_dt / 0.002)))
                    sub_dt = sim_dt / n_sub

                    for _ in range(n_sub):
                        sim_time += sub_dt
                        currents, circuit_errors, cap_voltages, ind_currents = solve_circuit(
                            elements, dt=sub_dt, time=sim_time,
                            cap_voltages=cap_voltages, ind_currents=ind_currents,
                            induced_voltages=induced_voltages)
                        _update_meter_peaks(currents)
                    for e in elements:
                        if isinstance(e, Wire) and e.auto_current:
                            e.current = currents.get(e, 0.0)
                            e.is_ac = _has_ac_source()
                        elif isinstance(e, ActiveElement):
                            e.current = currents.get(e, 0.0)
                    for e in elements:
                        if isinstance(e, Capacitor):
                            e.voltage = cap_voltages.get(e, 0.0)
                    _update_meters(currents)
                field_system.mark_dirty()
                mcs = [e for e in elements if isinstance(e, MotionCharge)]
                for e in mcs:
                    e.update(field_system, elements, sim_dt)
                collided = MotionCharge.resolve_all_collisions(mcs, elements)
                if record_trail:
                    for e in mcs:
                        if e not in collided and not e.fixed:
                            e.trail.append((e.x, e.y))
                if faraday_active:
                    faraday_time += sim_dt
                    for e in elements:
                        if isinstance(e, (Magnet, HorseshoeMagnet)):
                            omega = 2 * math.pi * 1.5
                            if not hasattr(e, '_faraday_ox'):
                                e._faraday_ox = e.x
                            e.x = e._faraday_ox + 80.0 * math.sin(omega * faraday_time)

            # --- Rotation slider: direct polling ---
            if not global_panel_open and _rotation_slider_rect and pygame.mouse.get_pressed()[0]:
                global _skip_slider_poll
                if _skip_slider_poll:
                    _skip_slider_poll = False
                else:
                    mx, my = pygame.mouse.get_pos()
                    if _rotation_slider_rect.collidepoint((mx, my)):
                        _set_angle_from_mouse(mx)

            # --- Global panel sliders: direct polling ---
            if global_panel_open and pygame.mouse.get_pressed()[0]:
                mx, my = pygame.mouse.get_pos()
                for sl in _gs_sliders:
                    dr = sl['detect_rect']
                    if dr and dr.collidepoint((mx, my)):
                        frac = (mx - sl['track_x']) / sl['track_w']
                        frac = max(0.0, min(1.0, frac))
                        raw = sl['vmin'] + frac * (sl['vmax'] - sl['vmin'])
                        stepped = round(raw / sl['vstep']) * sl['vstep']
                        stepped = max(sl['vmin'], min(sl['vmax'], stepped))
                        if sl['key'] == 'field_density' and settings['field_density'] != stepped:
                            settings['field_density'] = stepped
                            _apply_settings()
                        break

            # --- Draw ---
            screen.blit(get_ambient_bg(SCREEN_W, SCREEN_H), (0, 0))
            _draw_scene(screen, screen, elements, field_system, camera, mode,
                        wire_points, faraday_active, faraday_time, dt,
                        show_efield, show_bfield)

            _draw_rotation_slider(screen)

            draw_top_bar(screen)
            draw_study_title(screen)
            draw_left_toolbar(screen)
            draw_mode_hint(screen)
            draw_edit_panel(screen)
            draw_selected_info(screen)
            draw_circuit_warnings(screen)
            draw_context_menu(screen)
            draw_canvas_menu(screen)
            draw_measurement(screen)
            draw_global_panel(screen)

            pygame.display.flip()

        _cleanup_temp_files()
        if _exit_to_home:
            elements.clear()
            selected = None
            editing_element = None
            field_system.mark_dirty()
        else:
            break

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
