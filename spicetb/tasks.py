"""The 24 AnalogCoder problems and their SPICE testbenches.

Each problem has a checker function ``check_<type>(ctx)`` that raises
``CheckFailed`` with a diagnostic message when the design does not meet the
target.  The checks follow the original AnalogCoder PySpice testbenches
(``gpt_run.py`` + ``problem_check/*.py``) as closely as possible; deliberate
deviations are documented in README.md ("Differences from the original").
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .netlist import Element, Netlist, Rules, norm_node
from .ngspice import Plot, SimResult, simulate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBLEM_DIR = os.path.join(ROOT, "problems")
LIB_DIR = os.path.join(PROBLEM_DIR, "lib")

BIAS = 2.5                # DC operating voltage of the provided op-amp inputs
OPAMP = "singlestageopamp"
VTH = 0.5                 # threshold used by the operating-point check

STAGES = ("input", "netlist", "simulation", "operating-point", "function", "internal")


class CheckFailed(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass
class Result:
    task: int
    passed: bool
    stage: str                 # "pass" or the stage that failed
    message: str
    notes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def feedback(self) -> str:
        """Detailed, human-readable report (used for the 'error' feedback mode)."""
        if self.passed:
            return "PASS: " + (self.message or "the design meets the target.")
        out = [f"FAIL ({self.stage} check)", self.message.strip()]
        if self.notes:
            out.append("Notes:\n" + "\n".join(f"- {n}" for n in self.notes))
        return "\n\n".join(out)

    def to_dict(self) -> dict:
        return {"task": self.task, "passed": self.passed, "stage": self.stage,
                "message": self.message, "notes": self.notes, "metrics": self.metrics}


# --------------------------------------------------------------------------
# Context and simulation helpers
# --------------------------------------------------------------------------

class Ctx:
    def __init__(self, task: "Task", nl: Netlist, timeout: int, keep_dir: str | None):
        self.task = task
        self.nl = nl
        self.timeout = timeout
        self.keep_dir = keep_dir
        self.notes: list[str] = []
        self.metrics: dict = {}
        self._n = 0

    def sim(self, nl: Netlist, analysis: str, saves: list[str] | None = None) -> SimResult:
        self._n += 1
        kd = None
        if self.keep_dir:
            kd = os.path.join(self.keep_dir, f"{self._n:02d}_{analysis.split()[0]}")
        return simulate(nl.render(), analysis, saves, timeout=self.timeout, keep_dir=kd)

    def fail(self, stage: str, msg: str):
        raise CheckFailed(stage, msg)


FLOATING_MSG = ("The circuit design has one floating node: {node}, causing an error in simulation.\n"
                "Please consider connecting it to a voltage or current source or another device.")


def run_op(ctx: Ctx, nl: Netlist) -> SimResult:
    mos = nl.elements("m")
    saves = (["all"] + [f"@{m.name}[id]" for m in mos]) if mos else None
    return ctx.sim(nl, "op", saves)


def sanity_op(ctx: Ctx, nl: Netlist, floating_fatal: bool | None = None) -> Plot:
    """DC operating point of the submitted circuit.

    A node without a DC path ("singular matrix: check node X") is a hard error
    for the DC/AC problems 1-15 (as in AnalogCoder).  For the transient-based
    problems 16-24 ngspice still finds an operating point (transient-op
    fallback), so it is reported as a note only.
    """
    if floating_fatal is None:
        floating_fatal = ctx.task.id <= 15
    r = run_op(ctx, nl)
    if r.floating_nodes:
        if floating_fatal or not r.ok:
            ctx.fail("simulation", FLOATING_MSG.format(node=r.floating_nodes[0]))
        ctx.notes.append(f"Node {r.floating_nodes[0]} has no DC path to ground (the simulator had to "
                         "fall back to a transient operating point).")
    if not r.ok:
        ctx.fail("simulation", "The simulator reported an error while computing the DC operating "
                 "point. Simulator output:\n" + r.error_text())
    return r.plot


def node_v(op: Plot, node: str) -> float:
    node = norm_node(node)
    if node == "0":
        return 0.0
    return op.node_voltages().get(node, 0.0)


def op_listing(op: Plot) -> str:
    return "\n".join(f"{k}\t{v:.6f}" for k, v in op.node_voltages().items())


def check_io_nodes(ctx: Ctx, op: Plot):
    nodes = set(op.node_voltages())
    msg = ""
    for n in ctx.task.inputs:
        if n.lower() not in nodes:
            msg += f"The given input node ({n}) is not found in the netlist.\n"
    for n in ctx.task.outputs:
        if n.lower() not in nodes:
            msg += f"The given output node ({n}) is not found in the netlist.\n"
    if msg:
        ctx.fail("netlist", msg + "Suggestion: You can replace the nodes actually used for "
                 "input/output with the given names. Please rewrite the corrected complete netlist.")


def need_source(ctx: Ctx, nl: Netlist, node: str, label: str | None = None) -> Element:
    srcs = nl.sources_at(node, "v")
    if not srcs:
        label = label or node
        ctx.fail("netlist", f"No independent voltage source is connected to the input node {label}. "
                 f"Please drive {label} with a DC voltage source to ground, e.g. "
                 f"`V{label} {label} 0 <dc value>`.")
    return srcs[0]


def drive(e: Element, node: str, v: float, ac: str | None = None, phase: float = 0.0) -> str:
    """Card text for source ``e`` so that ``node`` sits at ``v`` volts."""
    sign = 1.0 if e.nodes[0] == norm_node(node) else -1.0
    if sign < 0:
        phase += 180.0
    s = f"{e.tokens[0]} {e.tokens[1]} {e.tokens[2]} dc {sign * v:.12g}"
    if ac is not None:
        s += f" ac {ac}" + (f" {phase:g}" if phase else "")
    return s


def sweep_cmd(e: Element, node: str, start: float, stop: float, step: float) -> str:
    sign = 1.0 if e.nodes[0] == norm_node(node) else -1.0
    return f"dc {e.tokens[0]} {sign * start:g} {sign * stop:g} {sign * step:g}"


def mos_id(op: Plot, name: str) -> float:
    for key in (f"i(@{name}[id])", f"@{name}[id]"):
        if op.has(key):
            return float(np.real(op.vec(key)[0]))
    return float("nan")


def uniform(plot: Plot, node: str, dt: float, tstop: float, tstart: float = 0.0):
    t = np.real(plot.scale)
    y = np.real(plot.vec(node))
    tu = np.arange(tstart, tstop + dt / 2, dt)
    return tu, np.interp(tu, t, y)


def rising_crossings(t, y, th):
    idx = np.nonzero((y[:-1] < th) & (y[1:] >= th))[0]
    return t[idx] + (th - y[idx]) * (t[idx + 1] - t[idx]) / (y[idx + 1] - y[idx])


def all_crossings(t, y, th):
    s = np.sign(y - th)
    idx = np.nonzero(s[:-1] * s[1:] < 0)[0]
    return t[idx] + (th - y[idx]) * (t[idx + 1] - t[idx]) / (y[idx + 1] - y[idx])


# --------------------------------------------------------------------------
# Problems 1-15: transistor-level circuits
# --------------------------------------------------------------------------

def dc_sweep_bias(ctx: Ctx, nl: Netlist, op: Plot) -> tuple[Netlist, Plot]:
    """Original AnalogCoder auto-biasing: sweep the input 0..5 V and pick the
    input DC level whose output is closest to 2.5 V."""
    t = ctx.task
    if t.type == "Amplifier":
        src = need_source(ctx, nl, "vin", "Vin")
        sweep_nl, node, others = nl, "vin", []
    else:
        src = need_source(ctx, nl, "vinn", "Vinn")
        sp = need_source(ctx, nl, "vinp", "Vinp")
        if sp.name == src.name:
            ctx.fail("netlist", "Vinp and Vinn must be driven by two separate DC voltage sources "
                     "(each referenced to ground).")
        tie = nl.unique_name("Vtb_tie")
        sweep_nl = nl.remove(sp.name).add(f"{tie} vinn vinp 0")
        node, others = "vinn", [(sp, "vinp")]
    r = ctx.sim(sweep_nl, sweep_cmd(src, node, 0, 5, 0.01), saves=["v(vout)", f"v({node})"])
    if not r.ok or not r.plot.has("vout"):
        ctx.notes.append("The DC sweep of the input failed; the input bias written in the netlist is used.")
        return nl, op
    vout = np.real(r.plot.vec("vout"))
    vin = np.real(r.plot.vec(node))
    if np.max(vout) - np.min(vout) < 1e-3:
        ctx.fail("function", "According to dc sweep analysis, changing the input voltage does not "
                 "change the output voltage. Please check the netlist and rewrite the complete netlist.\n"
                 "Reference operating point:\n" + op_listing(op))
    best = round(float(vin[int(np.argmin(np.abs(vout - 2.5)))]), 4)
    new = nl.replace(src.name, drive(src, node, best))
    for e, n in others:
        new = new.replace(e.name, drive(e, n, best))
    r2 = run_op(ctx, new)
    if r2.ok and not r2.floating_nodes:
        ctx.notes.append(f"According to dc sweep analysis, the best input voltage is {best} V "
                         f"(output closest to 2.5 V); the testbench re-biased the input(s) to it.")
        ctx.metrics["input_bias"] = best
        return new, r2.plot
    return nl, op


def region_check(ctx: Ctx, nl: Netlist, op: Plot):
    """Port of AnalogCoder ``check_netlist``: MOSFET operating-region sanity
    checks plus a few topology checks."""
    tid = ctx.task.id
    V = {k: round(v, 6) for k, v in op.node_voltages().items()}
    V["0"] = 0.0
    get = lambda n: V.get(n, 0.0)
    vdd = V.get("vdd", 5.0)
    msg: list[str] = []
    if "vinn" in V and "vinp" in V and V["vinn"] != V["vinp"]:
        msg += ["The given input voltages of Vinn and Vinp are not equal.",
                "Suggestion: Please make sure the input voltages are equal."]
    has_diode_load = False
    first_stage_outs: list[str] = []
    for m in nl.elements("m"):
        d, g, s, _b = (m.nodes + ["0"] * 4)[:4]
        name = m.tokens[0]
        typ = nl.mos_type(m).upper()
        if tid == 4:
            if "vin" in (d, g):
                msg += ["For a common-gate amplifier, the vin should be connected to source.",
                        "Suggestion: Please connect the vin to the source node."]
        elif tid == 3:
            if "vout" in (d, g):
                msg += ["For a common-drain amplifier, the vout should be connected to source.",
                        "Suggestion: Please connect the vout to the source node."]
        elif tid == 10:
            if g == d:
                has_diode_load = True
        elif tid == 9:
            if g == "vin":
                first_stage_outs.append(d)
        if typ == "NMOS":
            vds_err = False
            if get(d) == 0.0:
                if d == "0":
                    msg.append(f"Suggestion: Please avoid connecting {typ} {name} drain to the ground.")
                else:
                    vds_err = True
                    msg.append(f"For {typ} {name}, the drain node ({d}) voltage is 0.")
            elif get(d) < get(s):
                vds_err = True
                msg.append(f"For {typ} {name}, the drain node ({d}) voltage is lower than the source node ({s}) voltage.")
            if vds_err:
                msg.append(f"Suggestion: Please set {typ} {name} with an activated state and make sure V_DS > V_GS - V_TH.")
            vgs_err = False
            if get(g) == get(s):
                if g == s:
                    msg.append(f"For {typ} {name}, the gate node ({g}) is connected to the source node ({s}).")
                    msg.append(f"Suggestion: For {typ} {name}, please divide its gate ({g}) and source ({s}) connection.")
                else:
                    vgs_err = True
                    msg.append(f"For {typ} {name}, the gate node ({g}) voltage is equal to the source node ({s}) voltage.")
            elif get(g) < get(s):
                vgs_err = True
                msg.append(f"For {typ} {name}, the gate node ({g}) voltage is lower than the source node ({s}) voltage.")
            elif get(g) <= get(s) + VTH:
                vgs_err = True
                msg.append(f"For {typ} {name}, the gate node ({g}) voltage is lower than the source node ({s}) voltage plus the threshold voltage.")
            if vgs_err:
                msg.append(f"Suggestion: Please set {typ} {name} with an activated state by increasing the gate voltage or decreasing the source voltage and make sure V_GS > V_TH.")
        else:
            vds_err = False
            if get(d) == vdd:
                if d == "vdd":
                    msg.append(f"Suggestion: Please avoid connecting {typ} {name} drain to the vdd.")
                else:
                    vds_err = True
                    msg.append(f"For {typ} {name}, the drain node ({d}) voltage is V_dd.")
            elif get(d) > get(s):
                vds_err = True
                msg.append(f"For {typ} {name}, the drain node ({d}) voltage is higher than the source node ({s}) voltage.")
            if vds_err:
                msg.append(f"Suggestion: Please set {typ} {name} with an activated state and make sure V_DS < V_GS - V_TH.")
            vgs_err = False
            if get(g) == get(s):
                if g == s:
                    msg.append(f"For {typ} {name}, the gate node ({g}) is connected to the source node ({s}).")
                    msg.append(f"Suggestion: For {typ} {name}, please divide its gate ({g}) and source ({s}) connection.")
                else:
                    vgs_err = True
                    msg.append(f"For {typ} {name}, the gate node ({g}) voltage is equal to the source node ({s}) voltage.")
            elif get(g) > get(s):
                vgs_err = True
                msg.append(f"For {typ} {name}, the gate node ({g}) voltage is higher than the source node ({s}) voltage.")
            elif get(g) >= get(s) - VTH:
                vgs_err = True
                msg.append(f"For {typ} {name}, the gate node ({g}) voltage is higher than the source node ({s}) voltage minus the threshold voltage.")
            if vgs_err:
                msg.append(f"Suggestion: Please set {typ} {name} with an activated state by decreasing the gate voltage or increasing the source voltage and make sure V_GS < V_TH.")

    if tid in (1, 2, 3, 4, 5, 6, 8, 13) and not nl.elements("r"):
        msg += ["There is no resistance in the netlist.",
                "Suggestion: Please add a resistance load in the netlist."]
    if tid == 9:
        caps = nl.elements("c")
        ok = any(set(c.nodes) == {fso, "vout"} for c in caps for fso in first_stage_outs)
        if not first_stage_outs:
            msg += ["There is no first stage output in the netlist.",
                    "Suggestion: Please add a first stage output in the netlist."]
        elif ok:
            pass
        elif not caps:
            msg += ["There is no Miller capacitor in the netlist.",
                    "Suggestion: Please correctly connect the Miller compensation capacitor."]
        else:
            msg += ["The Miller compensation capacitor is not correctly connected "
                    "(it must connect the first-stage output to Vout).",
                    "Suggestion: Please correctly connect the Miller compensation capacitor."]
    if tid == 10 and not has_diode_load:
        msg += ["There is no diode-connected load in the netlist.",
                "Suggestion: Please add a diode-connected load in the netlist."]
    if msg:
        ctx.fail("operating-point",
                 "According to the operating point check, there are some issues, which defy the general "
                 "operating principles of MOSFET devices.\n" + "\n".join(msg) +
                 "\n\nPlease help me fix the issues and rewrite the corrected complete netlist.")


def id_check(ctx: Ctx, nl: Netlist, op: Plot):
    bad = []
    for m in nl.elements("m"):
        i = mos_id(op, m.name)
        ctx.metrics.setdefault("id", {})[m.tokens[0]] = i
        if not (i >= 1e-5):
            bad.append(f"The circuit does not function correctly. The current I_D for {m.tokens[0]} is 0 "
                       f"(I_D = {i:.3g} A < 10 uA).")
    if bad:
        ctx.fail("function", "\n".join(bad) + "\nPlease fix the wrong operating point.")


def ac_gain(ctx: Ctx, nl: Netlist) -> float:
    r = ctx.sim(nl, "ac dec 2 100 1000", saves=["v(vout)"])
    if not r.ok:
        ctx.fail("simulation", "AC analysis failed. Simulator output:\n" + r.error_text())
    return float(np.abs(r.plot.vec("vout")[0]) / 1e-6)


def fn_amplifier(ctx: Ctx, nl: Netlist, op: Plot):
    id_check(ctx, nl, op)
    src = need_source(ctx, nl, "vin", "Vin")
    gain = ac_gain(ctx, nl.replace(src.name, drive(src, "vin", node_v(op, "vin"), ac="1u")))
    ctx.metrics["gain_100Hz"] = gain
    ctx.metrics["gain_100Hz_dB"] = float(20 * np.log10(gain)) if gain > 0 else None
    if gain > 1e-5:
        return f"Voltage gain (Av) at 100 Hz: {gain:.6g}. The circuit functions correctly at 100 Hz."
    ctx.fail("function", f"Voltage Gain (Av) at 100 Hz: {gain}\nThe circuit does not function correctly.\n"
             "The gain is less than 1e-5.\nPlease fix the wrong operating point.")


def fn_opamp(ctx: Ctx, nl: Netlist, op: Plot):
    id_check(ctx, nl, op)
    sp = need_source(ctx, nl, "vinp", "Vinp")
    sn = need_source(ctx, nl, "vinn", "Vinn")
    if sp.name == sn.name:
        ctx.fail("netlist", "Vinp and Vinn must be driven by two separate DC voltage sources.")
    vp, vn = node_v(op, "vinp"), node_v(op, "vinn")
    cm = nl.replace(sp.name, drive(sp, "vinp", vp, ac="1u")).replace(sn.name, drive(sn, "vinn", vn, ac="1u"))
    g_cm = ac_gain(ctx, cm)
    dm = cm.replace(sn.name, drive(sn, "vinn", vn, ac="1u", phase=180))
    g_dm = ac_gain(ctx, dm)
    ctx.metrics.update(cm_gain_100Hz=g_cm, dm_gain_100Hz=g_dm)
    head = (f"Common-Mode Gain (Av) at 100 Hz: {g_cm:.6g}\n"
            f"Differential-Mode Gain (Av) at 100 Hz: {g_dm:.6g}\n")
    if g_cm < g_dm - 1e-5 and g_dm > 1e-5:
        return head + "The circuit functions correctly at 100 Hz."
    msg = head
    if g_cm >= g_dm - 1e-5:
        msg += "Common-Mode gain is larger than Differential-Mode gain.\n"
    if g_dm < 1e-5:
        msg += "Differential-Mode gain is smaller than 1e-5.\n"
    ctx.fail("function", msg + "The circuit does not function correctly.\nPlease fix the wrong operating point.")


def fn_inverter(ctx: Ctx, nl: Netlist, op: Plot):
    src = need_source(ctx, nl, "vin", "Vin")
    outs = []
    for v in (5.0, 0.0):
        r = run_op(ctx, nl.replace(src.name, drive(src, "vin", v)))
        if not r.ok:
            ctx.fail("simulation", f"Operating point with Vin = {v} V failed. Simulator output:\n" + r.error_text())
        outs.append(node_v(r.plot, "vout"))
    hi_in, lo_in = outs
    ctx.metrics.update(vout_at_vin_5V=hi_in, vout_at_vin_0V=lo_in)
    if hi_in <= 2.5 and lo_in >= 2.5 and lo_in - hi_in >= 1.0:
        return f"Vout(Vin=5 V) = {hi_in:.4f} V, Vout(Vin=0 V) = {lo_in:.4f} V. The circuit functions correctly."
    ctx.fail("function", f"Vout(Vin=5 V) = {hi_in:.4f} V, Vout(Vin=0 V) = {lo_in:.4f} V.\n"
             "The circuit does not function correctly.\nIt can not invert the input voltage.\n"
             "Please fix the wrong operating point.")


def fn_current_mirror(ctx: Ctx, nl: Netlist, op: Plot):
    out = ctx.task.outputs[0].lower()
    rs = nl.connected(out, "r")
    if not rs:
        ctx.fail("netlist", f"There is no load resistor connected to the output node "
                 f"{ctx.task.outputs[0]}. Please add the resistive load R at the output.")
    r = rs[0]
    n1, n2 = r.nodes

    def load_current(netlist: Netlist, R: float) -> float:
        res = run_op(ctx, netlist.replace(r.name, f"{r.tokens[0]} {r.tokens[1]} {r.tokens[2]} {R:g}"))
        if not res.ok:
            ctx.fail("simulation", f"Operating point with load {R:g} Ohm failed. Simulator output:\n"
                     + res.error_text())
        return abs(node_v(res.plot, n1) - node_v(res.plot, n2)) / R

    loads = [100, 300, 500, 750, 1000]
    currents = [load_current(nl, R) for R in loads]
    table = "\n".join(f"Load: {R} Ohm, Current: {i:.6g} A" for R, i in zip(loads, currents))
    ctx.metrics["load_currents"] = dict(zip(map(str, loads), currents))
    variations = [abs(currents[i + 1] - currents[i]) for i in range(4)]
    if not (min(variations) < 1e-6 and min(currents) > 1e-5):
        ctx.fail("function", table + "\nThe circuit does not function correctly as a current source.")
    if ctx.task.id == 12:
        isrc = nl.sources_at("iref", "i")
        if not isrc:
            ctx.fail("netlist", "No reference current source is connected to node Iref. Please supply "
                     "the reference current with an independent current source from Vdd to Iref, "
                     "e.g. `Iref Vdd Iref 1m`.")
        s = isrc[0]
        new = nl.replace(s.name, f"{s.tokens[0]} {s.tokens[1]} {s.tokens[2]} dc 1.55m")
        i2 = load_current(new, 500)
        ctx.metrics["load_current_Iref_1.55mA"] = i2
        if abs(i2 - currents[2]) < 1e-6:
            ctx.fail("function", table + "\nThe circuit does not work as a current mirror because it "
                     "cannot replicate the Iref current (changing Iref to 1.55 mA does not change the "
                     "output current).")
    return table + "\nThe circuit functions correctly as a current source within the given tolerance."


def check_basic(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    t = ctx.task
    if t.type in ("Amplifier", "Opamp"):
        nl, op = dc_sweep_bias(ctx, nl, op)
    if t.type != "Inverter":
        region_check(ctx, nl, op)
    fn = {"Amplifier": fn_amplifier, "Opamp": fn_opamp, "Inverter": fn_inverter,
          "CurrentMirror": fn_current_mirror}[t.type]
    return fn(ctx, nl, op)


# --------------------------------------------------------------------------
# Problems 16-22: op-amp applications (provided SingleStageOpamp)
# --------------------------------------------------------------------------

def need_opamps(ctx: Ctx, nl: Netlist) -> list[Element]:
    xs = [x for x in nl.elements("x") if x.model == OPAMP]
    if not xs:
        ctx.fail("netlist", "This problem must be solved with the provided op-amp: add "
                 "`.include opamp.lib` and instantiate it as "
                 "`Xop <non-inverting input> <inverting input> <output> SingleStageOpamp`.")
    return xs


def replace_input(nl: Netlist, node: str, card_tail: str, name: str = "Vtb_in") -> Netlist:
    """Remove every voltage source attached to ``node`` and drive it from the testbench."""
    srcs = nl.sources_at(node, "v")
    new = nl.remove(*[s.name for s in srcs]) if srcs else nl
    return new.add(f"{new.unique_name(name)} {node} 0 {card_tail}")


def require_element(ctx: Ctx, nl: Netlist, name: str, what: str) -> Element:
    e = nl.element(name)
    if e is None:
        ctx.fail("netlist", f"The {what} must be named {name} so that the testbench can set its value "
                 f"(no element called '{name}' found).")
    return e


def require_feedback(ctx: Ctx, opamps: list[Element], e: Element, what: str):
    """``e`` must connect an op-amp's inverting input to that op-amp's output."""
    for x in opamps:
        if len(x.nodes) >= 3 and set(e.nodes) == {x.nodes[1], x.nodes[2]}:
            return
    ctx.fail("netlist", f"{e.tokens[0]} must be the {what} connected between the inverting input and "
             f"the output of the op-amp (found {e.tokens[0]} between nodes {e.nodes[0]} and {e.nodes[1]}).")


def set_value(nl: Netlist, e: Element, value: str) -> Netlist:
    return nl.replace(e.name, f"{e.tokens[0]} {e.tokens[1]} {e.tokens[2]} {value}")


def check_oscillator(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    x = need_opamps(ctx, nl)[0]
    p, n = x.nodes[0], x.nodes[1]
    ics = [f"v({k})={v}" for k, v in ((p, BIAS + 0.01), (n, BIAS)) if k != "0"]
    tb = nl.add(".ic " + " ".join(ics)) if ics else nl
    r = ctx.sim(tb, "tran 1u 10m", saves=["v(vout)"])
    if not r.ok:
        ctx.fail("simulation", "Transient analysis failed. Simulator output:\n" + r.error_text())
    from scipy.signal import find_peaks, firwin, lfilter
    t, vout = uniform(r.plot, "vout", 1e-6, 10e-3)
    fir = firwin(51, 10.0, fs=1000, window="hamming")
    filt = lfilter(fir, 1.0, vout)
    peaks, _ = find_peaks(filt)
    troughs, _ = find_peaks(-filt)
    if len(peaks) == 0 or len(troughs) == 0:
        ctx.fail("function", "Not enough peaks were detected to determine amplitude. "
                 "Vout does not oscillate.")
    amps = np.array([abs(vout[pk] - vout[troughs[np.argmin(np.abs(troughs - pk))]]) for pk in peaks])
    amps = np.sort(amps)
    amps = amps[-(len(amps) // 2):]
    errs = []
    if not np.all(amps > 1e-6):
        errs.append("The peak amplitudes are too small. (<1uV)")
    if len(peaks) > 3:
        periods = np.diff(t[peaks])
        ctx.metrics.update(frequency_Hz=float(1 / np.mean(periods)), amplitude_V=float(np.max(amps)))
        if np.std(periods) >= 0.2 * np.mean(periods):
            errs.append("Periodicity is inconsistent, oscillation may not be an ideal periodicity.")
    else:
        errs.append("Not enough peaks were detected to determine periodicity.")
    if errs:
        ctx.fail("function", "\n".join(errs))
    return (f"The oscillator works correctly and produces periodic oscillations. "
            f"The average period is: {1 / ctx.metrics['frequency_Hz']:.6g} s")


def _slope_segment(t, v):
    from scipy.signal import find_peaks
    from scipy.stats import linregress
    peaks, _ = find_peaks(v)
    troughs, _ = find_peaks(-v)
    if len(peaks) < 2 or len(troughs) < 2:
        return None
    start = peaks[-2]
    after = troughs[troughs > start]
    if len(after) == 0 or after[0] - start < 3:
        return None
    end = after[0]
    slope = abs(np.polyfit(t[start:end], v[start:end], 1)[0])
    rv = linregress(t[start:end], v[start:end]).rvalue
    return slope, rv ** 2


def check_integrator(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    xs = need_opamps(ctx, nl)
    b = BIAS
    r1 = require_element(ctx, nl, "R1", "input resistor")
    cf = require_element(ctx, nl, "Cf", "feedback capacitor")
    require_feedback(ctx, xs, cf, "feedback capacitor")
    tb = set_value(set_value(nl, r1, "10k"), cf, "3u")
    tb = replace_input(tb, "vin", f"dc {b} PULSE({b - 0.5} {b + 0.5} 1u 1u 1u 10m 20m)")
    r = ctx.sim(tb, "tran 1u 200m", saves=["v(vout)", "v(vin)"])
    if not r.ok:
        ctx.fail("simulation", "Transient analysis failed. Simulator output:\n" + r.error_text())
    t, v = uniform(r.plot, "vout", 1e-6, 200e-3)
    expected = 0.5 / 0.03
    seg = _slope_segment(t, v)
    if seg is None:
        ctx.fail("function", "No peaks or troughs found in output voltage. Please check the netlist.")
    slope, r2 = seg
    ctx.metrics.update(slope_V_per_s=slope, expected_slope_V_per_s=expected, r_squared=r2)
    if not np.isclose(slope, expected, rtol=0.3):
        ctx.fail("function", "The circuit does not function correctly as an integrator.\n"
                 f"Expected slope: {expected} V/s | Actual slope: {slope} V/s\n"
                 "(test conditions: R1 = 10k, Cf = 3u, Vin = 2.5 V +/- 0.5 V square wave, 20 ms period)")
    if r2 < 0.9:
        ctx.fail("function", "The op-amp integrator does not have a linear response.")
    # The same circuit without the op-amp must not integrate (rules out passive RC).
    passive = tb.remove(*[x.name for x in xs])
    r = ctx.sim(passive, "tran 1u 200m", saves=["v(vout)", "v(vin)"])
    if r.ok and r.plot.has("vout"):
        t, v = uniform(r.plot, "vout", 1e-6, 200e-3)
        seg = _slope_segment(t, v)
        if seg is not None and np.isclose(seg[0], expected, rtol=0.5):
            ctx.fail("function", "The integrator maybe a passive integrator: it still integrates "
                     "after the op-amp is removed.")
    return f"The op-amp integrator functions correctly (slope {slope:.4g} V/s, expected {expected:.4g} V/s)."


def _square_stats(v, b):
    from scipy.signal import find_peaks
    mid = (np.max(v) + np.min(v)) / 2
    dist = len(v) / (2 * 2) / 1.5
    peaks, _ = find_peaks(v, height=mid, distance=dist)
    troughs, _ = find_peaks(-v, height=-mid, distance=dist)
    if len(peaks) == 0 or len(troughs) == 0:
        return None
    mp, mt = float(np.mean(v[peaks])), float(np.mean(v[troughs]))
    thr = (mp + mt) / 2
    hi, lo = v[v > thr], v[v <= thr]
    # "square": the average level of each half-cycle is close to its peak level.
    # (Measured relative to the bias; the original compared absolute voltages,
    # which also accepts a triangle wave riding on 2.5 V.)
    square = (len(hi) > 0 and len(lo) > 0 and mp - b > 0 and b - mt > 0
              and np.isclose(np.mean(hi) - b, mp - b, rtol=0.1)
              and np.isclose(b - np.mean(lo), b - mt, rtol=0.1))
    sym = bool(np.isclose(mp - b, -mt + b, rtol=0.2))
    amp = bool(np.isclose(mp - b, 0.6, rtol=0.2))
    return mp, mt, sym, amp, bool(square)


def check_differentiator(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    xs = need_opamps(ctx, nl)
    b = BIAS
    rf = require_element(ctx, nl, "Rf", "feedback resistor")
    c1 = require_element(ctx, nl, "C1", "input capacitor")
    require_feedback(ctx, xs, rf, "feedback resistor")
    tb = set_value(set_value(nl, rf, "10k"), c1, "3u")
    tb = replace_input(tb, "vin", f"dc {b} PULSE({b - 0.5} {b + 0.5} 0 50m 50m 1n 100m)")
    r = ctx.sim(tb, "tran 1u 200m", saves=["v(vout)", "v(vin)"])
    if not r.ok:
        ctx.fail("simulation", "Transient analysis failed. Simulator output:\n" + r.error_text())
    t, v = uniform(r.plot, "vout", 1e-6, 200e-3)
    st = _square_stats(v, b)
    if st is None:
        ctx.fail("function", "No peaks or troughs found in output voltage. Please check the netlist.")
    mp, mt, sym, amp, square = st
    ctx.metrics.update(mean_peak_V=mp, mean_trough_V=mt)
    cond = ("(test conditions: Rf = 10k, C1 = 3u, Vin = triangle wave 2.0 V..3.0 V with 100 ms period; "
            "expected output: square wave 2.5 V +/- 0.6 V)")
    if not (sym and square):
        ctx.fail("function", "The circuit does not function correctly as a differentiator.\n"
                 "When the input is a triangle wave, the output is not a square wave.\n" + cond)
    if not amp:
        ctx.fail("function", "The circuit does not function correctly as a differentiator.\n"
                 f"Output voltage peak value is wrong. Mean peak voltage: {mp} V | Mean trough voltage: {mt} V\n" + cond)
    passive = tb.remove(*[x.name for x in xs])
    r = ctx.sim(passive, "tran 1u 200m", saves=["v(vout)", "v(vin)"])
    if r.ok and r.plot.has("vout"):
        t, v = uniform(r.plot, "vout", 1e-6, 200e-3)
        st2 = _square_stats(v, b)
        if st2 is not None and st2[2] and st2[3] and st2[4]:
            ctx.fail("function", "The differentiator maybe a passive differentiator: it still "
                     "differentiates after the op-amp is removed.")
    return f"The op-amp differentiator functions correctly (output {mt:.3f} V .. {mp:.3f} V)."


def check_adder(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    need_opamps(ctx, nl)
    b = BIAS
    v2 = b + 0.125
    tb = replace_input(nl, "vin1", f"dc {b}", "Vtb_in1")
    s1 = tb.cards[-1].tokens[0]
    tb = replace_input(tb, "vin2", f"dc {v2}", "Vtb_in2")
    r = ctx.sim(tb, f"dc {s1} {b} {b + 0.5} 0.01", saves=["v(vout)", "v(vin1)"])
    if not r.ok:
        ctx.fail("simulation", "DC analysis failed. Simulator output:\n" + r.error_text())
    vout = np.real(r.plot.vec("vout"))
    vin1 = np.real(r.plot.vec("vin1"))
    worst = 0.0
    for vo, vi in zip(vout, vin1):
        expected = b - ((vi - b) + (v2 - b))
        worst = max(worst, abs(vo - expected))
        if not np.isclose(vo, expected, rtol=0.2):
            ctx.fail("function", "The circuit does not function correctly as an adder.\n"
                     f"Expected Vout: {expected:.4f} V, Vin1 = {vi:.4f} V, Vin2 = {v2:.4f} V | "
                     f"Actual Vout: {vo:.4f} V\n"
                     f"(signals are referenced to {b} V: Vout - {b} = -((Vin1 - {b}) + (Vin2 - {b})))")
    ctx.metrics["max_abs_error_V"] = worst
    return "The op-amp adder functions correctly."


def check_subtractor(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    need_opamps(ctx, nl)
    v1 = v2 = 2 * BIAS
    tb = replace_input(nl, "vin1", f"dc {v1}", "Vtb_in1")
    s1 = tb.cards[-1].tokens[0]
    tb = replace_input(tb, "vin2", f"dc {v2}", "Vtb_in2")
    r = ctx.sim(tb, f"dc {s1} {2 * BIAS - 2.25} {2 * BIAS - 1.75} 0.05", saves=["v(vout)", "v(vin1)"])
    if not r.ok:
        ctx.fail("simulation", "DC analysis failed. Simulator output:\n" + r.error_text())
    vout = np.real(r.plot.vec("vout"))
    vin1 = np.real(r.plot.vec("vin1"))
    worst = 0.0
    for vo, vi in zip(vout, vin1):
        expected = v2 - vi
        worst = max(worst, abs(vo - expected))
        if not np.isclose(vo, expected, rtol=0.2):
            ctx.fail("function", "The circuit does not function correctly as a subtractor.\n"
                     f"Expected Vout: {expected:.2f} V, Vin1 = {vi:.2f} V, Vin2 = {v2:.2f} V | "
                     f"Actual Vout: {vo:.2f} V")
    ctx.metrics["max_abs_error_V"] = worst
    return "The op-amp subtractor functions correctly."


def check_schmitt(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    need_opamps(ctx, nl)
    src = need_source(ctx, nl, "vin", "Vin")
    up = ctx.sim(nl, sweep_cmd(src, "vin", 0, 5, 0.1), saves=["v(vout)", "v(vin)"])
    dn = ctx.sim(nl, sweep_cmd(src, "vin", 5, 0, -0.1), saves=["v(vout)", "v(vin)"])
    for r in (up, dn):
        if not r.ok:
            ctx.fail("simulation", "DC analysis failed. Simulator output:\n" + r.error_text())
    vin, vout = np.real(up.plot.vec("vin")), np.real(up.plot.vec("vout"))
    vin2, vout2 = np.real(dn.plot.vec("vin"))[::-1], np.real(dn.plot.vec("vout"))[::-1]
    hi1, hi2 = np.nonzero(vout > 2.5)[0], np.nonzero(vout2 > 2.5)[0]
    if len(hi1) == 0 or len(hi2) == 0:
        ctx.fail("function", "The circuit does not function correctly. The output voltage does not cross the Vdd/2.")
    t1, t2 = float(vin[hi1[0]]), float(vin2[hi2[0]])
    ctx.metrics.update(trigger_rising_V=t1, trigger_falling_V=t2)
    if abs(t1 - t2) <= 0.05:
        ctx.fail("function", "The circuit does not function correctly. Trigger points are too close.\n"
                 f"Trigger points: {t1:.5f}V and {t2:.5f}V are not sufficiently different. Please use the "
                 "positive feedback which the Rf should connect to the non-inverting input of the op-amp.")
    if vout[-1] - vout[0] < 2.5 or vout2[-1] - vout2[0] < 2.5:
        ctx.fail("function", "The circuit does not function correctly. The output voltage does not vary more than Vdd/2.")
    if not (np.all(np.diff(vout) >= -1e-6) and np.all(np.diff(vout2) >= -1e-6)):
        ctx.fail("function", "The circuit does not function correctly. The output voltage variation does not "
                 "monotonically increase with increasing input voltage.")
    return (f"The circuit functions correctly with different trigger points "
            f"(rising {t1:.2f} V, falling {t2:.2f} V).")


# --------------------------------------------------------------------------
# Problems 23-24: VCO and PLL
# --------------------------------------------------------------------------

VCO_CONTROL = (0.6, 0.7, 0.8)


def check_vco(ctx: Ctx):
    nl = ctx.nl
    op = sanity_op(ctx, nl)
    check_io_nodes(ctx, op)
    freqs = []
    for vc in VCO_CONTROL:
        tb = replace_input(nl, "vin", f"dc {vc}", "Vtb_ctrl")
        r = ctx.sim(tb, "tran 1n 100u", saves=["v(vout)"])
        if not r.ok:
            ctx.fail("simulation", f"Transient analysis failed at Vin = {vc} V. Simulator output:\n" + r.error_text())
        t = np.real(r.plot.scale)
        y = np.real(r.plot.vec("vout"))
        m = t >= 20e-6
        t, y = t[m], y[m]
        pp = float(np.max(y) - np.min(y)) if len(y) else 0.0
        if pp < 0.1:
            ctx.fail("function", f"Vout does not oscillate at Vin = {vc} V (peak-to-peak swing {pp:.3g} V "
                     "between 20 us and 100 us, at least 0.1 V required).")
        cr = rising_crossings(t, y, (np.max(y) + np.min(y)) / 2)
        if len(cr) < 4:
            ctx.fail("function", f"Not enough oscillation periods at Vin = {vc} V: found {max(len(cr) - 1, 0)} "
                     "full period(s) between 20 us and 100 us, at least 3 required "
                     "(oscillation frequency must be above ~40 kHz).")
        per = np.diff(cr)
        if np.std(per) > 0.2 * np.mean(per):
            ctx.fail("function", f"The oscillation at Vin = {vc} V is not periodic "
                     f"(period spread {np.std(per) / np.mean(per):.0%}).")
        freqs.append(float(1 / np.median(per)))
    ctx.metrics["frequency_Hz"] = dict(zip(map(str, VCO_CONTROL), freqs))
    table = "\n".join(f"Vin = {vc} V: f = {f / 1e3:.4g} kHz" for vc, f in zip(VCO_CONTROL, freqs))
    d = np.diff(freqs)
    if not (np.all(d > 0) or np.all(d < 0)):
        ctx.fail("function", table + "\nThe voltage-controlled oscillator does not function correctly: "
                 "the oscillation frequency does not change monotonically with Vin.")
    span = abs(freqs[-1] - freqs[0]) / freqs[1]
    ctx.metrics["tuning_span"] = span
    if span < 0.10:
        ctx.fail("function", table + f"\nThe tuning range is too small: the frequency changes by only "
                 f"{span:.1%} for Vin = {VCO_CONTROL[0]} V .. {VCO_CONTROL[-1]} V (at least 10% required).")
    return table + "\nThe voltage-controlled oscillator functions correctly."


PLL_REF = 10e6
PLL_TRACK = 12e6


def pll_source(f: float, npulses: int | None = None) -> str:
    T = 1 / f
    s = f"dc 0 PULSE(0 1 30n {0.02 * T:g} {0.02 * T:g} {0.48 * T:g} {T:g}"
    return s + (f" {npulses})" if npulses else ")")


def _clk_freq(plot: Plot, t0: float, t1: float):
    t = np.real(plot.scale)
    y = np.real(plot.vec("clk_p"))
    m = (t >= t0) & (t <= t1)
    t, y = t[m], y[m]
    cr = all_crossings(t, y, 0.5)
    swing = float(np.max(y) - np.min(y)) if len(y) else 0.0
    if len(cr) < 3:
        return 0.0, len(cr), swing
    return float(1 / (2 * np.mean(np.diff(cr)))), len(cr), swing


def check_pll(ctx: Ctx):
    base = replace_input(ctx.nl, "clk_ref", pll_source(PLL_REF), "Vtb_ref")
    if ctx.nl.sources_at("clk_ref", "v"):
        ctx.notes.append("Your voltage source on clk_ref was replaced by the testbench reference clock.")
    op = sanity_op(ctx, base)
    check_io_nodes(ctx, op)
    for f in (PLL_REF, PLL_TRACK):
        tb = replace_input(ctx.nl, "clk_ref", pll_source(f), "Vtb_ref")
        r = ctx.sim(tb, "tran 10n 10u", saves=["v(clk_p)"])
        if not r.ok:
            ctx.fail("simulation", f"Transient analysis with a {f / 1e6:g} MHz reference failed. "
                     "Simulator output:\n" + r.error_text())
        fo, n, swing = _clk_freq(r.plot, 8e-6, 10e-6)
        ctx.metrics[f"clk_p_MHz_at_ref_{f / 1e6:g}MHz"] = fo / 1e6
        head = (f"REF Frequency : {f / 1e6:g} MHz\nOUT Frequency : {fo / 1e6:.4g} MHz "
                f"(measured on clk_p between 8 us and 10 us, swing {swing:.2f} V)\n")
        if swing < 0.5 or n < 8:
            ctx.fail("function", head + "The Phase-Locked Loop does not function correctly: clk_p does not "
                     "toggle (at least 0.5 V swing around 0.5 V required).")
        if not np.isclose(fo, f, rtol=0.05):
            ctx.fail("function", head + "The Phase-Locked Loop does not function correctly.\n"
                     f"When the clk_ref frequency is {f / 1e6:g} MHz, the output frequency should be "
                     f"{f / 1e6:g} MHz (within 5%).")
    # Hold-over: after the reference stops, a real PLL keeps oscillating (free-running VCO)
    tb = replace_input(ctx.nl, "clk_ref", pll_source(PLL_REF, 60), "Vtb_ref")
    r = ctx.sim(tb, "tran 10n 7u", saves=["v(clk_p)"])
    if not r.ok:
        ctx.fail("simulation", "Transient analysis (reference stopped at 6 us) failed. Simulator output:\n"
                 + r.error_text())
    _fo, n, swing = _clk_freq(r.plot, 6.2e-6, 7e-6)
    ctx.metrics["holdover_crossings"] = n
    if n < 6 or swing < 0.5:
        ctx.fail("function", "After the reference clock stops (at about 6 us), clk_p stops toggling. "
                 "The output must be produced by the loop's own oscillator (VCO) locked to clk_ref, "
                 "not derived directly from clk_ref.")
    return (f"REF Frequency : {PLL_REF / 1e6:g} MHz, OUT Frequency : "
            f"{ctx.metrics[f'clk_p_MHz_at_ref_{PLL_REF / 1e6:g}MHz']:.4g} MHz\n"
            "The Phase-Locked Loop functions correctly.")


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

R_TRANSISTOR = Rules(allowed_letters=set("rclmvi"), allow_user_subckt=False, allowed_x=set())
R_OPAMP = Rules(allowed_letters=set("rclmvix"), allow_user_subckt=False, allowed_x={OPAMP})
R_SYSTEM = Rules(allowed_letters=set("rclmvix"), allow_user_subckt=True, allowed_x=None)


@dataclass
class Task:
    id: int
    level: str
    circuit: str
    inputs: list[str]
    outputs: list[str]
    type: str
    submodule: str
    checker: Callable[[Ctx], str]
    rules: Rules
    libs: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"p{self.id:02d}"

    @property
    def problem_file(self) -> str:
        return os.path.join(PROBLEM_DIR, f"{self.name}.md")

    def lib_paths(self) -> dict[str, str]:
        return {lib: os.path.join(LIB_DIR, lib) for lib in self.libs}


def _t(i, level, circuit, inputs, outputs, typ, sub, checker, rules, libs=()):
    split = lambda s: [x.strip() for x in s.split(",") if x.strip() and x.strip() != "-"]
    return Task(i, level, circuit, split(inputs), split(outputs), typ, sub, checker, rules, list(libs))


TASKS: dict[int, Task] = {t.id: t for t in [
    _t(1, "Easy", "a single-stage common-source amplifier with resistive load R", "Vin", "Vout", "Amplifier", "SingleStageAmp", check_basic, R_TRANSISTOR),
    _t(2, "Easy", "A three-stage amplifier with single input and output (each stage is common-source with resistive load)", "Vin", "Vout", "Amplifier", "ThreeStageAmp", check_basic, R_TRANSISTOR),
    _t(3, "Easy", "A common-drain amplifier (a.k.a. a source follower) with resistive load R (output Vout at the source)", "Vin", "Vout", "Amplifier", "CommonDrainAmp", check_basic, R_TRANSISTOR),
    _t(4, "Easy", "A single-stage common-gate amplifier with resistive load R (input signal Vin must be applied at the source terminal)", "Vin, Vbias", "Vout", "Amplifier", "CommonGateAmp", check_basic, R_TRANSISTOR),
    _t(5, "Easy", "A single-stage cascode amplifier with two NMOS transistors provides a single-ended output through a resistive load R", "Vin, Vbias", "Vout", "Amplifier", "SingleStageCascodeAmp", check_basic, R_TRANSISTOR),
    _t(6, "Easy", "A NMOS inverter with resistive load R", "Vin", "Vout", "Inverter", "NMOSInverter", check_basic, R_TRANSISTOR),
    _t(7, "Easy", "A logical inverter with 1 NMOS and 1 PMOS", "Vin", "Vout", "Inverter", "LogicalInverter", check_basic, R_TRANSISTOR),
    _t(8, "Easy", "A simple NMOS constant current source with resistive load R", "Vbias", "Vout", "CurrentMirror", "NMOSConstantCurrentSource", check_basic, R_TRANSISTOR),
    _t(9, "Medium", "A two-stage amplifier with a Miller compensation capacitor", "Vin", "Vout", "Amplifier", "TwoStageOpampMiller", check_basic, R_TRANSISTOR),
    _t(10, "Medium", "A single-stage amplifier (common-source with PMOS diode-connected load (gate and drain are shorted))", "Vin", "Vout", "Amplifier", "CommonSourceAmpDiodeLoad", check_basic, R_TRANSISTOR),
    _t(11, "Medium", "A differential opamp with an active PMOS current mirror load, a tail current source, and two outputs", "Vinp, Vinn, Vbias", "Voutp, Vout", "Opamp", "SingleStageOpamp", check_basic, R_TRANSISTOR),
    _t(12, "Medium", "A cascode current mirror with 4 mosfets (2 stacked at input side with diode-connected, 2 stacked at output side), reference current source input Iref (connected to Vdd) and resistive load R", "Iref", "Iout", "CurrentMirror", "CascodeCurrentMirror", check_basic, R_TRANSISTOR),
    _t(13, "Medium", "A single-stage differential common-source opamp with dual resistive loads, tail current, and a single output", "Vinp, Vinn", "Vout", "Opamp", "SingleStageDiffCommonSourceOpamp", check_basic, R_TRANSISTOR),
    _t(14, "Hard", "A two-stage differential opamp (first stage: common-source with an active load and a tail current, second stage: common-source with an active load)", "Vinp, Vinn, Vbias1, Vbias2, Vbias3", "Voutp, Vout", "Opamp", "OpampResistanceLoad", check_basic, R_TRANSISTOR),
    _t(15, "Hard", "A single-stage telescopic cascode opamp with two outputs (4 nmos as cascode input pair, 4 pmos as cascode loads, and 1 tail current)", "Vinp, Vinn, Vbias1, Vbias2, Vbias3, Vbias4", "Voutp, Vout", "Opamp", "SingleStageDiffOpamp", check_basic, R_TRANSISTOR),
    _t(16, "Hard", "An RC phase-shift oscillator", "-", "Vout", "Oscillator", "Unknown", check_oscillator, R_OPAMP, ["opamp.lib"]),
    _t(17, "Hard", "A Wien Bridge oscillator", "-", "Vout", "Oscillator", "Unknown", check_oscillator, R_OPAMP, ["opamp.lib"]),
    _t(18, "Hard", "An Opamp integrator with resistor R1 and capacitor Cf", "Vin", "Vout", "Integrator", "Unknown", check_integrator, R_OPAMP, ["opamp.lib"]),
    _t(19, "Hard", "An Opamp differentiator with resistor Rf and capacitor C1", "Vin", "Vout", "Differentiator", "Unknown", check_differentiator, R_OPAMP, ["opamp.lib"]),
    _t(20, "Hard", "An Opamp adder to make Vout=-(Vin1+Vin2)", "Vin1, Vin2", "Vout", "Adder", "Unknown", check_adder, R_OPAMP, ["opamp.lib"]),
    _t(21, "Hard", "An Op-amp subtractor to make Vout=Vin2-Vin1", "Vin1, Vin2", "Vout", "Subtractor", "Unknown", check_subtractor, R_OPAMP, ["opamp.lib"]),
    _t(22, "Hard", "A non-inverting Schmitt trigger with positive feedback op-amp", "Vin", "Vout", "Schmitt", "Unknown", check_schmitt, R_OPAMP, ["opamp.lib"]),
    _t(23, "Hard", "A voltage-controlled oscillator", "Vin", "Vout", "VCO", "Unknown", check_vco, R_SYSTEM),
    _t(24, "Hard", "A phase-locked loop", "clk_ref", "clk_p", "PLL", "Unknown", check_pll, R_SYSTEM),
]}


def get_task(task: int | str) -> Task:
    if isinstance(task, str):
        s = task.lower().lstrip("p")
        task = int(s)
    if task not in TASKS:
        raise KeyError(f"unknown task {task} (valid: 1..24)")
    return TASKS[task]


def check(task: int | str, netlist_text: str, timeout: int = 300,
          keep_dir: str | None = None) -> Result:
    """Check a SPICE netlist (the full file content) against problem ``task``."""
    t = get_task(task)
    if not netlist_text or not netlist_text.strip():
        return Result(t.id, False, "input", "There is no netlist. Please write the complete SPICE netlist.")
    nl = Netlist.parse(netlist_text, libs=t.lib_paths())
    notes = list(nl.notes)
    errs = nl.errors + nl.validate(t.rules)
    if errs:
        return Result(t.id, False, "netlist", "The netlist violates the problem rules or could not be read:\n"
                      + "\n".join(errs), notes)
    if not nl.elements():
        return Result(t.id, False, "netlist", "The netlist contains no circuit elements. (Remember that the "
                      "first line of a SPICE file is the title line and is ignored.)", notes)
    ctx = Ctx(t, nl, timeout, keep_dir)
    ctx.notes = notes
    try:
        msg = t.checker(ctx) or "The design meets the target."
        return Result(t.id, True, "pass", msg, ctx.notes, ctx.metrics)
    except CheckFailed as exc:
        return Result(t.id, False, exc.stage, exc.message, ctx.notes, ctx.metrics)
    except Exception:  # pragma: no cover - testbench bug or unexpected data
        return Result(t.id, False, "internal", "The testbench could not evaluate this netlist:\n"
                      + traceback.format_exc(limit=3), ctx.notes, ctx.metrics)
