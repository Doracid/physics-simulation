import math
import numpy as np

from elements import ActiveElement, Wire, Resistor, Capacitor, Inductor, Power, Ammeter, Voltmeter, Solenoid

SNAP_THRESHOLD = 15
WIRE_R = 0.01        # small resistance per wire (DC)
INDUCTOR_R = 0.01    # inductor = short in DC
CAP_R = 1e9          # capacitor = open in DC
GND_R = 1e7          # bleed resistor to ground for numerical stability


def solve_circuit(elements, dt=None, time=0.0, cap_voltages=None, ind_currents=None):
    """Solve circuit using Modified Nodal Analysis.

    When dt > 0, performs transient analysis:
    - Capacitors use companion model (G = C/dt, I_eq = G * V_prev)
    - Inductors use companion model (G = dt/L, I_eq = I_prev)
    - AC sources use time-varying value

    Returns (currents_dict, errors_list, cap_voltages, ind_currents).
    cap_voltages/ind_currents are dicts mapping element → float, updated in place.
    """
    # ── 1. Collect all electrical terminals ─────────────────────────
    terminals = []  # (x, y, element, point_index)
    for e in elements:
        if isinstance(e, Wire):
            for i, pt in enumerate(e.points):
                terminals.append((pt[0], pt[1], e, i))
        elif isinstance(e, ActiveElement):
            a, b = e.get_connection_points()
            terminals.append((a[0], a[1], e, 0))
            terminals.append((b[0], b[1], e, 1))

    if len(terminals) < 2:
        return {}, [], cap_voltages, ind_currents

    # ── 2. Union-Find clustering → circuit nodes ────────────────────
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
        return {}, [], cap_voltages, ind_currents

    # ── 2.5 Pre-solve detection: shorts and voltage source conflicts ─
    errors = []
    v_src_info = []
    for e in elements:
        if isinstance(e, Power) and e.ptype == 'V' and e.switched_on:
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            if len(tidxs) >= 2:
                v_src_info.append((e, term_node[tidxs[0]], term_node[tidxs[1]], e.value))

    for elem, ni, nj, _ in v_src_info:
        if ni == nj:
            errors.append(f"短路: 电源({elem.id}) 两端直接通过导线连接")

    for i in range(len(v_src_info)):
        e1, ni1, nj1, v1 = v_src_info[i]
        for j in range(i + 1, len(v_src_info)):
            e2, ni2, nj2, v2 = v_src_info[j]
            if {ni1, nj1} == {ni2, nj2} and abs(v1 - v2) > 1e-6:
                errors.append(f"电压源冲突: 电源({e1.id})={v1}V 与 电源({e2.id})={v2}V 并联")

    # ground = node with most terminals
    degree = [0] * N
    for n in term_node:
        degree[n] += 1
    gnd = max(range(N), key=lambda i: degree[i])

    def vidx(node):
        if node == gnd:
            return -1
        return node if node < gnd else node - 1

    # ── 3. Build MNA branches ───────────────────────────────────────
    # ActiveElement / Power / Resistor etc → one branch
    # Wire → one branch per consecutive point pair
    branches = []       # (node_i, node_j, conductance, current_A, element, seg_idx)
    v_srcs = []         # (node_i_pos, node_j_neg, voltage, element)

    for e in elements:
        if isinstance(e, Wire):
            pts = e.points
            n_seg = len(pts) - 1
            if n_seg < 1:
                continue
            # Find terminal indices for each point of this wire
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            # tidxs should be in the same order as pts (since we appended in order)
            for si in range(n_seg):
                ni = term_node[tidxs[si]]
                nj = term_node[tidxs[si + 1]]
                if ni == nj:
                    continue
                Rseg = WIRE_R / n_seg
                branches.append((ni, nj, 1.0 / Rseg, 0.0, e, si))

        elif isinstance(e, ActiveElement):
            tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
            if len(tidxs) < 2:
                continue
            ni = term_node[tidxs[0]]
            nj = term_node[tidxs[1]]
            if ni == nj:
                continue

            if isinstance(e, Resistor):
                branches.append((ni, nj, 1.0 / e.resistance, 0.0, e, 0))
            elif isinstance(e, Ammeter):
                branches.append((ni, nj, 1.0 / Ammeter.R_METER, 0.0, e, 0))
            elif isinstance(e, Voltmeter):
                branches.append((ni, nj, 1.0 / Voltmeter.R_METER, 0.0, e, 0))
            elif isinstance(e, Inductor):
                if dt and dt > 0 and ind_currents is not None:
                    I_prev = ind_currents.get(e, 0.0)
                    L_SI = e.inductance * 1e-3  # mH → H
                    G = dt / L_SI if L_SI > 0 else 1e3
                    branches.append((ni, nj, G, I_prev, e, 0))
                else:
                    branches.append((ni, nj, 1.0 / INDUCTOR_R, 0.0, e, 0))
            elif isinstance(e, Capacitor):
                if dt and dt > 0 and cap_voltages is not None:
                    V_prev = cap_voltages.get(e, 0.0)
                    C_SI = e.capacitance * 1e-6  # μF → F
                    G = C_SI / dt if dt > 0 else 1e-9
                    branches.append((ni, nj, G, -G * V_prev, e, 0))
                else:
                    branches.append((ni, nj, 1.0 / CAP_R, 0.0, e, 0))
            elif isinstance(e, Solenoid):
                # DC: solenoid behaves as a pure resistor
                branches.append((ni, nj, 1.0 / e.resistance, 0.0, e, 0))
            elif isinstance(e, Power):
                if not e.switched_on:
                    continue  # switched off = open circuit
                if e.ptype == 'V':
                    V_val = e.value
                    if e.mode == 'AC':
                        freq = getattr(e, 'frequency', 50.0)
                        V_peak = e.value * math.sqrt(2)  # RMS → peak
                        V_val = V_peak * math.sin(2 * math.pi * freq * time)
                    v_srcs.append((ni, nj, V_val, e))
                else:
                    I_val = e.value
                    if e.mode == 'AC':
                        freq = getattr(e, 'frequency', 50.0)
                        I_peak = e.value * math.sqrt(2)  # RMS → peak
                        I_val = I_peak * math.sin(2 * math.pi * freq * time)
                    branches.append((ni, nj, 0.0, I_val, e, 0))

    if not branches and not v_srcs:
        return {}, errors, cap_voltages, ind_currents

    # ── 3.5 Shorted component detection ──────────────────────────────
    # Check if any passive component (R, C, L) is bypassed by a wire
    for e in elements:
        if not isinstance(e, (Resistor, Capacitor, Inductor, Solenoid, Ammeter, Voltmeter)):
            continue
        tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
        if len(tidxs) < 2:
            continue
        eni = term_node[tidxs[0]]
        enj = term_node[tidxs[1]]
        if eni == enj:
            continue  # already caught as shorted by being in same node
        for b_ni, b_nj, _, _, b_elem, _ in branches:
            if isinstance(b_elem, Wire) and {b_ni, b_nj} == {eni, enj}:
                name = type(e).__name__
                errors.append(f"短接: {name}({e.id}) 被导线旁路")
                break

    # ── 4. Build MNA matrix ─────────────────────────────────────────
    M = len(v_srcs)
    n_eq = (N - 1) + M
    if n_eq == 0:
        return {}, errors, cap_voltages, ind_currents

    A = np.zeros((n_eq, n_eq))
    b = np.zeros(n_eq)

    for ni, nj, G, Is, _, _ in branches:
        if abs(Is) > 1e-15:
            vi, vj = vidx(ni), vidx(nj)
            if vi >= 0:
                b[vi] -= Is
            if vj >= 0:
                b[vj] += Is

        if G < 1e-15:
            continue
        vi, vj = vidx(ni), vidx(nj)
        if vi >= 0:
            A[vi, vi] += G
        if vj >= 0:
            A[vj, vj] += G
        if vi >= 0 and vj >= 0:
            A[vi, vj] -= G
            A[vj, vi] -= G

    # Bleed resistors to ground
    for node in range(N):
        if node == gnd:
            continue
        vi = vidx(node)
        A[vi, vi] += 1.0 / GND_R

    # Voltage source stamps
    for idx, (ni, nj, V, _) in enumerate(v_srcs):
        eq = (N - 1) + idx
        col = eq
        vi, vj = vidx(ni), vidx(nj)
        if vi >= 0:
            A[vi, col] = 1.0
        if vj >= 0:
            A[vj, col] = -1.0
        if vi >= 0:
            A[eq, vi] = 1.0
        if vj >= 0:
            A[eq, vj] = -1.0
        b[eq] = V

    # ── 5. Solve ────────────────────────────────────────────────────
    try:
        x = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        errors.append("电路求解失败: 矩阵奇异，请检查是否存在冲突或短路")
        return {}, errors, cap_voltages, ind_currents

    node_V = {gnd: 0.0}
    for node in range(N):
        if node != gnd:
            node_V[node] = x[vidx(node)]

    vsrc_I = {}
    for idx, (_, _, _, elem) in enumerate(v_srcs):
        vsrc_I[elem] = x[(N - 1) + idx]

    # ── 6. Compute branch currents ──────────────────────────────────
    seg_currents = {}  # element -> list of (segment_current)

    for ni, nj, G, Is, elem, seg_idx in branches:
        Vi, Vj = node_V.get(ni, 0.0), node_V.get(nj, 0.0)
        I = G * (Vi - Vj) + Is
        seg_currents.setdefault(elem, []).append(I)

    currents = {}
    for elem, Is in seg_currents.items():
        currents[elem] = Is[0] if Is else 0.0

    for elem, I in vsrc_I.items():
        currents[elem] = I

    # ── 6.5 Update transient state (capacitor voltages, inductor currents) ──
    if dt and dt > 0:
        if cap_voltages is not None:
            for e in elements:
                if isinstance(e, Capacitor):
                    tidxs = [i for i, (_, _, elem, _) in enumerate(terminals) if elem is e]
                    if len(tidxs) >= 2:
                        ni, nj = term_node[tidxs[0]], term_node[tidxs[1]]
                        V_cap = node_V.get(ni, 0.0) - node_V.get(nj, 0.0)
                        cap_voltages[e] = V_cap
        if ind_currents is not None:
            for e in elements:
                if isinstance(e, Inductor):
                    I_ind = currents.get(e, 0.0)
                    ind_currents[e] = I_ind

    # ── 7. High current warning ─────────────────────────────────────
    HIGH_CURRENT = 100.0
    for elem, I in currents.items():
        if abs(I) > HIGH_CURRENT:
            errors.append(f"大电流警告: {elem.get_info()} 电流={I:.1f}A")

    return currents, errors, cap_voltages, ind_currents
