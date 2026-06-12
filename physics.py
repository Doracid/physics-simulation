import math
import pygame

# ── Real physical constants (SI units with pixel↔meter conversion) ──
K_COULOMB = 8.9875517923e9   # 1/(4πε₀) in N·m²/C²
PX_PER_METER = 200            # how many pixels represent 1 metre

# Plummer softening — prevents singularities at point charges
# 15 px = 0.075 m at 200 px/m scale
EPSILON_SOFT = 0.075

# Magnetic constants
MU_0_4PI = 1e-7              # μ₀/(4π) in T·m/A  (wire B-field)
MAGNET_K = 2e4               # visual-scale magnet constant (kept for display)


class FieldSystem:
    """Handles field computation and field-line tracing."""

    def __init__(self):
        self.e_lines = []
        self.b_lines = []
        self.dirty = True
        self._last_cam = None  # (cx, cy, zoom) at last generation
        self.field_density = 1.0

    def mark_dirty(self):
        self.dirty = True

    def _cam_changed(self, camera):
        """Return True if camera moved enough to need field regeneration."""
        if self._last_cam is None:
            return True
        cx1, cy1, z1 = self._last_cam
        cx2, cy2, z2 = camera['x'], camera['y'], camera['zoom']
        # Regenerate if zoom changed by >10% or pan by >30% of visible width
        if abs(z2 - z1) / max(z1, 0.01) > 0.1:
            return True
        # Pan threshold in world coords (30% of visible half-width at current zoom)
        vis_w = 640 / z1  # half screen width in world
        vis_h = 360 / z1
        if abs(cx2 - cx1) > vis_w * 0.3 or abs(cy2 - cy1) > vis_h * 0.3:
            return True
        return False

    # ── field computation ──────────────────────────────────────────

    @staticmethod
    def _coulomb_factor(q, dx, dy, eps=1.0):
        """Compute E-field multiplier f = k·q·PX_PER_METER² / (ε·r³)

        Returns f so that Ex = f·dx, Ey = f·dy  (E-field in N/C).
        dx, dy are pixel offsets, eps is the local relative permittivity.
        """
        eps_px = EPSILON_SOFT * PX_PER_METER
        r2 = dx*dx + dy*dy + eps_px*eps_px
        r = math.sqrt(r2)
        return K_COULOMB * q * PX_PER_METER**2 / (eps * r2 * r)

    @staticmethod
    def _same_side(x, y, plate, sx, sy):
        """True if (x, y) and (sx, sy) are on the same side of *plate*."""
        nx, ny = math.sin(plate.angle), -math.cos(plate.angle)
        d_eval = (x - plate.x) * nx + (y - plate.y) * ny
        d_src  = (sx - plate.x) * nx + (sy - plate.y) * ny
        return d_eval * d_src >= 0

    def _total_efield(self, x, y, elements, exclude=None, images=None,
                      charge_elems=None, shells=None, metal_balls=None, plates=None):
        """Total E-field at (x, y) — real charges + conductor image charges.

        Parameters
        ----------
        images : tuple or None
            Pre-computed image charges from :meth:`_compute_image_charges`.
            When *None* they are computed fresh (slower but always correct).
        charge_elems, shells, metal_balls, plates : list or None
            Pre-filtered element lists for faster inner loops.
        """
        Ex = Ey = 0.0

        # ── RectEfield uniform in-plane field regions (smooth boundary, rotatable) ──
        for e in elements:
            if e.__class__.__name__ == 'RectEfield':
                hw = e.width / 2
                hh = e.height / 2
                # Transform to local coordinates
                dx = x - e.x
                dy = y - e.y
                cos_a = math.cos(e.angle)
                sin_a = math.sin(e.angle)
                lx = dx * cos_a + dy * sin_a
                ly = -dx * sin_a + dy * cos_a
                # y-direction in local coords: hard boundary
                if not (-hh <= ly <= hh):
                    continue
                # x-direction: smooth transition over ~3 px
                adx = abs(lx)
                if adx < hw:
                    weight = 1.0
                elif adx < hw + 3.0:
                    t = (adx - hw) / 3.0  # 0→1
                    weight = 1.0 - t * t * (3.0 - 2.0 * t)  # smoothstep 1→0
                else:
                    continue
                Ex += e.E_mag * e.direction * cos_a * weight
                Ey += e.E_mag * e.direction * sin_a * weight

        if images is None:
            images = self._compute_image_charges(elements)
        ball_images, plate_images_with_src, shell_inner_images, shell_out_images = images

        # ── Real charges with side-filtering and Faraday shielding ──
        if charge_elems is None:
            charge_elems = [e for e in elements
                           if e.__class__.__name__ in ('Charge', 'MotionCharge')]
        if shells is None:
            shells = [e for e in elements if e.__class__.__name__ == 'MetalShell']
        if metal_balls is None:
            metal_balls = [e for e in elements if e.__class__.__name__ == 'MetalBall']
        if plates is None:
            plates = [e for e in elements if e.__class__.__name__ == 'MetalPlate']

        for e in charge_elems:
            if e is exclude:
                continue
            skip = False
            for _, _, _, plate, src in plate_images_with_src:
                if src is e and not self._same_side(x, y, plate, e.x, e.y):
                    skip = True
                    break
            if not skip:
                for cond in shells:
                    d_eval = math.hypot(x - cond.x, y - cond.y)
                    d_chg = math.hypot(e.x - cond.x, e.y - cond.y)
                    if d_eval < cond.r_inner and d_chg > cond.r_outer:
                        skip = True
                        break
                    if d_eval > cond.r_outer and d_chg < cond.r_inner:
                        skip = True
                        break
            if skip:
                continue
            dx = x - e.x
            dy = y - e.y
            f = self._coulomb_factor(e.q, dx, dy, 1.0)
            Ex += f * dx
            Ey += f * dy

        # ── MetalBall images ──
        for ix, iy, iq in ball_images:
            dx = x - ix
            dy = y - iy
            f = self._coulomb_factor(iq, dx, dy, 1.0)
            Ex += f * dx
            Ey += f * dy

        # ── MetalShell inner images ──
        for ix, iy, iq, cx, cy, r_in, r_out in shell_inner_images:
            d = math.hypot(x - cx, y - cy)
            if ix == cx and iy == cy:
                if d <= r_out:
                    continue
            else:
                if d >= r_in:
                    continue
            dx = x - ix
            dy = y - iy
            f = self._coulomb_factor(iq, dx, dy, 1.0)
            Ex += f * dx
            Ey += f * dy

        # ── MetalShell external images ──
        for ix, iy, iq, cx, cy, r_in, r_out in shell_out_images:
            d = math.hypot(x - cx, y - cy)
            if d < r_out:
                continue
            dx = x - ix
            dy = y - iy
            f = self._coulomb_factor(iq, dx, dy, 1.0)
            Ex += f * dx
            Ey += f * dy

        # ── MetalPlate images ──
        for ix, iy, iq, plate, src in plate_images_with_src:
            if not self._same_side(x, y, plate, src.x, src.y):
                continue
            dx = x - ix
            dy = y - iy
            f = self._coulomb_factor(iq, dx, dy, 1.0)
            Ex += f * dx
            Ey += f * dy

        # Inside a conductor → E = 0 at electrostatic equilibrium
        for e in (metal_balls or []):
            if math.hypot(x - e.x, y - e.y) < e.r_outer:
                return 0.0, 0.0
        for e in (shells or []):
            d = math.hypot(x - e.x, y - e.y)
            if e.r_inner < d < e.r_outer:
                return 0.0, 0.0
        for e in (plates or []):
            nx, ny = math.sin(e.angle), -math.cos(e.angle)
            sd = (x - e.x) * nx + (y - e.y) * ny
            if abs(sd) < e.thickness / 2:
                return 0.0, 0.0

        return Ex, Ey

    def _efield(self, x, y, elements, exclude=None):
        """Alias kept for backward compatibility — delegates to _total_efield."""
        return self._total_efield(x, y, elements, exclude=exclude)

    @staticmethod
    def _get_solenoid_poles(e):
        """Return ((nx,ny), (sx,sy)) for a Solenoid's N/S poles.
        Polarity determined by current direction AND winding direction (right-hand rule).
        N pole is at the end where curled fingers of the right hand (winding direction)
        point in the direction of current flow, with thumb pointing to N."""
        cos_a = math.cos(e.angle)
        sin_a = math.sin(e.angle)
        hl = e.coil_length / 2
        # Right-hand rule: N on right side when (current>=0) XOR (winding_clockwise)
        n_on_right = (e.current >= 0) != e.winding_clockwise
        sign = 1 if n_on_right else -1
        nx = e.x + sign * hl * cos_a
        ny = e.y + sign * hl * sin_a
        sx = e.x - sign * hl * cos_a
        sy = e.y - sign * hl * sin_a
        return (nx, ny), (sx, sy)

    def _bfield(self, x, y, elements, magnet_elems=None, solenoid_elems=None):
        Bx = By = 0.0
        mags = magnet_elems or [e for e in elements
                                if e.__class__.__name__ in ('Magnet', 'HorseshoeMagnet')]
        for e in mags:
            if e.__class__.__name__ == 'Magnet':
                cos_a = math.cos(e.angle)
                sin_a = math.sin(e.angle)
                hl = e.length / 2
                nx = e.x - hl * cos_a
                ny = e.y - hl * sin_a
                sx = e.x + hl * cos_a
                sy = e.y + hl * sin_a
            else:
                (nx, ny), (sx, sy) = e.get_pole_positions()
            # N pole — repulsive
            dx = x - nx
            dy = y - ny
            r = math.hypot(dx, dy) + EPSILON_SOFT
            f = MAGNET_K * e.strength / (r * r * r)
            Bx += f * dx
            By += f * dy
            # S pole — attractive
            dx = x - sx
            dy = y - sy
            r = math.hypot(dx, dy) + EPSILON_SOFT
            f = -MAGNET_K * e.strength / (r * r * r)
            Bx += f * dx
            By += f * dy

        # ── Solenoids (multi-dipole model ≈ Biot–Savart finite solenoid) ──
        sols = solenoid_elems or [e for e in elements
                                   if e.__class__.__name__ == 'Solenoid']
        for e in sols:
            if abs(e.current) < 1e-10:
                continue
            cos_a = math.cos(e.angle)
            sin_a = math.sin(e.angle)
            hl = e.coil_length / 2
            # N/S orientation from right-hand rule
            n_on_right = (e.current >= 0) != e.winding_clockwise
            sign = 1 if n_on_right else -1
            # Distribute N_DIPOLES virtual magnetic dipoles along the axis.
            # Each dipole uses the exact dipole-field formula:
            #   B = μ₀/(4π)·[3(m·r̂)r̂ − m]/r³
            # The superposition of evenly-spaced dipoles gives the correct
            # internal (≈uniform, S→N) and external (dipole-like) field.
            N_DIPOLES = 15
            m_mag = e.turns * abs(e.current) * 0.5  # visual-scale dipole moment
            for i in range(N_DIPOLES):
                t = (i + 0.5) / N_DIPOLES * 2 - 1  # −1 … +1
                z = t * hl
                di_x = e.x + z * cos_a
                di_y = e.y + z * sin_a
                dx = x - di_x
                dy = y - di_y
                r = math.hypot(dx, dy) + EPSILON_SOFT
                m_i = m_mag / N_DIPOLES
                mx = sign * m_i * cos_a
                my = sign * m_i * sin_a
                r_hat_x = dx / r
                r_hat_y = dy / r
                m_dot_r = mx * r_hat_x + my * r_hat_y
                factor = MAGNET_K / (r * r * r)
                Bx += factor * (3 * m_dot_r * r_hat_x - mx)
                By += factor * (3 * m_dot_r * r_hat_y - my)
        return Bx, By

    # ── wire B-field (Biot–Savart) ────────────────────────────────

    def _segment_bfield(self, px, py, x1, y1, x2, y2, current):
        """Scalar B-field (perpendicular to screen) at (px,py) from a
        current-carrying segment (x1,y1)–(x2,y2).  Positive = ⊙ (out),
        negative = ⊗ (into screen).  Returns Tesla."""
        sx, sy = x2 - x1, y2 - y1
        seg_len = math.hypot(sx, sy)
        if seg_len < 1e-10:
            return 0.0

        # Vectors from P to segment endpoints
        r1x, r1y = px - x1, py - y1
        r2x, r2y = px - x2, py - y2
        r1 = math.hypot(r1x, r1y)
        r2 = math.hypot(r2x, r2y)
        eps_px = EPSILON_SOFT * PX_PER_METER
        if r1 < eps_px or r2 < eps_px:
            return 0.0

        # Perpendicular distance  (|r1 × unit_segment|)
        d = abs(r1x * sy - r1y * sx) / seg_len + eps_px

        # cos of angles between segment and endpoint vectors
        cos_a1 = (r1x * sx + r1y * sy) / (r1 * seg_len)
        cos_a2 = (r2x * sx + r2y * sy) / (r2 * seg_len)

        # Sign from right-hand rule (cross product at segment midpoint)
        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        sign = 1 if (sx * (py - my) - sy * (px - mx)) > 0 else -1

        # B = μ₀/(4π) · I · (cosθ₁ − cosθ₂) / d   — d must be in metres
        return sign * MU_0_4PI * current * PX_PER_METER * (cos_a1 - cos_a2) / d

    def _wire_bfield_at(self, x, y, elements, wire_elems=None, resistor_elems=None):
        """Total scalar B at (x,y) from all wire segments and current-carrying components."""
        B = 0.0
        wires = wire_elems or [e for e in elements if e.__class__.__name__ == 'Wire']
        for e in wires:
            if abs(e.current) < 1e-10:
                continue
            pts = e.points
            for i in range(len(pts) - 1):
                B += self._segment_bfield(x, y, pts[i][0], pts[i][1],
                                          pts[i+1][0], pts[i+1][1], e.current)
        resistors = resistor_elems or [e for e in elements if e.__class__.__name__ == 'Resistor']
        for e in resistors:
            if abs(e.current) < 1e-10:
                continue
            p1, p2 = e.get_connection_points()
            B += self._segment_bfield(x, y, p1[0], p1[1], p2[0], p2[1], e.current)
        return B

    @staticmethod
    def _solenoid_bfield_biotsavart(e, x, y):
        """B-field at (x,y) from solenoid using 3D Biot-Savart numerical integration.

        Models each turn as a circular loop in 3D (the plane perpendicular to
        the solenoid axis). Returns (Bx, By, Bz) in Tesla — physically accurate
        for measurement display (unlike the visual-scale multi-dipole model).
        """
        if abs(e.current) < 1e-10:
            return 0.0, 0.0, 0.0

        cos_a = math.cos(e.angle)
        sin_a = math.sin(e.angle)
        perp_x, perp_y = -sin_a, cos_a  # in-plane perpendicular to axis
        n_on_right = (e.current >= 0) != e.winding_clockwise
        current_sign = 1 if n_on_right else -1
        I = e.current * current_sign

        R = e.coil_radius
        hl = e.coil_length / 2
        # Limit turns for performance (cap at 200, or use actual turns)
        N_turns = min(int(e.turns), 200)
        n_az = 16  # azimuthal segments per turn
        eps_px = EPSILON_SOFT * PX_PER_METER

        Bx = By = Bz = 0.0
        for ti in range(N_turns):
            z_ax = -hl + (ti + 0.5) * e.coil_length / N_turns
            cx = e.x + z_ax * cos_a
            cy = e.y + z_ax * sin_a

            for ai in range(n_az):
                phi = 2 * math.pi * ai / n_az
                phi1 = 2 * math.pi * (ai + 1) / n_az
                dphi = phi1 - phi

                # Current element position on the 3D loop
                ex = cx + R * math.cos(phi) * perp_x
                ey = cy + R * math.cos(phi) * perp_y
                ez = R * math.sin(phi)

                # Tangent vector dl (d/dphi of position × dphi)
                dlx = -R * math.sin(phi) * perp_x * dphi
                dly = -R * math.sin(phi) * perp_y * dphi
                dlz = R * math.cos(phi) * dphi

                # Vector from element to observation point (z=0 on screen)
                rx = x - ex
                ry = y - ey
                rz = 0.0 - ez
                r = math.hypot(rx, ry, rz) + eps_px

                # dB = μ₀/(4π) · I · (dl × r̂) / r²
                # dl × r = (dly*rz − dlz*ry, dlz*rx − dlx*rz, dlx*ry − dly*rx)
                cross_x = dly * rz - dlz * ry
                cross_y = dlz * rx - dlx * rz
                cross_z = dlx * ry - dly * rx

                # r is in pixels; convert dB to Tesla using
                #   dB = MU_0_4PI * I * (dl_m × r̂) / r_m²
                # where dl_m = dl/PX_PER_METER, r_m = r/PX_PER_METER
                # → dB = MU_0_4PI * I * (dl × r) * PX_PER_METER / r³
                factor = MU_0_4PI * I * PX_PER_METER / (r * r * r)
                Bx += factor * cross_x
                By += factor * cross_y
                Bz += factor * cross_z

        return Bx, By, Bz

    # ── public field accessors ──────────────────────────────────────

    def _potential(self, x, y, elements, exclude=None, images=None,
                   charge_elems=None, shells=None, metal_balls=None, plates=None,
                   _skip_same_side=False):
        """Electric potential V at (x,y): V = Σ k·q / r  (scalar, V).

        Includes image charges for conductors so the surface is an equipotential.
        """
        V = 0.0

        # ── RectEfield uniform in-plane field potential (continuous) ──
        for e in elements:
            if e.__class__.__name__ == 'RectEfield':
                hw = e.width / 2
                hh = e.height / 2
                if (e.y - hh <= y <= e.y + hh):
                    # V = -E * clamp(x - x0, -hw, +hw) — continuous outside boundary
                    dx = max(-hw, min(hw, x - e.x))
                    V -= e.E_mag * e.direction * dx / PX_PER_METER

        if images is None:
            images = self._compute_image_charges(elements)
        ball_images, plate_images_with_src, shell_inner_images, shell_out_images = images
        if charge_elems is None:
            charge_elems = [e for e in elements
                           if e.__class__.__name__ in ('Charge', 'MotionCharge')]
        if shells is None:
            shells = [e for e in elements if e.__class__.__name__ == 'MetalShell']
        if metal_balls is None:
            metal_balls = [e for e in elements if e.__class__.__name__ == 'MetalBall']
        if plates is None:
            plates = [e for e in elements if e.__class__.__name__ == 'MetalPlate']

        def add_q(q, px, py):
            dx = x - px
            dy = y - py
            r = math.hypot(dx, dy) / PX_PER_METER
            if r > 1e-10:
                return K_COULOMB * q / r
            return 0.0

        # Real charges (with shell shielding + plate side-filtering)
        for e in charge_elems:
            if e is exclude:
                continue
            skip = False
            for _, _, _, plate, src in plate_images_with_src:
                if src is e and not self._same_side(x, y, plate, e.x, e.y):
                    skip = True
                    break
            if skip:
                continue
            for cond in shells:
                d_eval = math.hypot(x - cond.x, y - cond.y)
                d_chg = math.hypot(e.x - cond.x, e.y - cond.y)
                if d_eval < cond.r_inner and d_chg > cond.r_outer:
                    skip = True
                    break
                if d_eval > cond.r_outer and d_chg < cond.r_inner:
                    skip = True
                    break
            if skip:
                continue
            V += add_q(e.q, e.x, e.y)

        # Image charges
        for ix, iy, iq in ball_images:
            V += add_q(iq, ix, iy)
        for ix, iy, iq, cx, cy, r_in, r_out in shell_inner_images:
            d = math.hypot(x - cx, y - cy)
            if ix == cx and iy == cy:
                if d <= r_out:
                    continue
            else:
                if d >= r_in:
                    continue
            V += add_q(iq, ix, iy)
        for ix, iy, iq, cx, cy, r_in, r_out in shell_out_images:
            d = math.hypot(x - cx, y - cy)
            if d < r_out:
                continue
            V += add_q(iq, ix, iy)
        for ix, iy, iq, plate, src in plate_images_with_src:
            if not _skip_same_side and not self._same_side(x, y, plate, src.x, src.y):
                continue
            V += add_q(iq, ix, iy)

        # If inside a conductor, potential is constant = value at the surface.
        # For spheres: project outward to the nearest surface point.
        _EPS = 1e-3  # floating-point tolerance to avoid re-projection recursion
        for e in (metal_balls or []):
            d = math.hypot(x - e.x, y - e.y)
            if d < e.r_outer - _EPS:
                # Move to the surface along the radial direction
                if d > 1:
                    scale = e.r_outer / d
                    sx = e.x + (x - e.x) * scale
                    sy = e.y + (y - e.y) * scale
                else:
                    sx, sy = e.x + e.r_outer, e.y
                return self._potential(sx, sy, elements, exclude, images,
                                      charge_elems, shells, metal_balls, plates)
        for e in (shells or []):
            d = math.hypot(x - e.x, y - e.y)
            # Compute V_shell constant for this shell
            V_shell = 0.0
            for chg in charge_elems:
                if chg is exclude:
                    continue
                dc = math.hypot(chg.x - e.x, chg.y - e.y)
                if dc < e.r_inner:
                    r_m = e.r_outer / PX_PER_METER
                elif dc > e.r_outer:
                    r_m = dc / PX_PER_METER
                else:
                    continue
                if r_m > 1e-10:
                    V_shell += K_COULOMB * chg.q / r_m
            # Conductor wall: V = V_shell (constant)
            if e.r_inner + _EPS < d < e.r_outer - _EPS:
                return V_shell
            # Cavity: if no charge inside → V = V_shell
            if d < e.r_inner - _EPS:
                has_inner = False
                for chg in charge_elems:
                    if chg is exclude:
                        continue
                    if math.hypot(chg.x - e.x, chg.y - e.y) < e.r_inner:
                        has_inner = True
                        break
                if not has_inner:
                    return V_shell
        for e in (plates or []):
            cos_a = math.cos(e.angle)
            sin_a = math.sin(e.angle)
            nx, ny = sin_a, -cos_a
            dx, dy = x - e.x, y - e.y
            sd = dx * nx + dy * ny
            d = abs(sd)
            if d < e.thickness / 2 + _EPS:
                # 无限大导体平面模型: V=0 (电容无穷大)
                return 0.0

        return V

    def get_efield(self, x, y, elements, exclude=None):
        """Return (Ex, Ey) at (x, y) from all charges."""
        return self._efield(x, y, elements, exclude)

    def get_potential(self, x, y, elements, exclude=None):
        """Return electric potential V at (x, y) from all charges + images."""
        return self._potential(x, y, elements, exclude)

    def get_wire_bfield(self, x, y, elements):
        """Return scalar Bz at (x, y) from wires + bounded field regions."""
        return self._wire_bfield_at(x, y, elements) + self._bounded_bfield_bz(x, y, elements)

    def get_total_bfield(self, x, y, elements):
        """Return (Bx, By, Bz) at (x, y) from magnets, wires, and bounded field regions."""
        Bx, By = self._bfield(x, y, elements)
        Bz = self._wire_bfield_at(x, y, elements) + self._bounded_bfield_bz(x, y, elements)
        return Bx, By, Bz

    def _bounded_bfield_bz(self, x, y, elements):
        """Bz from RectField and CircField regions (uniform perpendicular B-field)."""
        B = 0.0
        for e in elements:
            cname = e.__class__.__name__
            if cname == 'RectField':
                hw = e.width / 2
                hh = e.height / 2
                if (e.x - hw <= x <= e.x + hw) and (e.y - hh <= y <= e.y + hh):
                    B += e.B_mag * e.direction
            elif cname == 'CircField':
                dx = x - e.x
                dy = y - e.y
                if dx*dx + dy*dy <= e.radius * e.radius:
                    B += e.B_mag * e.direction
        return B

    # ── wire B-field grid drawing ──────────────────────────────────

    # Scale factor for B-field grid display (Tesla → display units)
    _B_GRID_SCALE = 2e5

    def _draw_wire_bfield_grid(self, surface, camera, screen_size, elements,
                                wire_elems=None, resistor_elems=None):
        sw, sh = screen_size
        zoom = camera['zoom']
        cx, cy = camera['x'], camera['y']
        cam_angle = camera.get('angle', 0.0)
        cos_cam = math.cos(cam_angle)
        sin_cam = math.sin(cam_angle)
        step = 48  # screen pixels between grid points

        # Build cache key from camera state and element version
        wires = wire_elems or [e for e in elements if e.__class__.__name__ == 'Wire']
        resistors = resistor_elems or [e for e in elements if e.__class__.__name__ == 'Resistor']
        has = bool(wires or resistors)
        if not has:
            return

        # Canvas area offset
        ox, oy = 80, 36  # TOOLBAR_W, TOP_BAR_H (hardcoded to avoid cross-module dep)

        sx = ox + step // 2
        while sx < sw:
            sy = oy + step // 2
            while sy < sh:
                # Undo camera rotation when converting screen → world
                dx = (sx - sw / 2) / zoom
                dy = (sy - sh / 2) / zoom
                if cam_angle != 0.0:
                    dx, dy = dx * cos_cam + dy * sin_cam, -dx * sin_cam + dy * cos_cam
                wx = dx + cx
                wy = dy + cy
                B = self._wire_bfield_at(wx, wy, elements, wires, resistors)
                B_disp = B * self._B_GRID_SCALE
                if abs(B_disp) > 0.15:
                    self._draw_bsym(surface, int(sx), int(sy), B_disp)
                sy += step
            sx += step

    def _draw_bsym(self, surface, x, y, B):
        """Draw ⊙ (positive) or ⊗ (negative) symbol at screen (x,y)."""
        size = max(3, min(14, int(math.sqrt(abs(B)) * 3)))
        if B > 0:
            color = (60, 200, 255)
            pygame.draw.circle(surface, color, (x, y), size, 1)
            if size > 3:
                pygame.draw.circle(surface, color, (x, y), max(2, size // 3))
        else:
            color = (255, 160, 80)
            pygame.draw.circle(surface, color, (x, y), size, 1)
            if size > 3:
                d = size // 2
                pygame.draw.line(surface, color, (x - d, y - d), (x + d, y + d), 1)
                pygame.draw.line(surface, color, (x - d, y + d), (x + d, y - d), 1)

    # ── termination detection ──────────────────────────────────────

    def _at_terminus(self, x, y, elements, field_type, source_pos,
                     charge_elems=None, magnet_elems=None,
                     metal_balls=None, metal_shells=None, metal_plates=None):
        """True if (x, y) is inside an opposite-sign termination zone
        or at a conductor surface."""
        if field_type == 'e':
            charges = charge_elems or [e for e in elements
                                       if e.__class__.__name__ in ('Charge', 'MotionCharge')]
            for e in charges:
                if source_pos and math.hypot(e.x - source_pos[0], e.y - source_pos[1]) < 1:
                    continue
                if math.hypot(x - e.x, y - e.y) < e.radius + 8:
                    return True
            balls = metal_balls or [e for e in elements if e.__class__.__name__ == 'MetalBall']
            for e in balls:
                d = math.hypot(x - e.x, y - e.y)
                if abs(d - e.r_outer) < 6:
                    return True
            shells = metal_shells or [e for e in elements if e.__class__.__name__ == 'MetalShell']
            for e in shells:
                d = math.hypot(x - e.x, y - e.y)
                if abs(d - e.r_outer) < 6 or abs(d - e.r_inner) < 6:
                    return True
            plates = metal_plates or [e for e in elements if e.__class__.__name__ == 'MetalPlate']
            for e in plates:
                cos_a = math.cos(e.angle)
                sin_a = math.sin(e.angle)
                nx, ny = sin_a, -cos_a
                dx, dy = x - e.x, y - e.y
                d = dx * nx + dy * ny
                if abs(abs(d) - e.thickness / 2) < 6:
                    return True
        elif field_type == 'b':
            mags = magnet_elems or [e for e in elements
                                    if e.__class__.__name__ in ('Magnet', 'HorseshoeMagnet')]
            for e in mags:
                if e.__class__.__name__ == 'Magnet':
                    cos_a = math.cos(e.angle)
                    sin_a = math.sin(e.angle)
                    hl = e.length / 2
                    poles = [(e.x - hl * cos_a, e.y - hl * sin_a),
                             (e.x + hl * cos_a, e.y + hl * sin_a)]
                    pole_r = e.height // 4 + 6
                else:
                    poles = list(e.get_pole_positions())
                    pole_r = e.thickness + 6
                for px, py in poles:
                    if source_pos and math.hypot(px - source_pos[0], py - source_pos[1]) < 1:
                        continue
                    if math.hypot(x - px, y - py) < pole_r:
                        return True
            # ── Solenoid pole terminators ──
            for e in (elements or []):
                if e.__class__.__name__ != 'Solenoid':
                    continue
                if abs(e.current) < 1e-10:
                    continue
                (nx, ny), (sx, sy) = FieldSystem._get_solenoid_poles(e)
                pole_r = max(6, e.coil_radius // 3 + 4)
                for px, py in [(nx, ny), (sx, sy)]:
                    if source_pos and math.hypot(px - source_pos[0], py - source_pos[1]) < 1:
                        continue
                    if math.hypot(x - px, y - py) < pole_r:
                        return True
        return False

    # ── Image charges for conductors (Method of Images) ──────────────

    def _compute_image_charges(self, elements, charge_elems=None):
        """Compute virtual image charges for conductors.

        Returns (ball_images, plate_images_with_src, shell_inner_images,
                 shell_out_images).
        """
        ball_images = []
        plate_images_with_src = []
        shell_inner_images = []
        shell_out_images = []
        if charge_elems is None:
            charge_elems = [e for e in elements
                           if e.__class__.__name__ in ('Charge', 'MotionCharge')]

        for cond in elements:
            cname = cond.__class__.__name__
            if cname == 'MetalBall':
                cx, cy, R = cond.x, cond.y, cond.r_outer
                for src in charge_elems:
                    qx, qy, q = src.x, src.y, src.q
                    dx, dy = qx - cx, qy - cy
                    d = math.hypot(dx, dy)
                    if d < R + 2:
                        continue
                    q_img = -q * R / d
                    scale = R * R / (d * d)
                    ball_images.append((cx + scale * dx, cy + scale * dy, q_img))
                    ball_images.append((cx, cy, -q_img))

            elif cname == 'MetalShell':
                cx, cy = cond.x, cond.y
                r_out = cond.r_outer
                r_in = cond.r_inner
                for src in charge_elems:
                    qx, qy, q = src.x, src.y, src.q
                    dx, dy = qx - cx, qy - cy
                    d = math.hypot(dx, dy)

                    if d > r_out:
                        q_img = -q * r_out / d
                        scale = r_out * r_out / (d * d)
                        shell_out_images.append(
                            (cx + scale * dx, cy + scale * dy, q_img, cx, cy, r_in, r_out))
                        shell_out_images.append(
                            (cx, cy, -q_img, cx, cy, r_in, r_out))

                    elif d < r_in:
                        q_img = -q * r_in / d
                        scale = r_in * r_in / (d * d)
                        shell_inner_images.append(
                            (cx + scale * dx, cy + scale * dy, q_img, cx, cy, r_in, r_out))
                        shell_inner_images.append(
                            (cx, cy, q, cx, cy, r_in, r_out))

            elif cname == 'MetalPlate':
                nx, ny = math.sin(cond.angle), -math.cos(cond.angle)
                for src in charge_elems:
                    qx, qy, q = src.x, src.y, src.q
                    dx = qx - cond.x
                    dy = qy - cond.y
                    dist = dx * nx + dy * ny
                    if abs(dist) < cond.thickness / 2 + 1:
                        continue
                    plate_images_with_src.append((
                        qx - 2 * dist * nx, qy - 2 * dist * ny, -q, cond, src))

        return ball_images, plate_images_with_src, shell_inner_images, shell_out_images

    # ── RK2 field-line tracing ─────────────────────────────────────

    def _trace(self, start_x, start_y, field_func, step=8, max_steps=600,
               reverse=False, elements=None, field_type='e', source_pos=None,
               world_bound=5000, charge_elems=None, magnet_elems=None,
               metal_balls=None, metal_shells=None, metal_plates=None,
               skip_first_terminus=False):
        direction = -1.0 if reverse else 1.0
        pts = [(start_x, start_y)]
        x, y = start_x, start_y
        for i in range(max_steps):
            if elements and (i > 0 or not skip_first_terminus):
                if self._at_terminus(x, y, elements, field_type, source_pos,
                                     charge_elems, magnet_elems,
                                     metal_balls, metal_shells, metal_plates):
                    pts.append((x, y))
                    break
            Fx, Fy = field_func(x, y)
            m = math.hypot(Fx, Fy)
            if m < 1e-10:
                break
            k1x = direction * step * Fx / m
            k1y = direction * step * Fy / m
            Fx2, Fy2 = field_func(x + k1x / 2, y + k1y / 2)
            m2 = math.hypot(Fx2, Fy2)
            if m2 < 1e-10:
                break
            k2x = direction * step * Fx2 / m2
            k2y = direction * step * Fy2 / m2
            x += k2x
            y += k2y
            pts.append((x, y))
            if abs(x) > world_bound or abs(y) > world_bound:
                break
        return pts

    # ── generation ─────────────────────────────────────────────────

    def generate(self, elements, camera=None, screen_size=None):
        self.e_lines.clear()
        self.b_lines.clear()

        # ── Pre-filter element lists once for all tracing ────────────
        charge_elems = [e for e in elements
                       if e.__class__.__name__ in ('Charge', 'MotionCharge')]
        magnet_elems = [e for e in elements
                        if e.__class__.__name__ in ('Magnet', 'HorseshoeMagnet')]
        metal_balls = [e for e in elements if e.__class__.__name__ == 'MetalBall']
        metal_shells = [e for e in elements if e.__class__.__name__ == 'MetalShell']
        metal_plates = [e for e in elements if e.__class__.__name__ == 'MetalPlate']

        has_any_charge = bool(charge_elems)
        has_any_magnet = bool(magnet_elems)

        # Adaptive world bound — fill the screen at any zoom
        if camera and screen_size:
            vis_w = screen_size[0] / camera['zoom']
            vis_h = screen_size[1] / camera['zoom']
            wb = max(vis_w, vis_h) * 2.5
            mag_max_steps = int(wb / 8 * 1.5)
        else:
            wb = 5000
            mag_max_steps = 600

        if has_any_charge:
            # Compute image charges once for field-line tracing (static snapshot)
            images = self._compute_image_charges(elements, charge_elems)

            # Fast closure — no isinstance checks in the inner loop
            def efunc(x, y):
                return self._total_efield(x, y, elements, images=images,
                                          charge_elems=charge_elems,
                                          shells=metal_shells,
                                          metal_balls=metal_balls,
                                          plates=metal_plates)
            for e in charge_elems:
                n = max(2, int(max(4, min(14, int(abs(e.q * 1e6) * 6))) * self.field_density))
                for i in range(n):
                    a = 2 * math.pi * i / n
                    forward = e.q > 0
                    sr = e.radius + 1
                    sx = e.x + sr * math.cos(a)
                    sy = e.y + sr * math.sin(a)
                    pts = self._trace(sx, sy, efunc, reverse=not forward,
                                      elements=elements, field_type='e',
                                      source_pos=(e.x, e.y),
                                      world_bound=wb, max_steps=mag_max_steps,
                                      charge_elems=charge_elems,
                                      metal_balls=metal_balls,
                                      metal_shells=metal_shells,
                                      metal_plates=metal_plates)
                    if len(pts) > 1:
                        if not forward:
                            pts.reverse()
                        self.e_lines.append(pts)

            # ── MetalShell external seeding ───────────────────────────
            for cond in metal_shells:
                net_q = 0.0
                for src in charge_elems:
                    d = math.hypot(src.x - cond.x, src.y - cond.y)
                    if d < cond.r_inner:
                        net_q += src.q
                if abs(net_q) < 1e-9:
                    continue
                n = max(2, int(max(6, min(18, int(abs(net_q * 1e6) * 8))) * self.field_density))
                for i in range(n):
                    a = 2 * math.pi * i / n
                    forward = net_q > 0
                    sx = cond.x + (cond.r_outer + 6) * math.cos(a)
                    sy = cond.y + (cond.r_outer + 6) * math.sin(a)
                    fwd = self._trace(sx, sy, efunc, reverse=not forward,
                                      elements=elements, field_type='e',
                                      world_bound=wb, max_steps=mag_max_steps,
                                      charge_elems=charge_elems,
                                      metal_balls=metal_balls,
                                      metal_shells=metal_shells,
                                      metal_plates=metal_plates)
                    if len(fwd) > 1:
                        if not forward:
                            fwd.reverse()
                        self.e_lines.append(fwd)

        if has_any_magnet:
            # Fast bfield closure — uses pre-filtered magnet list
            def bfunc(x, y):
                return self._bfield(x, y, elements, magnet_elems)
            for e in magnet_elems:
                if e.__class__.__name__ == 'Magnet':
                    hl = e.length / 2
                    # Ring-seed around bar magnet center
                    ring_r = hl * 1.6
                    n_seeds = max(4, int(16 * self.field_density))
                    centers = [(e.x, e.y)]
                else:
                    # HorseshoeMagnet: seed around both poles
                    (nx, ny), (sx, sy) = e.get_pole_positions()
                    pole_r = min(e.gap, e.arm_length) * 0.6
                    n_seeds = max(4, int(10 * self.field_density))
                    centers = [(nx, ny), (sx, sy)]
                    ring_r = pole_r
                for cx, cy in centers:
                    for i in range(n_seeds):
                        theta = 2 * math.pi * i / n_seeds
                        sx = cx + ring_r * math.cos(theta)
                        sy = cy + ring_r * math.sin(theta)

                        fwd = self._trace(sx, sy, bfunc, step=8, max_steps=mag_max_steps,
                                          elements=elements, field_type='b',
                                          world_bound=wb,
                                          magnet_elems=magnet_elems)
                        rev = self._trace(sx, sy, bfunc, step=8, max_steps=mag_max_steps,
                                          reverse=True, elements=elements,
                                          field_type='b', world_bound=wb,
                                          magnet_elems=magnet_elems)

                        pts = []
                        if len(rev) > 1:
                            rev.reverse()
                            pts.extend(rev[:-1])
                        if len(fwd) > 1:
                            pts.extend(fwd)
                        elif len(rev) > 1:
                            pts = rev

                        if len(pts) > 1:
                            self.b_lines.append(pts)

        # ── Solenoid field-line seeding (bar-magnet ring seeding + internal lines) ──
        solenoid_elems = [e for e in elements
                          if e.__class__.__name__ == 'Solenoid']
        if solenoid_elems:
            def bfunc_sol(x, y):
                return self._bfield(x, y, elements, solenoid_elems=solenoid_elems)
            for e in solenoid_elems:
                if abs(e.current) < 1e-10:
                    continue
                hl = e.coil_length / 2
                ring_r = hl * 1.6
                n_seeds = max(4, int(16 * self.field_density))
                for i in range(n_seeds):
                    theta = 2 * math.pi * i / n_seeds
                    sx = e.x + ring_r * math.cos(theta)
                    sy = e.y + ring_r * math.sin(theta)
                    fwd = self._trace(sx, sy, bfunc_sol, step=8,
                                      max_steps=mag_max_steps,
                                      elements=elements, field_type='b',
                                      world_bound=wb)
                    rev = self._trace(sx, sy, bfunc_sol, step=8,
                                      max_steps=mag_max_steps,
                                      reverse=True, elements=elements,
                                      field_type='b', world_bound=wb)
                    pts = []
                    if len(rev) > 1:
                        rev.reverse()
                        pts.extend(rev[:-1])
                    if len(fwd) > 1:
                        pts.extend(fwd)
                    elif len(rev) > 1:
                        pts = rev
                    if len(pts) > 1:
                        self.b_lines.append(pts)

                # Internal straight S→N lines
                cos_a = math.cos(e.angle)
                sin_a = math.sin(e.angle)
                perp_x = -sin_a
                perp_y = cos_a
                n_on_right = (e.current >= 0) != e.winding_clockwise
                sign = 1 if n_on_right else -1
                nx = e.x + sign * hl * cos_a
                ny = e.y + sign * hl * sin_a
                sx = e.x - sign * hl * cos_a
                sy = e.y - sign * hl * sin_a
                for side in (-1, 1):
                    for level in range(3):
                        off = side * (level + 1) * e.coil_radius * 0.3
                        nx_off = nx + off * perp_x
                        ny_off = ny + off * perp_y
                        sx_off = sx + off * perp_x
                        sy_off = sy + off * perp_y
                        pts = [(sx_off + (nx_off - sx_off) * t / 5,
                                sy_off + (ny_off - sy_off) * t / 5) for t in range(6)]
                        self.b_lines.append(pts)

        self._last_cam = (camera['x'], camera['y'], camera['zoom']) if camera else None
        self.dirty = False

    # ── conductor check for clipping ──────────────────────────────

    def _inside_conductor(self, x, y, elements,
                          metal_balls=None, metal_shells=None, metal_plates=None):
        """True if (x, y) is inside a MetalBound (field lines hidden there)."""
        balls = metal_balls or [e for e in (elements or [])
                                if e.__class__.__name__ == 'MetalBall']
        for e in balls:
            if math.hypot(x - e.x, y - e.y) < e.r_outer:
                return True
        shells = metal_shells or [e for e in (elements or [])
                                  if e.__class__.__name__ == 'MetalShell']
        for e in shells:
            d = math.hypot(x - e.x, y - e.y)
            if e.r_inner < d < e.r_outer:
                return True
        plates = metal_plates or [e for e in (elements or [])
                                  if e.__class__.__name__ == 'MetalPlate']
        for e in plates:
            cos_a = math.cos(e.angle)
            sin_a = math.sin(e.angle)
            nx, ny = sin_a, -cos_a
            dx, dy = x - e.x, y - e.y
            d = abs(dx * nx + dy * ny)
            if d < e.thickness / 2:
                return True
        return False

    # ── drawing ────────────────────────────────────────────────────

    def draw(self, surface, camera, screen_size, show_e=True, show_b=True, elements=None):
        sw, sh = screen_size
        zoom = camera['zoom']
        cx, cy = camera['x'], camera['y']
        cam_angle = camera.get('angle', 0.0)
        cos_cam = math.cos(cam_angle)
        sin_cam = math.sin(cam_angle)

        # Pre-filter conductors once for all draw_line calls
        metal_balls = [e for e in (elements or [])
                       if e.__class__.__name__ == 'MetalBall']
        metal_shells = [e for e in (elements or [])
                        if e.__class__.__name__ == 'MetalShell']
        metal_plates = [e for e in (elements or [])
                        if e.__class__.__name__ == 'MetalPlate']

        def to_screen(wx, wy):
            dx = (wx - cx) * zoom
            dy = (wy - cy) * zoom
            if cam_angle != 0.0:
                dx, dy = dx * cos_cam - dy * sin_cam, dx * sin_cam + dy * cos_cam
            return int(dx + sw / 2), int(dy + sh / 2)

        def draw_line(pts, color):
            """Draw field line, skipping segments inside conductors."""
            if len(pts) < 2:
                return
            # Build visible screen-segment list
            segs = []
            prev_sp = None
            for i in range(len(pts)):
                inside = self._inside_conductor(pts[i][0], pts[i][1], elements,
                                                metal_balls, metal_shells, metal_plates)
                sp = to_screen(pts[i][0], pts[i][1])
                if not inside and prev_sp is not None:
                    segs.append((prev_sp, sp))
                prev_sp = sp

            for a, b in segs:
                pygame.draw.line(surface, color, a, b, 1)

            # Arrows on visible portions
            interval = max(1, len(pts) // 5)
            arrow_pts = []
            for i in range(len(pts)):
                if not self._inside_conductor(pts[i][0], pts[i][1], elements,
                                              metal_balls, metal_shells, metal_plates):
                    arrow_pts.append(i)
            if not arrow_pts:
                return
            draw_indices = set(range(interval, len(arrow_pts), interval))
            if not draw_indices:
                draw_indices.add(len(arrow_pts) // 2)
            for idx in sorted(draw_indices):
                if idx >= len(arrow_pts):
                    continue
                i = arrow_pts[idx]
                j = i + 1
                while j < len(pts) and self._inside_conductor(pts[j][0], pts[j][1], elements,
                                                              metal_balls, metal_shells, metal_plates):
                    j += 1
                if j >= len(pts):
                    continue
                p1, p2 = to_screen(pts[i][0], pts[i][1]), to_screen(pts[j][0], pts[j][1])
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math.hypot(dx, dy)
                if length < 2:
                    continue
                dx, dy = dx / length, dy / length
                px, py = -dy, dx
                sz = max(4, int(6 * zoom))
                tip = p2
                left  = (int(p2[0] - dx * sz + px * sz * 0.5),
                         int(p2[1] - dy * sz + py * sz * 0.5))
                right = (int(p2[0] - dx * sz - px * sz * 0.5),
                         int(p2[1] - dy * sz - py * sz * 0.5))
                pygame.draw.polygon(surface, color, (tip, left, right))

        if show_e:
            for line in self.e_lines:
                draw_line(line, (255, 180, 50))
        if show_b:
            for line in self.b_lines:
                draw_line(line, (80, 200, 255))
            if elements:
                wires = [e for e in elements if e.__class__.__name__ == 'Wire']
                resistors = [e for e in elements if e.__class__.__name__ == 'Resistor']
                if wires or resistors:
                    self._draw_wire_bfield_grid(surface, camera, screen_size, elements,
                                                 wires, resistors)

    # ── Faraday's law: induced E-field ──────────────────────────────

    def compute_induced_efield_grid(self, elements, camera, screen_size,
                                    prev_grid, faraday_time, dt):
        """Compute induced E field on a grid from oscillating magnet.

        Returns list of ((sx, sy), (Eix, Eiy), magnitude) for drawing.
        prev_grid is a dict (grid_key -> Bz_prev) updated in-place.
        """
        sw, sh = screen_size
        zoom = camera['zoom']
        cx, cy = camera['x'], camera['y']
        step = 56  # slightly wider grid (was 48)

        # Pre-filter magnets
        magnets = [e for e in elements if e.__class__.__name__ in ('Magnet', 'HorseshoeMagnet')]
        if not magnets:
            return []

        freq = 1.5
        omega = 2 * math.pi * freq

        arrows = []
        ox, oy = 80, 36
        cam_angle = camera.get('angle', 0.0)
        cos_cam = math.cos(cam_angle)
        sin_cam = math.sin(cam_angle)
        sx = ox + step // 2
        while sx < sw:
            sy = oy + step // 2
            while sy < sh:
                dx = (sx - sw / 2) / zoom
                dy = (sy - sh / 2) / zoom
                if cam_angle != 0.0:
                    dx, dy = dx * cos_cam + dy * sin_cam, -dx * sin_cam + dy * cos_cam
                wx = dx + cx
                wy = dy + cy

                total_dBz_dt = 0.0
                total_Ex = 0.0
                total_Ey = 0.0
                for magnet in magnets:
                    dx = wx - magnet.x
                    dy = wy - magnet.y
                    r2 = dx*dx + dy*dy + 25.0
                    r = math.sqrt(r2)

                    dBz_dt = omega * math.cos(omega * faraday_time) / r2
                    total_dBz_dt += dBz_dt

                    scale = 500.0
                    total_Ex += -dy / r * dBz_dt * scale
                    total_Ey += dx / r * dBz_dt * scale

                if abs(total_dBz_dt) < 0.001:
                    sy += step
                    continue

                mag = math.hypot(total_Ex, total_Ey)
                arrows.append(((sx, sy), (total_Ex, total_Ey), mag))
                sy += step
            sx += step

        return arrows

    @staticmethod
    def draw_induced_efield(surface, screen_size, arrows):
        """Draw bright induced E-field arrows with glow and tapered arrowhead."""
        for (sx, sy), (Eix, Eiy), mag in arrows:
            if mag < 0.5:
                continue
            length = math.hypot(Eix, Eiy)
            if length < 1e-6:
                continue
            nx, ny = Eix / length, Eiy / length
            arrow_len = min(28, max(10, int(mag * 3)))
            ex = int(sx + nx * arrow_len)
            ey = int(sy + ny * arrow_len)
            ix, iy = int(sx), int(sy)
            color = (255, 80, 255)

            # Glow
            for w, a in ((5, 25), (3, 55)):
                g = pygame.Surface((abs(ex-ix)+w*2+1, abs(ey-iy)+w*2+1), pygame.SRCALPHA)
                pygame.draw.line(g, (*color, a), (w, w), (abs(ex-ix)+w, abs(ey-iy)+w), w)
                surface.blit(g, (min(ix, ex)-w, min(iy, ey)-w))

            # Core line
            pygame.draw.line(surface, (255, 180, 255), (ix, iy), (ex, ey), 2)
            pygame.draw.line(surface, color, (ix, iy), (ex, ey), 1)

            # Arrowhead
            hl = max(6, arrow_len // 2)
            px, py = -ny, nx
            pts = [
                (ex, ey),
                (int(ex - nx*hl + px*hl*0.4), int(ey - ny*hl + py*hl*0.4)),
                (int(ex - nx*hl - px*hl*0.4), int(ey - ny*hl - py*hl*0.4)),
            ]
            pygame.draw.polygon(surface, (255, 180, 255), pts)
            pygame.draw.polygon(surface, color, pts, 1)
