"""
AC steady-state phasor solver (Complex MNA).

Element → admittance mapping (at angular frequency ω = 2πf):
  Resistor:   Y = 1/R
  Capacitor:  Y = jωC      (C in Farads)
  Inductor:   Y = -j/(ωL)  (L in Henrys)
  Voltage source:  phasor V = V_RMS ∠0°  (stamped via MNA auxiliary equation)
  Current source:  phasor I = I_RMS ∠0°  (stamped into RHS)

All voltages/currents returned as complex phasors.
Display value = abs(phasor) gives RMS magnitude.
"""

import math
import numpy as np
from elements import ActiveElement, Wire, Resistor, Capacitor, Inductor, Power, Ammeter, Voltmeter, Solenoid

# Reuse the topology-building helpers from circuit.py
SNAP_THRESHOLD = 15
GND_R = 1e7  # bleed resistor to ground (used but less critical in AC)


def solve_ac(elements, frequency=50.0):
    """Solve circuit in AC steady state using complex MNA.

    Parameters
    ----------
    elements : list of Element
        Circuit topology.
    frequency : float
        AC frequency in Hz.

    Returns
    -------
    currents : dict
        Element → complex phasor current (RMS).
    node_voltages : dict
        Node index → complex phasor voltage (RMS).
    errors : list[str]
        Detected errors.
    """
    omega = 2.0 * math.pi * frequency

    # ── 1. Collect terminals ─────────────────────────────────────────
    terminals = []
    for e in elements:
        if isinstance(e, Wire):
            for i, pt in enumerate(e.points):
                terminals.append((pt[0], pt[1], e, i))
        elif isinstance(e, ActiveElement):
            a, b = e.get_connection_points()
            terminals.append((a[0], a[1], e, 0))
            terminals.append((b[0], b[1], e, 1))

    if len(terminals) < 2:
        return {}, {}, []

    # ── 2. Union-Find → circuit nodes ────────────────────────────────
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
            if math.hypot(xi - xj, yi - yj) < SNAP_THRESHOLD:
                union(i, j)

    root_to_node = {}
    term_node = [-1] * len(terminals)
    for i in range(len(terminals)):
        r = find(i)
        if r not in root_to_node:
            root_to_node[r] = len(root_to_node)
        term_node[i] = root_to_node[r]

    N = len(root_to_node)
    if N < 2:
        return {}, {}, []

    # ── 2.5 Error detection ──────────────────────────────────────────
    errors = []
    v_src_info = []
    for e in elements:
        if isinstance(e, Power) and e.ptype == 'V' and e.switched_on:
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            if len(tidxs) >= 2:
                v_src_info.append((e, term_node[tidxs[0]], term_node[tidxs[1]]))

    for elem, ni, nj in v_src_info:
        if ni == nj:
            errors.append(f"短路: 电源({elem.id}) 两端直接通过导线连接")

    # ground = node with most terminal connections
    degree = [0] * N
    for n in term_node:
        degree[n] += 1
    gnd = max(range(N), key=lambda i: degree[i])

    def vidx(node):
        if node == gnd:
            return -1
        return node if node < gnd else node - 1

    # ── 3. Build complex admittance branches ─────────────────────────
    # Y_branch entries: (ni, nj, Y_complex, I_src_complex, element)
    branches = []   # passive + current source branches
    v_srcs = []     # (ni_pos, nj_neg, V_complex, element)

    for e in elements:
        if isinstance(e, Wire):
            pts = e.points
            n_seg = len(pts) - 1
            if n_seg < 1:
                continue
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            for si in range(n_seg):
                ni = term_node[tidxs[si]]
                nj = term_node[tidxs[si + 1]]
                if ni == nj:
                    continue
                Rseg = 0.01 / n_seg  # same as WIRE_R
                branches.append((ni, nj, 1.0 / Rseg + 0j, 0j, e, si))

        elif isinstance(e, ActiveElement):
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            if len(tidxs) < 2:
                continue
            ni = term_node[tidxs[0]]
            nj = term_node[tidxs[1]]
            if ni == nj:
                continue

            if isinstance(e, Resistor):
                branches.append((ni, nj, 1.0 / e.resistance + 0j, 0j, e, 0))

            elif isinstance(e, Capacitor):
                C = e.capacitance * 1e-6       # μF → F
                Y = 1j * omega * C              # jωC
                branches.append((ni, nj, Y, 0j, e, 0))

            elif isinstance(e, Inductor):
                L = e.inductance * 1e-3         # mH → H
                Y = -1j / (omega * L) if L > 0 else 1e3 + 0j  # -j/(ωL)
                branches.append((ni, nj, Y, 0j, e, 0))

            elif isinstance(e, Solenoid):
                # AC: Z = R + jωL  (series RL)
                L_si = e.get_inductance()        # H
                R = e.resistance                 # Ω
                Z = R + 1j * omega * L_si
                Y = 1.0 / Z if abs(Z) > 1e-15 else 1e3 + 0j
                branches.append((ni, nj, Y, 0j, e, 0))

            elif isinstance(e, Ammeter):
                # Ammeter = near-zero impedance = very large admittance
                branches.append((ni, nj, 1.0 / Ammeter.R_METER + 0j, 0j, e, 0))

            elif isinstance(e, Voltmeter):
                # Voltmeter = very high impedance = tiny admittance
                branches.append((ni, nj, 1.0 / Voltmeter.R_METER + 0j, 0j, e, 0))

            elif isinstance(e, Power):
                if not e.switched_on:
                    continue
                if e.ptype == 'V':
                    # Phasor voltage = V_RMS ∠0° (user value = RMS)
                    V = e.value + 0j
                    v_srcs.append((ni, nj, V, e))
                else:
                    # Phasor current = I_RMS ∠0°
                    I = e.value + 0j
                    branches.append((ni, nj, 0j, I, e, 0))

    if not branches and not v_srcs:
        return {}, {}, errors

    # ── 4. Build complex MNA matrix ──────────────────────────────────
    M = len(v_srcs)
    n_eq = (N - 1) + M
    if n_eq == 0:
        return {}, {}, errors

    A = np.zeros((n_eq, n_eq), dtype=np.complex128)
    b = np.zeros(n_eq, dtype=np.complex128)

    # Passive/current-source branches
    for ni, nj, Y, Is, _, _ in branches:
        # Current source contribution to RHS
        if abs(Is) > 1e-15:
            vi, vj = vidx(ni), vidx(nj)
            if vi >= 0:
                b[vi] -= Is
            if vj >= 0:
                b[vj] += Is

        # Admittance stamp
        if abs(Y) < 1e-15:
            continue
        vi, vj = vidx(ni), vidx(nj)
        if vi >= 0:
            A[vi, vi] += Y
        if vj >= 0:
            A[vj, vj] += Y
        if vi >= 0 and vj >= 0:
            A[vi, vj] -= Y
            A[vj, vi] -= Y

    # Bleed resistors (purely real, helps conditioning for floating nodes)
    for node in range(N):
        if node == gnd:
            continue
        vi = vidx(node)
        A[vi, vi] += 1.0 / GND_R + 0j

    # Voltage source stamps
    for idx, (ni, nj, V, _) in enumerate(v_srcs):
        eq = (N - 1) + idx
        col = eq
        vi, vj = vidx(ni), vidx(nj)
        if vi >= 0:
            A[vi, col] = 1.0 + 0j
        if vj >= 0:
            A[vj, col] = -1.0 + 0j
        if vi >= 0:
            A[eq, vi] = 1.0 + 0j
        if vj >= 0:
            A[eq, vj] = -1.0 + 0j
        b[eq] = V

    # ── 5. Solve ─────────────────────────────────────────────────────
    try:
        x = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        errors.append("AC求解失败: 矩阵奇异")
        return {}, {}, errors

    # ── 6. Extract results ───────────────────────────────────────────
    node_V = {gnd: 0j}
    for node in range(N):
        if node != gnd:
            node_V[node] = x[vidx(node)]

    vsrc_I = {}
    for idx, (_, _, _, elem) in enumerate(v_srcs):
        vsrc_I[elem] = x[(N - 1) + idx]

    seg_currents = {}
    for ni, nj, Y, Is, elem, seg_idx in branches:
        Vi, Vj = node_V.get(ni, 0j), node_V.get(nj, 0j)
        I = Y * (Vi - Vj) + Is
        seg_currents.setdefault(elem, []).append(I)

    currents = {}
    for elem, Is in seg_currents.items():
        currents[elem] = Is[0] if Is else 0j
    for elem, I in vsrc_I.items():
        currents[elem] = I

    return currents, node_V, errors
