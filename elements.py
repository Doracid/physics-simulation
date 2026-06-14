import pygame
import math

from physics import PX_PER_METER


# ---------------------------------------------------------------------------
# 统一字体 —— 优先宋体 (SimSun)，回退保证中文与符号覆盖
# ---------------------------------------------------------------------------
_FONT_FAMILY = 'simsun,nsimsun,microsoftyahei,simhei'
_elem_font_cache = {}

def get_element_font(size, bold=False):
    """返回缓存的宋体字体（带回退），供所有元素标签绘制使用。"""
    size = max(1, int(size))
    key = (size, bold)
    f = _elem_font_cache.get(key)
    if f is None:
        try:
            f = pygame.font.SysFont(_FONT_FAMILY, size, bold=bold)
        except Exception:
            f = pygame.font.SysFont(None, size)
        _elem_font_cache[key] = f
    return f


# 文本框玻璃卡片缓存：key=(w,h,radius) -> Surface（竖直渐变 + 顶部高光 + 圆角遮罩）
_textbox_card_cache = {}

def _textbox_card(w, h, radius, highlight_h=None):
    """生成与整体霓虹玻璃 UI 一致的圆角玻璃卡片底（深紫渐变 + 高光）。"""
    key = (w, h, radius, highlight_h)
    s = _textbox_card_cache.get(key)
    if s is not None:
        return s
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    top_c = (36, 33, 58, 236)   # 顶部稍亮的深紫
    bot_c = (20, 19, 34, 236)   # 底部更深
    for yy in range(h):
        t = yy / max(1, h - 1)
        col = tuple(int(top_c[k] + (bot_c[k] - top_c[k]) * t) for k in range(4))
        pygame.draw.line(s, col, (0, yy), (w, yy))
    # 顶部玻璃高光（半透明白色光泽），默认一行字高度
    gloss_h = highlight_h if highlight_h is not None else max(3, int(h * 0.4))
    gloss = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(gloss, (255, 255, 255, 26),
                     (2, 1, max(1, w - 4), gloss_h),
                     border_radius=radius)
    s.blit(gloss, (0, 0))
    # 圆角遮罩
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if len(_textbox_card_cache) > 256:
        _textbox_card_cache.clear()
    _textbox_card_cache[key] = s
    return s


# ---------------------------------------------------------------------------
# 静电学元件美化 —— 球体 / 金属环 / 高光 / 选中发光（统一视觉语言）
# ---------------------------------------------------------------------------
_sphere_cache = {}

def _render_sphere(r, base):
    """带竖直柔和明暗 + 底部环境光遮蔽 + 圆形遮罩的球体表面（缓存）。"""
    r = max(2, int(r))
    base = tuple(int(c) for c in base[:3])
    key = (r, base)
    s = _sphere_cache.get(key)
    if s is not None:
        return s
    size = r * 2
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    top = tuple(min(255, base[k] + 72) for k in range(3))
    bot = tuple(max(0, base[k] - 66) for k in range(3))
    for yy in range(size):
        t = yy / max(1, size - 1)
        te = t * t * (3 - 2 * t)          # smoothstep，明暗过渡更柔和
        col = tuple(int(top[k] + (bot[k] - top[k]) * te) for k in range(3))
        pygame.draw.line(s, col, (0, yy), (size, yy))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (r, r), r)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # 底部环境光遮蔽（增加体积感）
    ao = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(ao, (0, 0, 0, 60), (r, r + max(1, r // 4)), r)
    ao.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(ao, (0, 0))
    if len(_sphere_cache) > 256:
        _sphere_cache.clear()
    _sphere_cache[key] = s
    return s


_ring_cache = {}

def _render_metal_ring(outer, inner, transparent=True, base=(206, 209, 214)):
    """金属球壳 / 环：竖直金属渐变 + 内腔 + 内外缘描边（缓存）。"""
    outer = max(2, int(outer))
    inner = max(1, int(inner))
    if inner >= outer:
        inner = outer - 1
    base = tuple(int(c) for c in base[:3])
    key = (outer, inner, transparent, base)
    s = _ring_cache.get(key)
    if s is not None:
        return s
    size = outer * 2
    c = outer
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    top = tuple(min(255, base[k] + 70) for k in range(3))
    bot = tuple(max(0, base[k] - 64) for k in range(3))
    for yy in range(size):
        t = yy / max(1, size - 1)
        te = t * t * (3 - 2 * t)
        col = tuple(int(top[k] + (bot[k] - top[k]) * te) for k in range(3))
        pygame.draw.line(s, col, (0, yy), (size, yy))
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), outer)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if transparent:
        # 透明内腔（背后元素可透出）
        erase = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(erase, (0, 0, 0, 255), (c, c), inner)
        s.blit(erase, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    else:
        # 不透明深色内腔（带轻微径向渐变）
        for i in range(inner, 0, -1):
            g = int(14 + 12 * (1 - i / inner))
            pygame.draw.circle(s, (g, g + 2, g + 8), (c, c), i)
    # 内缘阴影（强调壁厚立体感）
    if inner > 3:
        pygame.draw.circle(s, (120, 123, 130), (c, c), inner + 1,
                           max(1, (outer - inner) // 6))
    # 内外描边
    pygame.draw.circle(s, (232, 234, 238), (c, c), outer, 2)
    pygame.draw.circle(s, (168, 171, 178), (c, c), inner, 2)
    if len(_ring_cache) > 256:
        _ring_cache.clear()
    _ring_cache[key] = s
    return s


def _blit_specular(surface, cx, cy, hr, peak=160):
    """在 (cx,cy) 画一团柔和白色高光。"""
    hr = max(1, int(hr))
    s = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
    for i in range(hr, 0, -1):
        a = int(peak * (1 - i / hr))
        pygame.draw.circle(s, (255, 255, 255, a), (hr, hr), i)
    surface.blit(s, (int(cx) - hr, int(cy) - hr))


_vgrad_cache = {}

def _render_vgrad_rounded(w, h, top, bot, radius, border=None, border_w=2):
    """竖直渐变(smoothstep) + 圆角遮罩的立体块（缓存）。

    top→bot 由上至下渐变，模拟横卧金属体的体积感；可选描边。
    用于条形磁铁本体、马蹄磁铁极面等需要金属/喷漆立体质感的部位。
    """
    w = max(2, int(w))
    h = max(2, int(h))
    top = tuple(int(c) for c in top[:3])
    bot = tuple(int(c) for c in bot[:3])
    radius = max(0, int(radius))
    bkey = tuple(border) if border is not None else None
    key = (w, h, top, bot, radius, bkey, border_w)
    s = _vgrad_cache.get(key)
    if s is not None:
        return s
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        t = yy / max(1, h - 1)
        te = t * t * (3 - 2 * t)            # smoothstep，明暗过渡更柔和
        col = tuple(int(top[k] + (bot[k] - top[k]) * te) for k in range(3))
        pygame.draw.line(s, col, (0, yy), (w, yy))
    # 圆角遮罩
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if border is not None:
        pygame.draw.rect(s, border, (0, 0, w, h), border_w, border_radius=radius)
    if len(_vgrad_cache) > 256:
        _vgrad_cache.clear()
    _vgrad_cache[key] = s
    return s


def _draw_selection_glow(surface, cx, cy, r):
    """主题青色选中发光环（与文本框 / 整体 UI 一致）。"""
    cx, cy, r = int(cx), int(cy), int(r)
    for i in range(4, 0, -1):
        gr = r + 3 + 3 * i
        g = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(g, (94, 234, 212, max(6, 30 // i)), (gr, gr), gr)
        surface.blit(g, (cx - gr, cy - gr))
    pygame.draw.circle(surface, (94, 234, 212), (cx, cy), r + 3, 2)


def _silhouette_glow(sprite, color, pad=5, alpha=80):
    """由精灵不透明轮廓生成一圈柔和的同色辉光（用于电路元件霓虹质感）。"""
    w, h = sprite.get_size()
    if w < 2 or h < 2:
        return None
    tint = pygame.Surface((w, h), pygame.SRCALPHA)
    tint.fill((color[0], color[1], color[2], 255))
    tint.blit(sprite, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    glow = pygame.transform.smoothscale(tint, (w + pad * 2, h + pad * 2))
    glow.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return glow


def _draw_selection_rect_glow(surface, rect):
    """主题青色矩形选中辉光（用于电路元件等矩形精灵）。"""
    cx, cy = rect.center
    for i in range(4, 0, -1):
        pad = 4 + 3 * i
        g = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
        pygame.draw.rect(g, (94, 234, 212, max(6, 26 // i)), g.get_rect(),
                         border_radius=10 + pad)
        surface.blit(g, g.get_rect(center=(cx, cy)).topleft)
    pygame.draw.rect(surface, (94, 234, 212), rect.inflate(6, 6), 2, border_radius=8)


def world_to_screen(wx, wy, camera, sw, sh):
    """Transform world → screen coordinates, including camera rotation."""
    cx, cy = camera['x'], camera['y']
    zoom = camera['zoom']
    dx = (wx - cx) * zoom
    dy = (wy - cy) * zoom
    angle = camera.get('angle', 0.0)
    if angle != 0.0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx, dy = dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a
    return int(dx + sw / 2), int(dy + sh / 2)


class Element:
    """Base class for all electromagnetic simulation elements."""

    _id_counter = 0

    def __init__(self, x, y, color):
        Element._id_counter += 1
        self.id = Element._id_counter
        self.x = float(x)
        self.y = float(y)
        self.color = tuple(color)
        self.is_selected = False

    def draw(self, surface, camera, screen_size):
        raise NotImplementedError

    def check_click(self, mouse_screen_pos, camera, screen_size):
        raise NotImplementedError

    def move_by(self, dx, dy):
        self.x += dx
        self.y += dy

    def get_info(self):
        return f"Element #{self.id}"


class Charge(Element):
    """A point charge — positive or negative."""

    def __init__(self, x, y, q=1e-6, radius=18):
        color = (255, 60, 60) if q > 0 else (60, 120, 255)
        super().__init__(x, y, color)
        self.q = q
        self.radius = radius

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        r = max(4, int(self.radius * zoom))
        ix, iy = int(sx), int(sy)
        c = (255, 74, 74) if self.q > 0 else (74, 132, 255)

        # --- 颜色外发光（正红 / 负蓝，霓虹能量感）---
        gr = int(r * 1.85) + 2
        glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        for i in range(5, 0, -1):
            rr = r + int((gr - r) * i / 5)
            pygame.draw.circle(glow, (*c, int(22 * (1 - i / 6))), (gr, gr), rr)
        surface.blit(glow, (ix - gr, iy - gr))

        # --- 投影 ---
        so = max(1, int(3 * zoom))
        shadow_surf = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
        for i in range(r, 0, -1):
            pygame.draw.circle(shadow_surf, (0, 0, 0, int(30 * (1 - i / r))),
                               (r + 3, r + 3), i)
        surface.blit(shadow_surf, (ix - r - 3 + so, iy - r - 3 + so))

        # --- 球体本体（柔和明暗 + 体积感）---
        surface.blit(_render_sphere(r, c), (ix - r, iy - r))

        # --- 高光（主 + 次）---
        _blit_specular(surface, ix - r // 3, iy - int(r * 0.42), max(2, r // 3), 170)
        _blit_specular(surface, ix - r // 2, iy - r // 2, max(1, r // 6), 130)

        # --- 描边 ---
        pygame.draw.circle(surface, (255, 255, 255), (ix, iy), r, max(1, r // 18))

        # --- 符号 ---
        font = get_element_font(max(14, r), bold=True)
        sign = "+" if self.q > 0 else "−"
        text = font.render(sign, True, (255, 255, 255))
        surface.blit(text, text.get_rect(center=(ix, iy)))

        # --- 选中发光（主题青色）---
        if self.is_selected:
            _draw_selection_glow(surface, ix, iy, r)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        r = max(3, int(self.radius * camera['zoom']))
        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy
        return dx * dx + dy * dy <= (r + 5) * (r + 5)

    def get_info(self):
        return f"Charge: q = {self.q*1e6:+.2f} µC"


_bar_magnet_cache = {}

def _build_bar_magnet_sprite(w, h, pad):
    """金属立体条形磁铁精灵（缓存）：渐变红 N / 蓝 S 极、顶部高光、投影、圆角描边。"""
    w = max(8, int(w))
    h = max(6, int(h))
    pad = max(1, int(pad))
    key = (w, h, pad)
    cached = _bar_magnet_cache.get(key)
    if cached is not None:
        return cached

    radius = max(2, min(h // 3, w // 2))
    half_w = w // 2
    SW, SH = w + pad * 2, h + pad * 2
    spr = pygame.Surface((SW, SH), pygame.SRCALPHA)
    ox, oy = pad, pad

    # ── 投影（多层柔和）──
    so = max(1, int(pad * 0.8))
    shadow = pygame.Surface((SW, SH), pygame.SRCALPHA)
    for k in range(3, 0, -1):
        pygame.draw.rect(shadow, (0, 0, 0, 26),
                         (ox - k + so, oy - k + so, w + 2 * k, h + 2 * k),
                         border_radius=radius + k)
    spr.blit(shadow, (0, 0))

    # ── 极体（红 N / 蓝 S，竖直渐变金属/喷漆质感）──
    red = _render_vgrad_rounded(w, h, (255, 120, 110), (138, 16, 20), radius)
    blu = _render_vgrad_rounded(w, h, (120, 150, 255), (20, 32, 150), radius)
    body = pygame.Surface((w, h), pygame.SRCALPHA)
    body.blit(red, (0, 0), pygame.Rect(0, 0, half_w, h))
    body.blit(blu, (half_w, 0), pygame.Rect(half_w, 0, w - half_w, h))

    # ── 顶部高光带（玻璃/金属反光）──
    gloss = pygame.Surface((w, h), pygame.SRCALPHA)
    gh = max(3, int(h * 0.42))
    inset = max(2, radius // 2)
    for yy in range(gh):
        t = yy / max(1, gh - 1)
        a = int(120 * (1 - t) ** 1.3)
        pygame.draw.line(gloss, (255, 255, 255, a), (inset, yy + 2), (w - inset, yy + 2))
    gmask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(gmask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
    gloss.blit(gmask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    body.blit(gloss, (0, 0))

    # ── 中缝（两极分界：暗线 + 一侧亮边）──
    seam_w = max(1, w // 90 + 1)
    pygame.draw.line(body, (20, 8, 10, 150), (half_w, 3), (half_w, h - 3), seam_w)
    pygame.draw.line(body, (255, 255, 255, 60), (half_w + seam_w, 4), (half_w + seam_w, h - 4), 1)

    # ── 描边（亮金属边）──
    pygame.draw.rect(body, (236, 238, 242), (0, 0, w, h), max(1, h // 16), border_radius=radius)

    # ── N / S 标签（带投影增强可读性）──
    label_font = get_element_font(max(10, int(h * 0.6)), bold=True)
    for txt, cxp in (("N", half_w // 2), ("S", half_w + (w - half_w) // 2)):
        shadow_t = label_font.render(txt, True, (0, 0, 0))
        fg_t = label_font.render(txt, True, (255, 255, 255))
        body.blit(shadow_t, shadow_t.get_rect(center=(cxp + 1, h // 2 + 1)))
        body.blit(fg_t, fg_t.get_rect(center=(cxp, h // 2)))

    spr.blit(body, (ox, oy))
    if len(_bar_magnet_cache) > 128:
        _bar_magnet_cache.clear()
    _bar_magnet_cache[key] = spr
    return spr


class Magnet(Element):
    """A bar magnet with N (red) and S (blue) poles."""

    def __init__(self, x, y, strength=1.0, angle=0.0, length=100, height=32):
        super().__init__(x, y, (180, 180, 180))
        self.strength = float(strength)
        self.angle = float(angle)  # radians
        self.length = float(length)
        self.height = float(height)
    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']

        w = max(20, int(self.length * zoom))
        h = max(10, int(self.height * zoom))
        pad = max(2, int(3 * zoom))

        sprite = _build_bar_magnet_sprite(w, h, pad)

        # Rotate and blit (compound with camera rotation)
        cam_angle = camera.get('angle', 0.0)
        total_angle = -math.degrees(self.angle + cam_angle)
        rotated = pygame.transform.rotate(sprite, total_angle)
        rect = rotated.get_rect(center=(int(sx), int(sy)))
        surface.blit(rotated, rect.topleft)

        # Selection（主题青色辉光，与电路元件统一）
        if self.is_selected:
            _draw_selection_rect_glow(surface, rect.inflate(-2 * pad, -2 * pad))

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(20, int(self.length * zoom))
        h = max(10, int(self.height * zoom))

        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy

        # Undo camera rotation to get world-space offset
        cam_angle = camera.get('angle', 0.0)
        if cam_angle != 0:
            cos_cam = math.cos(-cam_angle)
            sin_cam = math.sin(-cam_angle)
            dx, dy = dx * cos_cam - dy * sin_cam, dx * sin_cam + dy * cos_cam

        # Then undo magnet angle to get local-space offset
        cos_a = math.cos(-self.angle)
        sin_a = math.sin(-self.angle)
        lx = dx * cos_a - dy * sin_a
        ly = dx * sin_a + dy * cos_a

        return abs(lx) <= w / 2 and abs(ly) <= h / 2

    def get_info(self):
        return f"Magnet: strength={self.strength}, angle={math.degrees(self.angle):.0f}°"


class HorseshoeMagnet(Element):
    """A horseshoe (U-shaped) magnet with curved back and N (red) / S (blue) poles."""

    def __init__(self, x, y, strength=1.0, angle=0.0, gap=50, arm_length=80, thickness=20):
        super().__init__(x, y, (180, 180, 180))
        self.strength = float(strength)
        self.angle = float(angle)
        self.gap = float(gap)
        self.arm_length = float(arm_length)
        self.thickness = float(thickness)
        self._sprite_cache = None   # (key, sprite, w, h, pad) —— 避免每帧重建立体精灵
    def get_pole_positions(self):
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        hw = self.arm_length / 2
        hh = self.gap / 2
        t = self.thickness
        lx_n, ly_n = hw, -(hh + t / 2)
        nx = self.x + lx_n * cos_a - ly_n * sin_a
        ny = self.y + lx_n * sin_a + ly_n * cos_a
        lx_s, ly_s = hw, hh + t / 2
        sx = self.x + lx_s * cos_a - ly_s * sin_a
        sy = self.y + lx_s * sin_a + ly_s * cos_a
        return (nx, ny), (sx, sy)

    def _build_polygon(self):
        """Curved-back U-shape polygon in local coords.  Opens to the right (+x)."""
        hw = self.arm_length / 2
        hh = self.gap / 2
        t = self.thickness
        verts = []

        # top arm outer edge (rightward)
        verts.append((-hw, -(hh + t)))
        verts.append(( hw, -(hh + t)))
        # N tip (down)
        verts.append(( hw, -hh))
        # top arm inner edge (leftward to back)
        verts.append((-hw + t, -hh))

        # inner semicircle (top → bottom, bowing left)
        n_arc = 14
        for i in range(1, n_arc):
            a = -math.pi / 2 + math.pi * i / n_arc
            verts.append((-hw + t - hh * math.cos(a), hh * math.sin(a)))
        verts.append((-hw + t, hh))

        # bottom arm inner edge (rightward)
        verts.append(( hw,  hh))
        # S tip (down)
        verts.append(( hw,  hh + t))
        # bottom arm outer edge (leftward to back)
        verts.append((-hw,  hh + t))

        # outer semicircle (bottom → top, bowing left)
        for i in range(1, n_arc):
            a = math.pi / 2 - math.pi * i / n_arc
            verts.append((-hw - (hh + t) * math.cos(a), (hh + t) * math.sin(a)))
        verts.append((-hw, -(hh + t)))

        return verts

    @staticmethod
    def _point_in_polygon(px, py, poly):
        inside = False
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > py) != (yj > py)) and \
               px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    def _build_sprite(self, zoom):
        """构建带投影的立体马蹄磁铁精灵（按缩放/尺寸缓存）。返回 (sprite, w, h, pad)。"""
        poly = self._build_polygon()
        xs = [v[0] for v in poly]
        ys = [v[1] for v in poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        poly_cx = (min_x + max_x) / 2
        poly_cy = (min_y + max_y) / 2
        bw = max_x - min_x + 4
        bh = max_y - min_y + 4
        w = max(20, int(bw * zoom))
        h = max(20, int(bh * zoom))
        pad = max(3, int(4 * zoom))

        key = (w, h, pad, round(self.gap, 1),
               round(self.arm_length, 1), round(self.thickness, 1))
        if self._sprite_cache is not None and self._sprite_cache[0] == key:
            return self._sprite_cache[1], w, h, pad

        SW, SH = w + pad * 2, h + pad * 2
        sprite = pygame.Surface((SW, SH), pygame.SRCALPHA)
        ox, oy = pad, pad
        scx, scy = w / 2, h / 2

        def to_spr(lx, ly):
            return (int(ox + scx + (lx - poly_cx) * zoom),
                    int(oy + scy + (ly - poly_cy) * zoom))

        sp_verts = [to_spr(lx, ly) for lx, ly in poly]

        # ── 投影 ──
        so = max(2, int(3 * zoom))
        shadow = pygame.Surface((SW, SH), pygame.SRCALPHA)
        pygame.draw.polygon(shadow, (0, 0, 0, 70), [(x + so, y + so) for x, y in sp_verts])
        sprite.blit(shadow, (0, 0))

        # ── 金属本体：竖直渐变 + 多边形遮罩（横卧金属的体积明暗）──
        ys_v = [v[1] for v in sp_verts]
        gy0, gy1 = min(ys_v), max(ys_v)
        top_m, mid_m, bot_m = (198, 201, 207), (150, 153, 159), (74, 77, 84)
        grad = pygame.Surface((SW, SH), pygame.SRCALPHA)
        for yy in range(gy0, gy1 + 1):
            t = (yy - gy0) / max(1, gy1 - gy0)
            # 双段渐变：上半亮→中灰，下半中灰→暗，模拟圆柱金属反光
            if t < 0.5:
                u = t / 0.5
                ue = u * u * (3 - 2 * u)
                col = tuple(int(top_m[k] + (mid_m[k] - top_m[k]) * ue) for k in range(3))
            else:
                u = (t - 0.5) / 0.5
                ue = u * u * (3 - 2 * u)
                col = tuple(int(mid_m[k] + (bot_m[k] - mid_m[k]) * ue) for k in range(3))
            pygame.draw.line(grad, col, (0, yy), (SW, yy))
        pmask = pygame.Surface((SW, SH), pygame.SRCALPHA)
        pygame.draw.polygon(pmask, (255, 255, 255, 255), sp_verts)
        grad.blit(pmask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        sprite.blit(grad, (0, 0))

        # ── 两极极面（红 N / 蓝 S，竖直渐变 + 高光）──
        hw = self.arm_length / 2
        hh = self.gap / 2
        t = self.thickness

        def fill_pole(corners, ctop, cbot):
            pxs = [c[0] for c in corners]
            pys = [c[1] for c in corners]
            x0, y0 = min(pxs), min(pys)
            pw = max(2, max(pxs) - x0)
            ph = max(2, max(pys) - y0)
            sprite.blit(_render_vgrad_rounded(pw, ph, ctop, cbot, max(1, ph // 5)), (x0, y0))
            gloss = pygame.Surface((pw, ph), pygame.SRCALPHA)
            gh = max(2, int(ph * 0.42))
            for yy in range(gh):
                a = int(115 * (1 - yy / max(1, gh - 1)))
                pygame.draw.line(gloss, (255, 255, 255, a), (2, yy + 1), (pw - 2, yy + 1))
            sprite.blit(gloss, (x0, y0))

        n_rect = [to_spr(-hw + t, -(hh + t)), to_spr(hw, -(hh + t)),
                  to_spr(hw, -hh), to_spr(-hw + t, -hh)]
        s_rect = [to_spr(-hw + t, hh), to_spr(hw, hh),
                  to_spr(hw, hh + t), to_spr(-hw + t, hh + t)]
        fill_pole(n_rect, (255, 118, 108), (150, 20, 22))
        fill_pole(s_rect, (120, 150, 255), (22, 34, 150))

        # ── 描边（暗底边 + 亮金属边，强调立体轮廓）──
        pygame.draw.polygon(sprite, (74, 76, 82), sp_verts, max(2, int(2 * zoom)))
        pygame.draw.polygon(sprite, (236, 238, 242), sp_verts, max(1, int(zoom)))

        # ── N / S 标签（带投影）──
        label_font = get_element_font(max(11, int(14 * zoom)), bold=True)
        for txt, (lx, ly) in (("N", (hw, -(hh + t / 2))), ("S", (hw, hh + t / 2))):
            pos = to_spr(lx, ly)
            sh_t = label_font.render(txt, True, (0, 0, 0))
            fg_t = label_font.render(txt, True, (255, 255, 255))
            sprite.blit(sh_t, sh_t.get_rect(center=(pos[0] + 1, pos[1] + 1)))
            sprite.blit(fg_t, fg_t.get_rect(center=pos))

        self._sprite_cache = (key, sprite)
        return sprite, w, h, pad

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']

        sprite, w, h, pad = self._build_sprite(zoom)

        # Compound rotation
        cam_angle = camera.get('angle', 0.0)
        total_angle = -math.degrees(self.angle + cam_angle)
        rotated = pygame.transform.rotate(sprite, total_angle)
        rect = rotated.get_rect(center=(int(sx), int(sy)))
        surface.blit(rotated, rect.topleft)

        if self.is_selected:
            _draw_selection_rect_glow(surface, rect.inflate(-2 * pad, -2 * pad))

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']

        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy

        cam_angle = camera.get('angle', 0.0)
        if cam_angle != 0:
            cos_cam = math.cos(-cam_angle)
            sin_cam = math.sin(-cam_angle)
            dx, dy = dx * cos_cam - dy * sin_cam, dx * sin_cam + dy * cos_cam

        cos_a = math.cos(-self.angle)
        sin_a = math.sin(-self.angle)
        lx = dx * cos_a - dy * sin_a
        ly = dx * sin_a + dy * cos_a

        poly = self._build_polygon()
        poly_screen = [(vx * zoom, vy * zoom) for vx, vy in poly]
        # Check a small neighborhood so edge/corner clicks are not missed
        margin = 2
        for ox in (-margin, 0, margin):
            for oy in (-margin, 0, margin):
                if self._point_in_polygon(lx + ox, ly + oy, poly_screen):
                    return True
        return False

    def get_info(self):
        return f"HorseshoeMagnet: strength={self.strength}"


class Wire(Element):
    """Multi-segment polyline with animated current particles."""

    def __init__(self, points, current=0.0):
        x, y = points[0] if points else (0, 0)
        super().__init__(x, y, (200, 150, 50))
        self.points = list(points)
        self.current = float(current)
        self.auto_current = True
        self.is_ac = False
        self.vx = 0.0  # auto-movement velocity (px/s)
        self.vy = 0.0
        self._speed = 2.5  # particle animation speed multiplier
        self._particles = []
    # ── particle helpers ───────────────────────────────────────────

    def _total_length(self):
        total = 0.0
        for i in range(len(self.points) - 1):
            dx = self.points[i+1][0] - self.points[i][0]
            dy = self.points[i+1][1] - self.points[i][1]
            total += math.hypot(dx, dy)
        return total

    def _init_particles(self):
        total = self._total_length()
        if total <= 0:
            self._particles = []
            return
        spacing = 20
        n = max(2, int(total / spacing))
        self._particles = [{'dist': i * spacing % total} for i in range(n)]

    def update_particles(self, dt=1.0):
        """Advance particle positions along the wire."""
        total = self._total_length()
        if total <= 0 or not self._particles:
            return
        speed = abs(self.current) * self._speed * dt
        direction = 1 if self.current >= 0 else -1
        for p in self._particles:
            p['dist'] += direction * speed
            if p['dist'] >= total:
                p['dist'] -= total
            if p['dist'] < 0:
                p['dist'] += total

    def _position_at(self, dist):
        """World-coord (x, y) at given distance along the wire."""
        if not self.points:
            return (self.x, self.y)
        if dist <= 0:
            return self.points[0]
        total = 0.0
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i+1]
            seg = math.hypot(x2 - x1, y2 - y1)
            if seg <= 0:
                continue
            if dist <= total + seg:
                t = (dist - total) / seg
                return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
            total += seg
        return self.points[-1]

    def move_by(self, dx, dy):
        super().move_by(dx, dy)
        self.points = [(px + dx, py + dy) for px, py in self.points]

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        mx, my = mouse_screen_pos
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i+1]
            sx1, sy1 = world_to_screen(x1, y1, camera, sw, sh)
            sx2, sy2 = world_to_screen(x2, y2, camera, sw, sh)
            if self._seg_dist((mx, my), (sx1, sy1), (sx2, sy2)) < 10:
                return True
        return False

    @staticmethod
    def _seg_dist(p, a, b):
        px, py = p
        ax, ay = a
        bx, by = b
        abx, aby = bx - ax, by - ay
        lsq = abx * abx + aby * aby
        if lsq == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / lsq))
        return math.hypot(px - (ax + t * abx), py - (ay + t * aby))

    def draw(self, surface, camera, screen_size):
        if len(self.points) < 2:
            return
        sw, sh = screen_size
        zoom = camera['zoom']

        def to_screen(wx, wy):
            return world_to_screen(wx, wy, camera, sw, sh)

        sp = [to_screen(p[0], p[1]) for p in self.points]

        # 选中：底层青色辉光描边
        if self.is_selected:
            pygame.draw.lines(surface, (94, 234, 212), False, sp, max(6, int(8 * zoom)))

        # 导线：深色外壳 + 铜色芯线 + 顶部高光，营造金属质感
        casing_w = max(4, int(5 * zoom))
        wire_w = max(2, int(3 * zoom))
        pygame.draw.lines(surface, (70, 50, 18), False, sp, casing_w)
        pygame.draw.lines(surface, self.color, False, sp, wire_w)
        if wire_w >= 3:
            pygame.draw.lines(surface, (245, 205, 120), False, sp, max(1, wire_w // 2))

        # 节点（铜色 + 亮芯）
        nr = max(3, int(4 * zoom))
        for pt in sp:
            pygame.draw.circle(surface, (120, 85, 30), pt, nr + 1)
            pygame.draw.circle(surface, (230, 180, 90), pt, nr)
            pygame.draw.circle(surface, (255, 232, 165), pt, max(1, nr // 2))

        # Direction indication (arrows for DC, "~" for AC)
        if abs(self.current) > 1e-9:
            if self.is_ac:
                # AC: draw wavy line along the wire
                wave_amp = max(2, int(3 * zoom))
                wave_freq = max(5, int(10 * zoom))
                for i in range(len(self.points) - 1):
                    x1, y1 = self.points[i]
                    x2, y2 = self.points[i+1]
                    seg_len = math.hypot(x2 - x1, y2 - y1)
                    if seg_len < 1:
                        continue
                    ux = (x2 - x1) / seg_len
                    uy = (y2 - y1) / seg_len
                    nx, ny = -uy, ux  # normal
                    steps = max(2, int(seg_len / 4))
                    pts = []
                    for s in range(steps + 1):
                        t = s / steps
                        cx = x1 + (x2 - x1) * t
                        cy = y1 + (y2 - y1) * t
                        wave = math.sin(t * seg_len / wave_freq * math.pi * 2) * wave_amp
                        sx, sy = world_to_screen(cx + nx * wave, cy + ny * wave, camera, sw, sh)
                        pts.append((sx, sy))
                    if len(pts) > 1:
                        pygame.draw.lines(surface, (255, 232, 140), False, pts, max(1, int(2 * zoom)))
            else:
                # DC: arrows (triangles) along the wire
                arrow_spacing = max(30, int(50 * zoom))
                arrow_size = max(4, int(10 * zoom))
                dir_sign = 1 if self.current > 0 else -1
                for i in range(len(self.points) - 1):
                    x1, y1 = self.points[i]
                    x2, y2 = self.points[i+1]
                    seg_len = math.hypot(x2 - x1, y2 - y1)
                    if seg_len < 1:
                        continue
                    ux = (x2 - x1) / seg_len * dir_sign
                    uy = (y2 - y1) / seg_len * dir_sign
                    n_arrows = max(1, int(seg_len / arrow_spacing))
                    for j in range(n_arrows):
                        d = (j + 0.5) * seg_len / n_arrows
                        cx = x1 + (x2 - x1) * d / seg_len
                        cy = y1 + (y2 - y1) * d / seg_len
                        sx, sy = world_to_screen(cx, cy, camera, sw, sh)
                        tip = (sx + ux * arrow_size, sy + uy * arrow_size)
                        l = (sx - ux * arrow_size * 0.35 + uy * arrow_size * 0.5,
                             sy - uy * arrow_size * 0.35 - ux * arrow_size * 0.5)
                        r = (sx - ux * arrow_size * 0.35 - uy * arrow_size * 0.5,
                             sy - uy * arrow_size * 0.35 + ux * arrow_size * 0.5)
                        pygame.draw.polygon(surface, (255, 232, 140), [tip, l, r])

    def get_info(self):
        return f"Wire: I = {self.current:+.2f} A, {len(self.points)} segments"


# ────────────────────────────────────────────────────────────────────────
# Phase 4 – Circuit elements
# ────────────────────────────────────────────────────────────────────────


class ActiveElement(Element):
    """Base for rotated circuit components (Power, Resistor, Capacitor, Inductor)."""

    def __init__(self, x, y, color, angle=0, elem_width=60, elem_height=40):
        super().__init__(x, y, color)
        self.angle = float(angle)
        self.elem_width = float(elem_width)
        self.elem_height = float(elem_height)
        self.current = 0.0
        self._sprite_cache = None   # (key, surface) —— 避免每帧重建符号

    def get_connection_points(self):
        """Return the two terminal positions (left, right) in world coords."""
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        hl = self.elem_width / 2
        return (
            (self.x - hl * cos_a, self.y - hl * sin_a),
            (self.x + hl * cos_a, self.y + hl * sin_a),
        )

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(20, int(self.elem_width * zoom))
        h = max(20, int(self.elem_height * zoom))
        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy
        # Undo camera rotation
        cam_angle = camera.get('angle', 0.0)
        if cam_angle != 0:
            cos_cam = math.cos(-cam_angle)
            sin_cam = math.sin(-cam_angle)
            dx, dy = dx * cos_cam - dy * sin_cam, dx * sin_cam + dy * cos_cam
        cos_a = math.cos(-self.angle)
        sin_a = math.sin(-self.angle)
        lx = dx * cos_a - dy * sin_a
        ly = dx * sin_a + dy * cos_a
        return abs(lx) <= w / 2 and abs(ly) <= h / 2

    def _make_sprite(self, w, h):
        """Subclass hook: draw the circuit symbol on a (w × h) surface."""
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        return surf

    def _sprite_key(self, w, h):
        """子类返回影响外观的状态元组以启用精灵缓存；None 表示每帧重建。"""
        return None

    def _get_sprite(self, w, h):
        key = self._sprite_key(w, h)
        if key is not None and self._sprite_cache is not None \
                and self._sprite_cache[0] == key:
            return self._sprite_cache[1]
        sprite = self._make_sprite(w, h)
        if key is not None:
            self._sprite_cache = (key, sprite)
        return sprite

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(20, int(self.elem_width * zoom))
        h = max(20, int(self.elem_height * zoom))

        sprite = self._get_sprite(w, h)

        # Compound element angle with camera rotation
        cam_angle = camera.get('angle', 0.0)
        total_angle = -math.degrees(self.angle + cam_angle)
        rotated = pygame.transform.rotate(sprite, total_angle)
        rect = rotated.get_rect(center=(int(sx), int(sy)))

        # 霓虹辉光（由符号轮廓生成，统一发光质感）
        glow = _silhouette_glow(rotated, self.color, pad=max(3, int(4 * zoom)),
                                alpha=70)
        if glow is not None:
            surface.blit(glow, glow.get_rect(center=(int(sx), int(sy))).topleft)

        surface.blit(rotated, rect.topleft)

        if self.is_selected:
            _draw_selection_rect_glow(surface, rect)


class Power(ActiveElement):
    """Voltage / current source with DC/AC mode and on/off switch."""

    def __init__(self, x, y, ptype='V', value=12.0, angle=0, mode='DC', frequency=50.0):
        super().__init__(x, y, (220, 60, 60), angle, 60, 80)
        self.ptype = ptype    # 'V' or 'I'
        self.value = value
        self.mode = mode      # 'DC' or 'AC'
        self.frequency = float(frequency)
        self.switched_on = False
    def draw(self, surface, camera, screen_size):
        """Draw the Power sprite plus a floating label box below it."""
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(20, int(self.elem_width * zoom))
        h = max(20, int(self.elem_height * zoom))

        # Draw the sprite via ActiveElement
        ActiveElement.draw(self, surface, camera, screen_size)

        # ── Floating label box below the element ──────────────────
        sep = "~" if self.mode == 'AC' else "="
        text = f"{self.ptype}{sep}{self.value}"
        lbl_size = max(10, int(18 * zoom))
        f_lbl = get_element_font(lbl_size, bold=False)
        lbl = f_lbl.render(text, True, (220, 220, 240))

        pad_x, pad_y = 8, 4
        box_w = lbl.get_width() + pad_x * 2
        box_h = lbl.get_height() + pad_y * 2
        box_x = int(sx - box_w // 2)
        box_y = int(sy + h // 2 + max(2, 3 * zoom))

        # Background card
        card = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        card_rect = card.get_rect()
        pygame.draw.rect(card, (20, 18, 36, 210), card_rect, border_radius=6)
        pygame.draw.rect(card, (62, 56, 96, 180), card_rect, 1, border_radius=6)
        surface.blit(card, (box_x, box_y))

        # Text
        surface.blit(lbl, (box_x + pad_x, box_y + pad_y))

        # On/Off indicator
        state_text = "ON" if self.switched_on else "OFF"
        state_size = max(8, int(13 * zoom))
        f_state = get_element_font(state_size, bold=True)
        state_color = (80, 220, 80) if self.switched_on else (160, 80, 80)
        state_lbl = f_state.render(state_text, True, state_color)
        state_x = box_x + box_w + 4
        state_y = box_y + (box_h - state_lbl.get_height()) // 2
        surface.blit(state_lbl, (state_x, state_y))

    def _switch_center(self, w, h):
        """Return (cx, cy, r) of the switch button in sprite-local coords."""
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 4
        sr = max(4, r // 3)
        return (cx, cy - int(r * 0.65), sr)

    def _sprite_key(self, w, h):
        return (w, h, self.ptype, self.mode, round(self.value, 3), self.switched_on)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 4
        lw = max(2, r // 11)
        # 玻璃填充圆盘 + 双层描边
        disk = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(disk, (224, 64, 64, 48), (r + 2, r + 2), r)
        surf.blit(disk, (cx - r - 2, cy - r - 2))
        pygame.draw.circle(surf, (236, 82, 82), (cx, cy), r, lw)
        pygame.draw.circle(surf, (255, 130, 130), (cx, cy), max(1, r - lw), 1)

        # +/- signs at left/right
        sym_size = max(14, min(r, 32))
        f_sym = get_element_font(sym_size, bold=True)
        if self.mode == 'DC':
            plus = f_sym.render("+", True, (255, 255, 255))
            minus = f_sym.render("-", True, (255, 255, 255))
            surf.blit(plus, plus.get_rect(center=(cx - r // 2, cy)))
            surf.blit(minus, minus.get_rect(center=(cx + r // 2, cy)))
        else:
            f_tilde = get_element_font(int(sym_size * 1.4), bold=True)
            tilde = f_tilde.render("~", True, (255, 255, 100))
            surf.blit(tilde, tilde.get_rect(center=(cx, cy + sym_size // 2)))

        # ── Switch button (top of the circle) ──────────────────────
        scx, scy, sr = self._switch_center(w, h)
        if self.switched_on:
            sw_color = (80, 220, 80)
            dot_color = (50, 180, 50)
        else:
            sw_color = (160, 160, 160)
            dot_color = (120, 120, 120)
        pygame.draw.circle(surf, (60, 60, 60), (scx, scy), sr + 2)   # shadow
        pygame.draw.circle(surf, sw_color, (scx, scy), sr)           # body
        pygame.draw.circle(surf, dot_color, (scx, scy), sr, 1)       # border
        # "|" power symbol
        bar_w = max(1, sr // 3)
        bar_h = int(sr * 1.2)
        bar_rect = pygame.Rect(scx - bar_w // 2, scy - bar_h // 2, bar_w, bar_h)
        pygame.draw.rect(surf, (255, 255, 255), bar_rect)
        return surf

    def is_switch_click(self, mouse_screen_pos, camera, screen_size):
        """Check if a screen-coord click is on the switch button."""
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(20, int(self.elem_width * zoom))
        h = max(20, int(self.elem_height * zoom))
        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy
        # Undo camera rotation
        cam_angle = camera.get('angle', 0.0)
        if cam_angle != 0:
            cos_cam = math.cos(-cam_angle)
            sin_cam = math.sin(-cam_angle)
            dx, dy = dx * cos_cam - dy * sin_cam, dx * sin_cam + dy * cos_cam
        cos_a = math.cos(-self.angle)
        sin_a = math.sin(-self.angle)
        lx = dx * cos_a - dy * sin_a + w // 2   # sprite-local
        ly = dx * sin_a + dy * cos_a + h // 2
        scx, scy, sr = self._switch_center(w, h)
        return math.hypot(lx - scx, ly - scy) < sr

    def toggle_switch(self):
        self.switched_on = not self.switched_on

    def get_info(self):
        state = "ON" if self.switched_on else "OFF"
        freq_str = f", {self.frequency:.1f}Hz" if self.mode == 'AC' else ""
        return f"Power: {self.ptype}={self.value:.1f} ({self.mode}{freq_str}) [{state}]"


class Resistor(ActiveElement):
    """Fixed resistor."""

    def __init__(self, x, y, resistance=1.0, angle=0):
        super().__init__(x, y, (200, 180, 100), angle, 80, 30)
        self.resistance = resistance

    def _sprite_key(self, w, h):
        return (w, h, round(self.resistance, 3))

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cy = h // 2
        # Rectangle body
        bw = max(20, w - 20)
        bh = max(12, h - 8)
        bx = (w - bw) // 2
        by = (h - bh) // 2
        lw = max(2, h // 13)
        col = (245, 225, 160)
        # 玻璃填充体 + 描边
        body = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(body, (240, 220, 150, 52), (0, 0, bw, bh), border_radius=4)
        surf.blit(body, (bx, by))
        pygame.draw.rect(surf, col, (bx, by, bw, bh), lw, border_radius=4)
        # Connection leads
        pygame.draw.line(surf, col, (0, cy), (bx, cy), lw)
        pygame.draw.line(surf, col, (bx + bw, cy), (w, cy), lw)
        return surf

    def get_info(self):
        return f"Resistor: R = {self.resistance:.0f} Ω"


class Capacitor(ActiveElement):
    """Capacitor with two parallel plates."""

    def __init__(self, x, y, capacitance=10.0, angle=0):
        super().__init__(x, y, (100, 200, 255), angle, 50, 50)
        self.capacitance = capacitance
        self.voltage = 0.0

    def _sprite_key(self, w, h):
        return (w, h)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        gap = max(4, w // 6)
        left = (w - gap) // 2
        right = left + gap
        col = (192, 226, 255)
        plate_w = max(3, w // 13)
        lw = max(2, h // 15)
        # Plates
        pygame.draw.line(surf, col, (left, 6), (left, h - 6), plate_w)
        pygame.draw.line(surf, col, (right, 6), (right, h - 6), plate_w)
        # Connection leads
        pygame.draw.line(surf, col, (0, h // 2), (left, h // 2), lw)
        pygame.draw.line(surf, col, (right, h // 2), (w, h // 2), lw)
        return surf

    def get_info(self):
        return f"Capacitor: C = {self.capacitance:.1f} μF, V = {self.voltage:.2f} V"


class Inductor(ActiveElement):
    """Inductor with coil loops."""

    def __init__(self, x, y, inductance=50.0, angle=0):
        super().__init__(x, y, (150, 200, 150), angle, 80, 40)
        self.inductance = inductance

    def _sprite_key(self, w, h):
        return (w, h)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cy = h // 2
        n = 5
        loop_r = min(h // 4, w // (n * 2 + 2))
        spacing = (w - 10) / (n + 1)
        col = (192, 236, 192)
        lw = max(2, loop_r // 4 + 1)
        for i in range(n):
            cx = 5 + spacing * (i + 1)
            pygame.draw.circle(surf, col, (int(cx), cy), loop_r, lw)
        # Connection leads
        pygame.draw.line(surf, col, (0, cy), (int(5 + spacing), cy), lw)
        pygame.draw.line(surf, col, (int(5 + spacing * n), cy), (w, cy), lw)
        return surf

    def get_info(self):
        return f"Inductor: L = {self.inductance:.1f} mH"


class Solenoid(ActiveElement):
    """螺线管 — A cylindrical coil that generates B-field when current flows through it.

    Modeled as a finite solenoid with N turns. The magnetic field is computed
    by treating each turn as a magnetic dipole (Biot–Savart equivalent for
    distances > coil radius), giving the correct dipole-like external field
    and approximate internal uniformity.
    """

    def __init__(self, x, y, coil_length=140, coil_radius=25, turns=50, angle=0):
        super().__init__(x, y, (214, 150, 78), angle, coil_length, coil_radius * 2 + 16)
        self._coil_length = float(coil_length)
        self._coil_radius = float(coil_radius)
        self._turns = int(turns)
        self.winding_clockwise = True  # 绕向: True=顺时针(从右端看), False=逆时针
        # Coil resistance (copper wire approximation) — used by circuit solver
        self.resistance = 2.0

    @property
    def coil_length(self):
        return self._coil_length

    @coil_length.setter
    def coil_length(self, v):
        self._coil_length = float(v)
        self.elem_width = float(v)

    @property
    def coil_radius(self):
        return self._coil_radius

    @coil_radius.setter
    def coil_radius(self, v):
        self._coil_radius = float(v)
        self.elem_height = float(v * 2 + 16)

    @property
    def turns(self):
        return self._turns

    @turns.setter
    def turns(self, v):
        self._turns = int(v)

    @property
    def diameter(self):
        return self._coil_radius * 2

    @diameter.setter
    def diameter(self, v):
        self._coil_radius = float(v) / 2
        self.elem_height = float(self._coil_radius * 2 + 16)

    def get_inductance(self):
        """Solenoid inductance L = μ₀·N²·A/l  (air-core, SI units)."""
        from physics import PX_PER_METER
        MU_0 = 4e-7 * math.pi  # 4π × 10⁻⁷ H/m
        l_m = self.coil_length / PX_PER_METER
        A_m2 = math.pi * (self.coil_radius / PX_PER_METER) ** 2
        if l_m < 1e-10:
            return 0.0
        return MU_0 * (self.turns ** 2) * A_m2 / l_m

    def _sprite_key(self, w, h):
        cur_dir = 0 if abs(self.current) < 1e-9 else (1 if self.current > 0 else -1)
        return (w, h, self._turns, self.winding_clockwise, cur_dir)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cx, cy = w // 2, h // 2

        body_w = max(12, w - 16)
        body_h = max(10, h - 14)
        bx = (w - body_w) // 2
        by = (h - body_h) // 2

        # ── 3D 铜线圆柱体 ──
        n_loops = int(min(self.turns, max(4, body_w // 6)))
        coil = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
        # 暗色管芯（线匝间隙透出）
        pygame.draw.rect(coil, (54, 30, 14), (0, 0, body_w, body_h),
                         border_radius=min(body_h // 2, body_w // 2))
        # 逐匝立体铜线（横向高光形成绕线纹理）
        cop_dark = (116, 60, 26)
        cop_mid = (198, 118, 54)
        cop_hi = (255, 216, 152)
        seg = body_w / n_loops
        tw = max(2, int(seg * 1.7))
        for i in range(n_loops):
            lx = (i + 0.5) * seg
            for dx in range(-tw // 2, tw // 2 + 1):
                u = dx / (tw / 2) if tw > 0 else 0.0       # -1..1 跨线宽
                prof = math.sqrt(max(0.0, 1.0 - u * u))     # 铜线圆截面
                hl = max(0.0, 1.0 - ((u + 0.4) ** 2) * 2.2)  # 高光偏左上
                col = tuple(
                    min(255, int(cop_dark[k] + (cop_mid[k] - cop_dark[k]) * prof
                                 + (cop_hi[k] - cop_mid[k]) * hl * 0.9))
                    for k in range(3))
                x = int(lx + dx)
                if 0 <= x < body_w:
                    pygame.draw.line(coil, col, (x, 0), (x, body_h))
        # 圆柱竖直明暗（上下变暗 → 横卧圆柱的体积感）
        vshade = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
        for yy in range(body_h):
            v = (yy / max(1, body_h - 1)) * 2 - 1
            s = math.sqrt(max(0.0, 1.0 - v * v))
            g = int(70 + 185 * s)
            pygame.draw.line(vshade, (g, g, g, 255), (0, yy), (body_w, yy))
        coil.blit(vshade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        # 顶部长条高光
        spec = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
        sh0 = int(body_h * 0.16)
        shh = max(2, int(body_h * 0.26))
        for k in range(shh):
            a = int(120 * (1 - abs(k - shh / 2) / (shh / 2)))
            pygame.draw.line(spec, (255, 255, 255, a), (3, sh0 + k), (body_w - 3, sh0 + k))
        coil.blit(spec, (0, 0))
        # 胶囊圆角遮罩（圆柱两端收圆）
        cmask = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
        pygame.draw.rect(cmask, (255, 255, 255, 255), (0, 0, body_w, body_h),
                         border_radius=min(body_h // 2, body_w // 2))
        coil.blit(cmask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(coil, (bx, by))
        # 端部铜环（左端暗、右端亮，强调管口立体）
        cap_w = max(3, int(seg * 0.9))
        pygame.draw.ellipse(surf, (70, 40, 18), (bx - cap_w // 2, by, cap_w, body_h))
        pygame.draw.ellipse(surf, (150, 92, 46), (bx - cap_w // 2, by, cap_w, body_h), 1)
        pygame.draw.ellipse(surf, (150, 92, 46),
                            (bx + body_w - cap_w // 2, by, cap_w, body_h))
        pygame.draw.ellipse(surf, (240, 186, 116),
                            (bx + body_w - cap_w // 2, by, cap_w, body_h), 1)
        # 整体描边
        pygame.draw.rect(surf, (92, 52, 24), (bx, by, body_w, body_h), 1,
                         border_radius=min(body_h // 2, body_w // 2))

        # ── Winding current direction arrows (if current flows) ──
        if abs(self.current) > 1e-9:
            arrow_color = (255, 220, 80)
            # On the top surface: arrow points rightward when (current>=0) == winding_clockwise
            top_right = (self.current >= 0) == self.winding_clockwise
            a_sign = 1 if top_right else -1

            step = max(1, n_loops // 4)  # mark ~4 windings
            arrow_len = 6
            for i in range(step, n_loops, step):
                t = (i + 0.5) / n_loops
                lx = bx + t * body_w

                # Top surface arrow
                y_top = by + 3
                pygame.draw.line(surf, arrow_color,
                                 (lx - a_sign * arrow_len, y_top),
                                 (lx + a_sign * arrow_len, y_top), 2)
                tx = lx + a_sign * arrow_len
                pygame.draw.line(surf, arrow_color,
                                 (tx, y_top), (tx - a_sign * 3, y_top - 3), 2)

                # Bottom surface arrow (opposite direction)
                y_bot = by + body_h - 3
                pygame.draw.line(surf, arrow_color,
                                 (lx + a_sign * arrow_len, y_bot),
                                 (lx - a_sign * arrow_len, y_bot), 2)
                tx_b = lx - a_sign * arrow_len
                pygame.draw.line(surf, arrow_color,
                                 (tx_b, y_bot), (tx_b + a_sign * 3, y_bot - 3), 2)

        # ── External circuit current arrow (if current flows) ──
        if abs(self.current) > 1e-9:
            arrow_color = (255, 220, 80)
            dir_sign = 1 if self.current > 0 else -1
            mid_y = cy + body_h // 2 + 5
            arrow_len = min(body_w // 4, 20)
            cx_arrow = cx - dir_sign * arrow_len // 2
            tip_x = cx_arrow + dir_sign * arrow_len
            pygame.draw.line(surf, arrow_color, (cx_arrow, mid_y), (tip_x, mid_y), 2)
            # Arrowhead
            hl = 5
            pygame.draw.line(surf, arrow_color, (tip_x, mid_y),
                             (tip_x - dir_sign * hl, mid_y - hl), 2)
            pygame.draw.line(surf, arrow_color, (tip_x, mid_y),
                             (tip_x - dir_sign * hl, mid_y + hl), 2)

        # ── N / S magnetic pole labels ──
        if abs(self.current) > 1e-9:
            lbl_font = get_element_font(max(9, h // 4))
            # N pole side determined by current direction AND winding direction (right-hand rule)
            n_on_right = (self.current >= 0) != self.winding_clockwise
            n_label = lbl_font.render("N", True, (255, 120, 120))
            s_label = lbl_font.render("S", True, (120, 160, 255))
            if n_on_right:
                n_x = bx + body_w - 2 - n_label.get_width()
                s_x = bx + 2
            else:
                n_x = bx + 2
                s_x = bx + body_w - 2 - n_label.get_width()
            n_sh = lbl_font.render("N", True, (40, 10, 10))
            s_sh = lbl_font.render("S", True, (10, 16, 50))
            surf.blit(n_sh, (n_x + 1, by + 3))
            surf.blit(s_sh, (s_x + 1, by + 3))
            surf.blit(n_label, (n_x, by + 2))
            surf.blit(s_label, (s_x, by + 2))

        # ── Connection leads（铜质引线：暗壳 + 铜芯 + 高光）──
        lead_w = max(3, h // 6)
        for x0, x1 in ((0, bx), (bx + body_w, w)):
            pygame.draw.line(surf, (70, 50, 18), (x0, cy), (x1, cy), lead_w)
            pygame.draw.line(surf, (214, 150, 78), (x0, cy), (x1, cy), max(2, lead_w - 2))
            pygame.draw.line(surf, (245, 205, 120), (x0, cy - 1), (x1, cy - 1), 1)

        return surf

    def get_info(self):
        return (f"螺线管: N={self.turns}, L={self.coil_length:.0f}, "
                f"R={self.coil_radius:.0f}, I={self.current:+.2f}A, "
                f"R_coil={self.resistance:.1f}Ω")


class Ammeter(ActiveElement):
    """Ammeter — measures current through a branch (connected in series)."""

    R_METER = 0.001  # near-zero resistance

    def __init__(self, x, y, angle=0):
        super().__init__(x, y, (255, 200, 80), angle, 70, 48)
        self.display_value = 0.0
        self.is_ac = False
        self._rms_max = -1e30
        self._rms_min = 1e30
        self._rms_value = 0.0

    def _sprite_key(self, w, h):
        label = f"~{self.display_value:.2f}" if self.is_ac else f"{self.display_value:.2f}"
        return (w, h, label)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 6
        lw = max(2, r // 11)
        # 玻璃填充盘 + 描边
        disk = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(disk, (255, 200, 80, 48), (r + 2, r + 2), r)
        surf.blit(disk, (cx - r - 2, cy - r - 2))
        pygame.draw.circle(surf, (255, 212, 110), (cx, cy), r, lw)
        # "A" in center
        f = get_element_font(max(14, r), bold=True)
        a_txt = f.render("A", True, (255, 236, 165))
        surf.blit(a_txt, a_txt.get_rect(center=(cx, cy - 2)))
        # Value below
        fs = get_element_font(max(7, r * 2 // 3))
        label = f"~{self.display_value:.2f}" if self.is_ac else f"{self.display_value:.2f}"
        txt = fs.render(label, True, (220, 200, 120))
        surf.blit(txt, txt.get_rect(center=(cx, cy + r * 2 // 3)))
        # Connection leads
        pygame.draw.line(surf, (255, 212, 110), (0, cy), (cx - r, cy), lw)
        pygame.draw.line(surf, (255, 212, 110), (cx + r, cy), (w, cy), lw)
        return surf

    def get_info(self):
        prefix = "~" if self.is_ac else ""
        return f"Ammeter: {prefix}{self.display_value:.4f} A"


class Voltmeter(ActiveElement):
    """Voltmeter — measures voltage between two nodes (connected in parallel)."""

    R_METER = 10e6  # 10 MΩ — very high resistance

    def __init__(self, x, y, angle=0):
        super().__init__(x, y, (100, 220, 255), angle, 70, 48)
        self.display_value = 0.0
        self.is_ac = False
        self._rms_max = -1e30
        self._rms_min = 1e30
        self._rms_value = 0.0

    def _sprite_key(self, w, h):
        label = f"~{self.display_value:.2f}" if self.is_ac else f"{self.display_value:.2f}"
        return (w, h, label)

    def _make_sprite(self, w, h):
        surf = super()._make_sprite(w, h)
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 6
        lw = max(2, r // 11)
        # 玻璃填充盘 + 描边
        disk = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(disk, (100, 220, 255, 48), (r + 2, r + 2), r)
        surf.blit(disk, (cx - r - 2, cy - r - 2))
        pygame.draw.circle(surf, (130, 228, 255), (cx, cy), r, lw)
        # "V" in center
        f = get_element_font(max(14, r), bold=True)
        v_txt = f.render("V", True, (195, 244, 255))
        surf.blit(v_txt, v_txt.get_rect(center=(cx, cy - 2)))
        # Value below
        fs = get_element_font(max(7, r * 2 // 3))
        label = f"~{self.display_value:.2f}" if self.is_ac else f"{self.display_value:.2f}"
        txt = fs.render(label, True, (140, 210, 230))
        surf.blit(txt, txt.get_rect(center=(cx, cy + r * 2 // 3)))
        # Connection leads
        pygame.draw.line(surf, (130, 228, 255), (0, cy), (cx - r, cy), lw)
        pygame.draw.line(surf, (130, 228, 255), (cx + r, cy), (w, cy), lw)
        return surf

    def get_info(self):
        prefix = "~" if self.is_ac else ""
        return f"Voltmeter: {prefix}{self.display_value:.2f} V"


# ────────────────────────────────────────────────────────────────────────
# Phase 4 – Conductors
# ────────────────────────────────────────────────────────────────────────


class MetalBall(Element):
    """Solid metal sphere or hollow spherical shell."""

    def __init__(self, x, y, r_outer=40, r_inner=0):
        super().__init__(x, y, (200, 202, 204))
        self.r_outer = r_outer
        self.r_inner = r_inner   # 0 → solid
    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        outer = max(4, int(self.r_outer * zoom))
        inner = max(0, int(self.r_inner * zoom))
        ix, iy = int(sx), int(sy)

        if 0 < inner < outer:
            # 空心球壳（金属渐变 + 不透明深色内腔）
            surface.blit(_render_metal_ring(outer, inner, transparent=False),
                         (ix - outer, iy - outer))
            _blit_specular(surface, ix - outer // 2, iy - outer // 2,
                           max(2, (outer - inner) // 2), 120)
        else:
            # 实心金属球（柔和明暗 + 体积感）
            surface.blit(_render_sphere(outer, (206, 209, 214)),
                         (ix - outer, iy - outer))
            pygame.draw.circle(surface, (232, 234, 238), (ix, iy), outer, 2)
            _blit_specular(surface, ix - outer // 3, iy - int(outer * 0.42),
                           max(2, outer // 3), 175)
            _blit_specular(surface, ix - outer // 2, iy - outer // 2,
                           max(1, outer // 6), 130)

        if self.is_selected:
            _draw_selection_glow(surface, ix, iy, outer)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        r = max(4, int(self.r_outer * camera['zoom']))
        mx, my = mouse_screen_pos
        return (mx - sx) ** 2 + (my - sy) ** 2 <= (r + 5) ** 2

    def get_info(self):
        if self.r_inner > 0:
            return f"Metal shell: r={self.r_outer}, inner={self.r_inner}"
        return f"Metal ball: r={self.r_outer}"


class MetalShell(Element):
    """Hollow conducting spherical shell with inner radius and wall thickness."""

    def __init__(self, x, y, inner_radius=90, thickness=10):
        super().__init__(x, y, (200, 202, 204))
        self._inner_radius = float(inner_radius)
        self._thickness = float(thickness)
    @property
    def inner_radius(self):
        return self._inner_radius

    @inner_radius.setter
    def inner_radius(self, v):
        self._inner_radius = float(v)

    @property
    def thickness(self):
        return self._thickness

    @thickness.setter
    def thickness(self, v):
        self._thickness = float(v)

    @property
    def r_outer(self):
        return self._inner_radius + self._thickness

    @property
    def r_inner(self):
        return self._inner_radius

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        outer = max(4, int(self.r_outer * zoom))
        inner = max(2, int(self.r_inner * zoom))
        ix, iy = int(sx), int(sy)

        if inner >= outer:
            inner = outer - 2

        # 金属环：竖直金属渐变 + 透明内腔（背后元素可透出）
        surface.blit(_render_metal_ring(outer, inner, transparent=True),
                     (ix - outer, iy - outer))
        # 壳壁上的一点高光，强调金属质感
        _blit_specular(surface, ix - int(outer * 0.45), iy - int(outer * 0.6),
                       max(2, (outer - inner) // 2), 110)

        if self.is_selected:
            _draw_selection_glow(surface, ix, iy, outer)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        r_outer = max(4, int(self.r_outer * camera['zoom']))
        r_inner = max(2, int(self.r_inner * camera['zoom']))
        mx, my = mouse_screen_pos
        d2 = (mx - sx) ** 2 + (my - sy) ** 2
        if d2 > (r_outer + 5) ** 2:
            return False
        if d2 < (r_inner - 5) ** 2:
            return False
        return True

    def get_info(self):
        return f"Metal shell: inner_r={self.inner_radius:.0f}, thickness={self.thickness:.0f}"


class MetalPlate(Element):
    """Infinite conducting plane (rotatable, with adjustable thickness)."""

    # Half-length used for visual rendering (extends well beyond screen bounds)
    _SCREEN_EXTEND = 10000.0

    def __init__(self, x, y, thickness=20, angle=0):
        super().__init__(x, y, (200, 202, 204))
        self.thickness = thickness    # cross-section thickness
        self.angle = float(angle)     # radians, 0 = horizontal plate
    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        hw = self._SCREEN_EXTEND
        ht = max(3, self.thickness / 2)

        def edge_pts(off):
            p = []
            for lx in (-hw, hw):
                rx = self.x + lx * cos_a - off * sin_a
                ry = self.y + lx * sin_a + off * cos_a
                p.append(world_to_screen(rx, ry, camera, sw, sh))
            return p

        # 跨厚度的金属渐变（上缘亮、下缘暗）
        base = (200, 202, 206)
        top = tuple(min(255, base[k] + 34) for k in range(3))
        bot = tuple(max(0, base[k] - 50) for k in range(3))
        n = max(4, min(int(2 * ht * zoom), 26))
        line_w = max(2, int(math.ceil(2 * ht * zoom / n)) + 1)
        for k in range(n):
            t = k / (n - 1)
            off = -ht + 2 * ht * t
            col = tuple(int(top[j] + (bot[j] - top[j]) * t) for j in range(3))
            a, b = edge_pts(off)
            pygame.draw.line(surface, col, a, b, line_w)

        # 顶缘高光 / 底缘暗边
        tp = edge_pts(-ht)
        pygame.draw.line(surface, (236, 238, 242), tp[0], tp[1], 2)
        bp = edge_pts(ht)
        pygame.draw.line(surface, (150, 152, 158), bp[0], bp[1], 2)

        if self.is_selected:
            sel_pts = []
            expand = 4
            for lx, ly in [(-hw, -ht), (hw, -ht), (hw, ht), (-hw, ht)]:
                sx_extra = 1 if lx > 0 else -1
                sy_extra = 1 if ly > 0 else -1
                ex = lx + sx_extra * expand / zoom if zoom > 0 else lx
                ey = ly + sy_extra * expand / zoom if zoom > 0 else ly
                rx = self.x + ex * cos_a - ey * sin_a
                ry = self.y + ex * sin_a + ey * cos_a
                sel_pts.append(world_to_screen(rx, ry, camera, sw, sh))
            # 主题青色选中描边（外柔 + 内亮）
            pygame.draw.polygon(surface, (45, 212, 191), sel_pts, 4)
            pygame.draw.polygon(surface, (94, 234, 212), sel_pts, 2)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        cx, cy = camera['x'], camera['y']
        cam_angle = camera.get('angle', 0.0)
        # Inverse camera rotation to get world-space mouse position
        dx = (mouse_screen_pos[0] - sw / 2) / zoom
        dy = (mouse_screen_pos[1] - sh / 2) / zoom
        if cam_angle != 0:
            cos_a = math.cos(cam_angle)
            sin_a = math.sin(cam_angle)
            dx, dy = dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a
        mx, my = dx + cx, dy + cy
        dx, dy = mx - self.x, my - self.y
        # Project onto normal vector to get perpendicular distance
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        nx, ny = sin_a, -cos_a
        dist = abs(dx * nx + dy * ny)
        return dist <= self.thickness / 2 + 8


class MotionCharge(Element):
    """A charged test particle experiencing Lorentz force F = q(E + v x B)."""

    def __init__(self, x, y, q=1e-6, mass=1e-4, vx=0.0, vy=0.0):
        super().__init__(x, y, (0, 255, 128))
        self.q = float(q)
        self.mass = float(mass)
        self.vx = float(vx)
        self.vy = float(vy)
        self.radius = 1
        self.fixed = False
        self.trail = []

    # ── physics update (symplectic Boris integrator) ─────────────────

    def update(self, field_system, elements, dt):
        """Run symplectic integration (no collision check).

        After all MotionCharges have been updated, call
        :meth:`resolve_collisions` to detect and roll back overlaps.
        """
        if self.fixed:
            return
        self._saved_x, self._saved_y = self.x, self.y
        self._saved_vx, self._saved_vy = self.vx, self.vy
        substeps = 4
        dt_sub = dt / substeps
        for _ in range(substeps):
            self._symplectic_step(field_system, elements, dt_sub)

    @classmethod
    def resolve_all_collisions(cls, motion_charges, elements):
        """Collision resolution with reflection law.

        1. Captures the post-physics position of each particle.
        2. Detects overlaps (Charge ↔ MotionCharge and
           MotionCharge ↔ MotionCharge) against these frozen positions.
        3. Rolls back every collided particle to its pre-frame state, then
           reflects velocity across the collision normal (angle of incidence
           = angle of reflection), conserving kinetic energy.

        For MotionCharge ↔ MotionCharge the collision is treated as
        equal-mass elastic (normal velocity components are exchanged).

        Returns the set of collided particles.
        """
        # Pass 1 – snapshot post-physics positions so that a particle that
        #         has already rolled back doesn't hide an overlap.
        for mc in motion_charges:
            if not mc.fixed:
                mc._post_x, mc._post_y = mc.x, mc.y

        # Pass 2 – detect overlaps, collecting (mc, nx, ny) collision info.
        collisions = []   # [(mc, nx, ny)]  for Charge↔MotionCharge
        mc_pair = []      # [(a, b, nx, ny)] for MotionCharge↔MotionCharge
        for i, a in enumerate(motion_charges):
            if a.fixed or not hasattr(a, '_saved_x'):
                continue
            # ── Fixed Charge collisions ──
            for el in elements:
                if el is a or not isinstance(el, Charge):
                    continue
                dx = a._post_x - el.x
                dy = a._post_y - el.y
                r_sum = a.radius + el.radius
                if dx*dx + dy*dy < r_sum*r_sum:
                    dist = math.hypot(dx, dy)
                    if dist > 1e-9:
                        nx, ny = dx / dist, dy / dist
                    else:
                        nx, ny = 1.0, 0.0
                    collisions.append((a, nx, ny))
                    break
            # ── MotionCharge–MotionCharge collisions ──
            for b in motion_charges[i+1:]:
                if b.fixed or not hasattr(b, '_saved_x'):
                    continue
                dx = a._post_x - b._post_x
                dy = a._post_y - b._post_y
                r_sum = a.radius + b.radius
                if dx*dx + dy*dy < r_sum*r_sum:
                    dist = math.hypot(dx, dy)
                    if dist > 1e-9:
                        nx, ny = dx / dist, dy / dist
                    else:
                        nx, ny = 1.0, 0.0
                    mc_pair.append((a, b, nx, ny))

        # Pass 3 – roll back and apply reflection
        rollback = set()
        for mc, nx, ny in collisions:
            rollback.add(mc)
            mc.x, mc.y = mc._saved_x, mc._saved_y
            # Reflect v across normal: v' = v - 2(v·n̂)n̂
            vn = mc._saved_vx * nx + mc._saved_vy * ny
            mc.vx = mc._saved_vx - 2.0 * vn * nx
            mc.vy = mc._saved_vy - 2.0 * vn * ny

        for a, b, nx, ny in mc_pair:
            rollback.add(a)
            rollback.add(b)
            a.x, a.y = a._saved_x, a._saved_y
            b.x, b.y = b._saved_x, b._saved_y
            # Equal-mass elastic: exchange normal velocity components
            v1n = a._saved_vx * nx + a._saved_vy * ny
            v2n = b._saved_vx * nx + b._saved_vy * ny
            a.vx = a._saved_vx + (v2n - v1n) * nx
            a.vy = a._saved_vy + (v2n - v1n) * ny
            b.vx = b._saved_vx + (v1n - v2n) * nx
            b.vy = b._saved_vy + (v1n - v2n) * ny

        return rollback

    def _symplectic_step(self, field_system, elements, dt):
        """Boris/Verlet symplectic integrator — conserves energy for
        electrostatic + magnetostatic Lorentz force.

        Position in pixels, velocity in px/s.  Field system returns
        real SI values (N/C, T) that must be converted.
        """
        qm = self.q / self.mass  # C/kg

        # 1. Half-step electric acceleration at current position
        Ex, Ey = field_system.get_efield(self.x, self.y, elements, exclude=self)
        # acceleration: a = (q/m)·E  (m/s²), convert to px/s²
        ax_px = qm * Ex * PX_PER_METER
        ay_px = qm * Ey * PX_PER_METER
        vx = self.vx + 0.5 * ax_px * dt
        vy = self.vy + 0.5 * ay_px * dt

        # 2. Full-step magnetic rotation (Boris rotation — preserves |v|)
        Bz = field_system.get_wire_bfield(self.x, self.y, elements)
        if abs(Bz) > 1e-12:
            theta = -qm * Bz * dt   # screen coords (+y down) negates cross product sign
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            vx, vy = vx * cos_t + vy * sin_t, -vx * sin_t + vy * cos_t

        # 3. Position update with rotated velocity (px/s → px)
        self.x += vx * dt
        self.y += vy * dt

        # 4. Second half-step electric acceleration at NEW position
        Ex2, Ey2 = field_system.get_efield(self.x, self.y, elements, exclude=self)
        self.vx = vx + 0.5 * qm * Ex2 * PX_PER_METER * dt
        self.vy = vy + 0.5 * qm * Ey2 * PX_PER_METER * dt

    # ── drawing ─────────────────────────────────────────────────────

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        ix, iy = world_to_screen(self.x, self.y, camera, sw, sh)
        r = max(3, int(self.radius * zoom))
        cam_angle = camera.get('angle', 0.0)

        # ── Trail ──
        if len(self.trail) > 1:
            pts = [world_to_screen(p[0], p[1], camera, sw, sh) for p in self.trail]
            if len(pts) > 2:
                pygame.draw.lines(surface, (0, 255, 100), False, pts, max(1, int(2 * zoom)))
            else:
                pygame.draw.line(surface, (0, 255, 100), pts[0], pts[1], max(1, int(2 * zoom)))

        # ── Glow ──
        glow = pygame.Surface((r*4, r*4), pygame.SRCALPHA)
        for i in range(r*2, 0, -1):
            a = int(60 * (1 - i/(r*2)))
            pygame.draw.circle(glow, (0, 255, 128, a), (r*2, r*2), i)
        surface.blit(glow, (ix - r*2, iy - r*2))

        # ── Body ──
        body = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        for i in range(r, 0, -1):
            t = 1 - i/r
            cr = min(255, int(0 + 255*t*0.7))
            cg = min(255, int(255 + 0*t*0.7))
            cb = min(255, int(128 + 255*t*0.7))
            pygame.draw.circle(body, (cr, cg, cb), (r, r), i)
        surface.blit(body, (ix - r, iy - r))
        pygame.draw.circle(surface, (255, 255, 255), (ix, iy), r, 1)

        # ── Velocity arrow (rotated by camera angle) ──
        speed = math.hypot(self.vx, self.vy)
        if speed > 0.5:
            # Rotate velocity direction by camera angle so arrow points correctly on screen
            if cam_angle != 0:
                cos_a = math.cos(cam_angle)
                sin_a = math.sin(cam_angle)
                rvx = self.vx * cos_a - self.vy * sin_a
                rvy = self.vx * sin_a + self.vy * cos_a
            else:
                rvx, rvy = self.vx, self.vy
            scale = min(30, max(8, speed * 2)) * zoom
            ex = ix + int(rvx / speed * scale)
            ey = iy + int(rvy / speed * scale)
            pygame.draw.line(surface, (255, 255, 100), (ix, iy), (ex, ey), max(1, int(2*zoom)))
            arrow_angle = math.atan2(rvy, rvx)
            hl = max(4, int(8*zoom))
            for sign in (-1, 1):
                ha = arrow_angle + sign * 2.5
                hx = ex + int(hl * math.cos(ha))
                hy = ey + int(hl * math.sin(ha))
                pygame.draw.line(surface, (255, 255, 100), (ex, ey), (hx, hy), max(1, int(2*zoom)))

        # ── Selection ──
        if self.is_selected:
            for i in range(3, 0, -1):
                gr = r + 4 + 3*i
                gs = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
                pygame.draw.circle(gs, (255, 255, 0, 24//i), (gr, gr), gr)
                surface.blit(gs, (ix - gr, iy - gr))
            pygame.draw.circle(surface, (255, 255, 100), (ix, iy), r + 4, 2)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        r = max(3, int(self.radius * camera['zoom']))
        mx, my = mouse_screen_pos
        dx, dy = mx - sx, my - sy
        return dx*dx + dy*dy <= (r+5)*(r+5)

    def get_info(self):
        return f"MotionCharge: q={self.q:.2e} C, m={self.mass:.2e} kg, v=({self.vx:.1f},{self.vy:.1f}) px/s"


# ---------------------------------------------------------------------------
# Bounded field region helpers
# ---------------------------------------------------------------------------

def _screen_to_world(sx, sy, camera, sw, sh):
    """Inverse of world_to_screen: screen → world coords."""
    cx, cy = camera['x'], camera['y']
    zoom = camera['zoom']
    angle = camera.get('angle', 0.0)
    dx = (sx - sw / 2) / zoom
    dy = (sy - sh / 2) / zoom
    if angle != 0.0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx, dy = dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a
    return dx + cx, dy + cy


class RectField(Element):
    """A rectangular region with uniform perpendicular B-field (dots/crosses)."""

    def __init__(self, x, y, width=200, height=150, B_mag=50, direction=1):
        super().__init__(x, y, (100, 180, 255))
        self.width = float(width)
        self.height = float(height)
        self.B_mag = float(B_mag)
        self.direction = int(direction)  # +1 = out of page (⊙), -1 = into page (⊗)
    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        hw = self.width / 2
        hh = self.height / 2

        # Four corners in world → screen
        corners = [(self.x - hw, self.y - hh), (self.x + hw, self.y - hh),
                   (self.x + hw, self.y + hh), (self.x - hw, self.y + hh)]
        pts = [world_to_screen(cx, cy, camera, sw, sh) for cx, cy in corners]

        # Semi-transparent fill
        fill = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.polygon(fill, (100, 180, 255, 30), pts)
        surface.blit(fill, (0, 0))

        # Border
        color = (150, 210, 255) if self.is_selected else (100, 180, 255)
        pygame.draw.polygon(surface, color, pts, 2)

        # Dot/cross pattern (screen-space step ~35px)
        step = max(10, int(35 / zoom))
        dot_size = max(2, int(4 * zoom))
        for wx in _frange(self.x - hw + step/2, self.x + hw, step):
            for wy in _frange(self.y - hh + step/2, self.y + hh, step):
                sx, sy = world_to_screen(wx, wy, camera, sw, sh)
                if self.direction > 0:
                    # ⊙ dot
                    pygame.draw.circle(surface, (180, 220, 255), (sx, sy), dot_size, 1)
                    if dot_size > 2:
                        pygame.draw.circle(surface, (180, 220, 255), (sx, sy), dot_size // 2)
                else:
                    # ⊗ cross
                    d = dot_size
                    pygame.draw.line(surface, (180, 220, 255), (sx-d, sy-d), (sx+d, sy+d), 1)
                    pygame.draw.line(surface, (180, 220, 255), (sx-d, sy+d), (sx+d, sy-d), 1)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        hw = self.width / 2
        hh = self.height / 2
        return (self.x - hw <= wx <= self.x + hw) and (self.y - hh <= wy <= self.y + hh)

    def check_edge(self, mouse_screen_pos, camera, screen_size):
        """Return resize handle name if near edge/corner, else None."""
        sw, sh = screen_size
        zoom = camera['zoom']
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        t = 15 / zoom  # world-space threshold (~15px screen)
        hw = self.width / 2
        hh = self.height / 2
        left, right = self.x - hw, self.x + hw
        top, bottom = self.y - hh, self.y + hh

        if not (left - t <= wx <= right + t and top - t <= wy <= bottom + t):
            return None
        on_left = abs(wx - left) < t
        on_right = abs(wx - right) < t
        on_top = abs(wy - top) < t
        on_bottom = abs(wy - bottom) < t

        if on_left and on_top: return 'nw'
        if on_right and on_top: return 'ne'
        if on_left and on_bottom: return 'sw'
        if on_right and on_bottom: return 'se'
        if on_left: return 'w'
        if on_right: return 'e'
        if on_top: return 'n'
        if on_bottom: return 's'
        return None

    def get_info(self):
        return f"矩形磁场: B={self.B_mag:.2f}T, {self.width:.0f}×{self.height:.0f}" + (" ⊙" if self.direction > 0 else " ⊗")


class RectEfield(Element):
    """A rectangular region with uniform in-plane E-field (arrows, rotatable)."""

    def __init__(self, x, y, width=200, height=150, E_mag=500, direction=1, angle=0):
        super().__init__(x, y, (255, 200, 50))
        self.width = float(width)
        self.height = float(height)
        self.E_mag = float(E_mag)          # N/C
        self.direction = int(direction)     # +1 = right (→), -1 = left (←) in local coords
        self.angle = float(angle)           # radians from horizontal
    def _local_to_world(self, lx, ly):
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        return self.x + lx * cos_a - ly * sin_a, self.y + lx * sin_a + ly * cos_a

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        hw = self.width / 2
        hh = self.height / 2
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)

        # Four corners in local coords → world → screen
        local_corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        pts = []
        for lx, ly in local_corners:
            wx = self.x + lx * cos_a - ly * sin_a
            wy = self.y + lx * sin_a + ly * cos_a
            pts.append(world_to_screen(wx, wy, camera, sw, sh))

        # Semi-transparent fill
        fill = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.polygon(fill, (255, 200, 50, 25), pts)
        surface.blit(fill, (0, 0))

        # Border
        color = (255, 220, 100) if self.is_selected else (255, 200, 50)
        pygame.draw.polygon(surface, color, pts, 2)

        # Plate thickness in screen pixels
        plate_w = max(3, int(5 * zoom))
        arr_color = (255, 210, 80)
        dir_sign = 1 if self.direction > 0 else -1

        # Left/right plates (in local coords: x = ±hw)
        for side_x in (-hw, hw):
            p1 = self._local_to_world(side_x, -hh)
            p2 = self._local_to_world(side_x, hh)
            s1 = world_to_screen(p1[0], p1[1], camera, sw, sh)
            s2 = world_to_screen(p2[0], p2[1], camera, sw, sh)
            pygame.draw.line(surface, (200, 150, 50), s1, s2, plate_w)

        # + / - labels on plates
        font = get_element_font(max(12, int(15 * zoom)))
        for side_x, label in [( -hw, '+' if dir_sign > 0 else '-'),
                               ( hw, '-' if dir_sign > 0 else '+')]:
            wx, wy = self._local_to_world(side_x, 0)
            sx, sy = world_to_screen(wx, wy, camera, sw, sh)
            label_color = (255, 100, 80) if label == '+' else (100, 180, 255)
            txt = font.render(label, True, label_color)
            offset = 14 * zoom
            sx += cos_a * offset * (1 if side_x > 0 else -1)
            sy += sin_a * offset * (1 if side_x > 0 else -1)
            surface.blit(txt, txt.get_rect(center=(sx, sy)))

        # Arrows showing field direction (screen-space step ~50px)
        step = max(12, int(50 / zoom))
        arr_len = max(10, int(18 * zoom))
        arr_w = max(2, int(3 * zoom))
        for lx in _frange(-hw + step, hw - step/2, step):
            for ly in _frange(-hh + step/2, hh, step):
                wx, wy = self._local_to_world(lx, ly)
                sx, sy = world_to_screen(wx, wy, camera, sw, sh)
                # Arrow direction along local x-axis
                dx = cos_a * dir_sign
                dy = sin_a * dir_sign
                tail_x = sx - dx * arr_len
                tail_y = sy - dy * arr_len
                tip_x = sx + dx * arr_len
                tip_y = sy + dy * arr_len
                # Shaft
                pygame.draw.line(surface, arr_color, (tail_x, tail_y), (tip_x, tip_y), arr_w)
                # Filled arrowhead
                head_len = max(5, int(10 * zoom))
                head_w = max(3, int(6 * zoom))
                perp_x = -dy
                perp_y = dx
                pygame.draw.polygon(surface, arr_color, [
                    (tip_x, tip_y),
                    (tip_x - dx * head_len + perp_x * head_w,
                     tip_y - dy * head_len + perp_y * head_w),
                    (tip_x - dx * head_len - perp_x * head_w,
                     tip_y - dy * head_len - perp_y * head_w),
                ])

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        # Transform to local coordinates
        dx = wx - self.x
        dy = wy - self.y
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        lx = dx * cos_a + dy * sin_a
        ly = -dx * sin_a + dy * cos_a
        hw = self.width / 2
        hh = self.height / 2
        return (-hw <= lx <= hw) and (-hh <= ly <= hh)

    def check_edge(self, mouse_screen_pos, camera, screen_size):
        """Return resize handle name if near edge/corner, else None."""
        sw, sh = screen_size
        zoom = camera['zoom']
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        # Transform to local coordinates
        dx = wx - self.x
        dy = wy - self.y
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        lx = dx * cos_a + dy * sin_a
        ly = -dx * sin_a + dy * cos_a
        t = 15 / zoom
        hw = self.width / 2
        hh = self.height / 2

        if not (-hw - t <= lx <= hw + t and -hh - t <= ly <= hh + t):
            return None
        on_left  = abs(lx + hw) < t
        on_right = abs(lx - hw) < t
        on_top    = abs(ly + hh) < t
        on_bottom = abs(ly - hh) < t

        if on_left  and on_top:    return 'nw'
        if on_right and on_top:    return 'ne'
        if on_left  and on_bottom: return 'sw'
        if on_right and on_bottom: return 'se'
        if on_left:   return 'w'
        if on_right:  return 'e'
        if on_top:    return 'n'
        if on_bottom: return 's'
        return None

    def get_info(self):
        d = "→" if self.direction > 0 else "←"
        return f"平行平面电场: E={self.E_mag:.0f}N/C {d}, {self.width:.0f}×{self.height:.0f}"


class CircField(Element):
    """A circular region with uniform perpendicular B-field (dots/crosses)."""

    def __init__(self, x, y, radius=100, B_mag=50, direction=1):
        super().__init__(x, y, (100, 180, 255))
        self.radius = float(radius)
        self.B_mag = float(B_mag)
        self.direction = int(direction)
    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        zoom = camera['zoom']
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        r = max(5, int(self.radius * zoom))

        # Semi-transparent fill
        fill = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(fill, (100, 180, 255, 30), (r, r), r)
        surface.blit(fill, (sx - r, sy - r))

        # Border
        color = (150, 210, 255) if self.is_selected else (100, 180, 255)
        pygame.draw.circle(surface, color, (sx, sy), r, 2)

        # Dot/cross pattern
        step = max(10, int(35 / zoom))
        dot_size = max(2, int(4 * zoom))
        r_world = self.radius
        for wx in _frange(self.x - r_world + step/2, self.x + r_world, step):
            for wy in _frange(self.y - r_world + step/2, self.y + r_world, step):
                if (wx - self.x)**2 + (wy - self.y)**2 <= r_world * r_world:
                    sx_i, sy_i = world_to_screen(wx, wy, camera, sw, sh)
                    if self.direction > 0:
                        pygame.draw.circle(surface, (180, 220, 255), (sx_i, sy_i), dot_size, 1)
                        if dot_size > 2:
                            pygame.draw.circle(surface, (180, 220, 255), (sx_i, sy_i), dot_size // 2)
                    else:
                        d = dot_size
                        pygame.draw.line(surface, (180, 220, 255), (sx_i-d, sy_i-d), (sx_i+d, sy_i+d), 1)
                        pygame.draw.line(surface, (180, 220, 255), (sx_i-d, sy_i+d), (sx_i+d, sy_i-d), 1)

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        dx = wx - self.x
        dy = wy - self.y
        return dx*dx + dy*dy <= self.radius * self.radius

    def check_edge(self, mouse_screen_pos, camera, screen_size):
        """Return 'r' if near the circle's edge for radius resize."""
        sw, sh = screen_size
        zoom = camera['zoom']
        wx, wy = _screen_to_world(mouse_screen_pos[0], mouse_screen_pos[1], camera, sw, sh)
        dist = math.hypot(wx - self.x, wy - self.y)
        t = 15 / zoom
        # Near the circumference and within reasonable range
        if abs(dist - self.radius) < t:
            return 'r'
        return None

    def get_info(self):
        return f"圆形磁场: B={self.B_mag:.2f}T, r={self.radius:.0f}" + (" ⊙" if self.direction > 0 else " ⊗")


class TextBox(Element):
    """文本框 — A text annotation box for notes on the canvas.

    Displays user-defined text with a background box. Right-click to
    adjust box size, font size, or delete.
    """

    def __init__(self, x, y, text='备注', box_width=160, box_height=60, font_size=18):
        super().__init__(x, y, (224, 224, 240))
        self.text = text
        self.box_width = float(box_width)
        self.box_height = float(box_height)
        self.font_size = int(font_size)

    def draw(self, surface, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(1, int(self.box_width * zoom))
        h = max(1, int(self.box_height * zoom))
        px, py = int(sx - w / 2), int(sy - h / 2)

        # ── 霓虹玻璃卡片（紫主青辅，呼应整体 UI 主题）──────────────
        radius = min(14, max(3, int(min(w, h) * 0.16)))

        # 选中时的青色外发光
        if self.is_selected:
            pad = 12
            glow = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            for i in range(5, 0, -1):
                a = 16 + (5 - i) * 12
                pygame.draw.rect(
                    glow, (94, 234, 212, a),
                    (pad - i * 2, pad - i * 2, w + i * 4, h + i * 4),
                    border_radius=radius + i * 2)
            surface.blit(glow, (px - pad, py - pad))

        # 玻璃底（带渐变与高光，缓存复用）
        line_h = max(3, int(self.font_size * zoom * 1.3))
        surface.blit(_textbox_card(w, h, radius, line_h), (px, py))

        # 左侧强调条（选中青色，常态霓虹紫）
        accent = (94, 234, 212) if self.is_selected else (139, 92, 246)
        bar_w = max(2, int(3 * zoom))
        if bar_w < w:
            bar = pygame.Surface((bar_w, h), pygame.SRCALPHA)
            pygame.draw.rect(bar, (*accent, 230), (0, 0, bar_w, h),
                             border_top_left_radius=radius,
                             border_bottom_left_radius=radius)
            surface.blit(bar, (px, py))

        # 边框
        border = (94, 234, 212) if self.is_selected else (96, 64, 168)
        pygame.draw.rect(surface, border, (px, py, w, h),
                         2 if self.is_selected else 1, border_radius=radius)

        # ── Plain text (auto-fit) ─────────────────────────────────────────
        margin = 6
        text_pad_l = margin + max(2, int(3 * zoom)) + 2   # 让出左侧强调条
        avail_w = w - text_pad_l - margin
        avail_h = h - margin * 2
        min_fs = 6

        # Build wrapped lines for a given font size, return (lines, total_w, total_h)
        def _layout(layout_fs):
            fnt = get_element_font(layout_fs)
            line_h = layout_fs + 4
            char_w, _ = fnt.size('字')
            if char_w < 1:
                char_w = layout_fs
            max_chars = max(1, avail_w // char_w)
            lines = []
            for ch in self.text:
                if ch == '\n':
                    lines.append('')
                    continue
                if not lines or len(lines[-1]) >= max_chars:
                    lines.append('')
                lines[-1] += ch
            if not lines:
                lines = ['']
            max_line_w = max(fnt.size(l)[0] for l in lines)
            total_h = len(lines) * line_h
            return lines, max_line_w, total_h, fnt

        for try_fs in range(max(min_fs, int(self.font_size * zoom)), min_fs - 1, -1):
            lines, max_w, total_h, fnt = _layout(try_fs)
            if max_w <= avail_w and total_h <= avail_h:
                break

        text_x = px + text_pad_l
        text_y = py + margin
        for i in range(len(lines)):
            ts = fnt.render(lines[i], True, self.color)
            surface.blit(ts, (text_x, text_y + i * (try_fs + 4)))

    def check_click(self, mouse_screen_pos, camera, screen_size):
        sw, sh = screen_size
        sx, sy = world_to_screen(self.x, self.y, camera, sw, sh)
        zoom = camera['zoom']
        w = max(1, int(self.box_width * zoom) // 2)
        h = max(1, int(self.box_height * zoom) // 2)
        mx, my = mouse_screen_pos
        return abs(mx - sx) <= w and abs(my - sy) <= h

    def get_info(self):
        return f"文本框: {self.text[:20]}"


def _frange(start, stop, step):
    """Float range helper."""
    vals = []
    v = start
    while v <= stop:
        vals.append(v)
        v += step
    return vals
