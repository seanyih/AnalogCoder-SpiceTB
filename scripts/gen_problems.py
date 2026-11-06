#!/usr/bin/env python3
"""(Re)generate problems/pNN.md from the task registry.

The problem files are plain Markdown and may be edited by hand; this script
only exists to keep the 24 files consistent.  Run it from the repository root:

    python scripts/gen_problems.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from spicetb.tasks import PLL_REF, PLL_TRACK, TASKS, VCO_CONTROL  # noqa: E402

MODELS = """```spice
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
```"""

SPICE_FORMAT = """\
## Netlist format

- Submit one complete SPICE netlist in **ngspice** syntax. As usual in SPICE, the
  **first line is the title line and is ignored**; start the file with a `*` comment.
- Node names are case-insensitive; `0` (or `gnd`) is ground.
- MOSFET card: `Mname drain gate source bulk model W=<w> L=<l>`. The terminal order matters.
- Independent sources must be plain DC sources (`Vx n+ n- <value>` or `... dc <value>`).
  AC magnitudes, `PULSE`, `SIN`, `PWL`, ... are not allowed. The testbench applies all
  stimuli itself.
- Analysis and output cards (`.op`, `.ac`, `.dc`, `.tran`, `.print`, `.meas`, ...) are
  ignored, because the testbench runs its own analyses. `.control` blocks, `.option(s)`,
  `.temp` and including any file other than the ones provided for this problem are rejected.
- `.model`, `.param`, `.func`, `.ic`, `.nodeset`, `.global` and `.end` are allowed.
"""


def node_line(label, nodes):
    return f"**{label} node name{'s' if len(nodes) > 1 else ''}:** " + (
        ", ".join(f"`{n}`" for n in nodes) if nodes else "none")


def transistor_rules(t):
    letters = "R, C, L, M (MOSFET), V and I (independent DC sources)"
    lines = [
        "## Design rules",
        "",
        "- Use level-1 MOSFET models with these parameters:",
        "",
        MODELS,
        "",
        "- Supply: a 5.0 V independent DC source on node `Vdd` (`Vdd Vdd 0 5.0`).",
        "- Connect the bulk of each MOSFET to its source.",
        "- Use the MOSFET threshold voltage (0.5 V) when you choose bias voltages.",
        "- Use nominal transistor sizing (e.g. `W=50u L=1u`).",
        "- Do not use subcircuits.",
        f"- Allowed element types: {letters}. Controlled/behavioural sources (E, F, G, H, B),"
        " switches, diodes, BJTs and subcircuit instances (X) are rejected.",
        "- Make sure all the input and output node names above appear in the circuit.",
    ]
    if t.type in ("Amplifier", "Opamp", "Inverter"):
        ins = [n for n in t.inputs if n.lower() in ("vin", "vinp", "vinn")]
        lines.append("- Drive " + " and ".join(f"`{n}`" for n in ins) +
                     " with " + ("its own " if len(ins) == 1 else "separate ") +
                     "DC voltage source" + ("" if len(ins) == 1 else "s") +
                     " to ground (for example `Vin Vin 0 1.0`). Just set up the operating point;"
                     " do not add AC sources.")
    if [n for n in t.inputs if n.lower().startswith("vbias")]:
        lines.append("- Bias inputs (`Vbias...`) are DC voltage sources to ground that you choose.")
    if t.id == 12:
        lines.append("- The reference current is an independent current source from `Vdd` into node "
                     "`Iref` (for example `Iref Vdd Iref 1m`).")
    if t.type == "CurrentMirror":
        lines.append(f"- The load resistor R connects the output node `{t.outputs[0]}` to `Vdd`. "
                     f"It must be the (first) resistor attached to `{t.outputs[0]}`.")
    return "\n".join(lines)


OPAMP_INFO = """\
## Provided subcircuit

You can use this op-amp subcircuit directly. It is defined in the library file
`opamp.lib`, which sits next to this problem description:

| Subcircuit | Type | Differential-mode gain | Ports (in order) |
|---|---|---|---|
| `SingleStageOpamp` | Opamp | very high (ideal-like, level-1 MOSFETs with no channel-length modulation) | `Vinp Vinn Vout` |

- `Vinp` is the non-inverting input and `Vinn` is the inverting input.
- The DC operating voltage for `Vinn`/`Vinp` is **2.5 V**. The op-amp is supplied
  internally from 5 V, so the output range is about 0 to 5 V. You do not need to add a
  power supply for the subcircuit.
- Because of that operating range, connect nodes that would normally be grounded
  (signal references) to a **2.5 V DC source** instead.

To use it, insert:

```spice
.include opamp.lib
* Xname <non-inverting input> <inverting input> <output> SingleStageOpamp
Xop1 Vinp Vinn Vout SingleStageOpamp
```
"""


def opamp_rules(t, extra=()):
    lines = [
        "## Design rules",
        "",
        "- Build the circuit around the provided `SingleStageOpamp` (at least one instance).",
        "- Allowed element types: R, C, L, M, V and I (DC sources only), plus X instances of "
        "`SingleStageOpamp`. Do not define your own subcircuits, and do not redefine the provided one.",
        "- Make sure all the input and output node names above appear in the circuit.",
    ]
    lines += list(extra)
    return "\n".join(lines)


def system_rules(t, extra=()):
    lines = [
        "## Design rules",
        "",
        "- Transistor-level design: allowed element types are R, C, L, M (level-1 MOSFET models; "
        "you choose the parameters), V and I (DC sources only) and X instances of subcircuits that "
        "you define yourself with `.subckt`.",
        "- Controlled/behavioural sources (E, F, G, H, B), switches, XSPICE code models, diodes and BJTs "
        "are rejected.",
        "- You may add `.ic` / `.nodeset` cards to help the circuit start up.",
        "- Make sure all the input and output node names above appear in the circuit.",
    ]
    lines += list(extra)
    return "\n".join(lines)


COMMON_EVAL = ("The netlist must simulate without errors. In particular, nodes without a DC path to "
               "ground (\"floating\" nodes) are an error. The input and output nodes must exist.")


def region_text(t):
    s = ["Operating-point check of every MOSFET (threshold 0.5 V):",
         "   - NMOS: V(drain) > V(source), drain not at 0 V or tied to ground, and V(gate) > V(source) + 0.5 V;",
         "   - PMOS: V(drain) < V(source), drain not at Vdd or tied to `Vdd`, and V(gate) < V(source) - 0.5 V;",
         "   - a MOSFET whose gate is tied to its own source is rejected."]
    extra = {
        3: "   - `Vout` must be at the source of the transistor (not at a drain or gate).",
        4: "   - `Vin` must be applied at the source terminal (not at a drain or gate).",
        9: "   - a capacitor (Miller compensation) must connect the drain of the transistor driven by "
           "`Vin` (the first-stage output) to `Vout`.",
        10: "   - a diode-connected transistor (gate shorted to drain) must be present.",
    }
    if t.id in (1, 2, 3, 4, 5, 8, 13):
        s.append("   - the circuit must contain a resistor.")
    if t.id in extra:
        s.append(extra[t.id])
    if t.type == "Opamp":
        s.append("   - the DC voltages of `Vinp` and `Vinn` must be equal.")
    return "\n".join(s)


def evaluation(t):
    b = "## How the design is evaluated\n\n"
    b += "The testbench runs ngspice on your netlist and checks, in order:\n\n"
    if t.type == "Amplifier":
        items = [COMMON_EVAL,
                 "**Automatic input biasing.** The `Vin` source is swept from 0 V to 5 V. If `Vout` does "
                 "not change (by at least 1 mV) the design fails. Otherwise the DC value of `Vin` is reset to "
                 "the value where `Vout` is closest to 2.5 V.",
                 region_text(t),
                 "Every MOSFET conducts a drain current of at least 10 uA.",
                 "**AC check.** A 1 uV AC signal is applied on `Vin`. The magnitude of `Vout` at 100 Hz must be "
                 "non-zero (gain > 1e-5)."]
    elif t.type == "Opamp":
        items = [COMMON_EVAL,
                 "**Automatic input biasing.** `Vinp` is tied to `Vinn` and the `Vinn` source is swept from "
                 "0 V to 5 V. If `Vout` does not change the design fails. Otherwise both input sources are "
                 "reset to the common-mode voltage where `Vout` is closest to 2.5 V.",
                 region_text(t),
                 "Every MOSFET conducts a drain current of at least 10 uA.",
                 "**AC check at 100 Hz.** The common-mode gain (1 uV AC on both inputs, in phase) must be "
                 "smaller than the differential-mode gain (`Vinn` driven 180 degrees out of phase), and "
                 "the differential gain must be non-zero (> 1e-5). The output is `Vout`."]
    elif t.type == "Inverter":
        items = [COMMON_EVAL,
                 "The `Vin` source is set to 5 V and then to 0 V (DC operating points). The design passes if "
                 "Vout(Vin = 5 V) <= 2.5 V, Vout(Vin = 0 V) >= 2.5 V, and the difference is at least 1 V."]
    elif t.type == "CurrentMirror":
        items = [COMMON_EVAL, region_text(t),
                 f"The load resistor on `{t.outputs[0]}` is set to 100, 300, 500, 750 and 1000 Ohm. The current "
                 "through it must exceed 10 uA in every case, and it must stay constant, to within 1 uA, "
                 "between at least one pair of neighbouring load values."]
        if t.id == 12:
            items.append("With a 500 Ohm load the reference source `Iref` is changed to 1.55 mA. The output "
                         "current must change by more than 1 uA (the circuit must mirror Iref).")
    elif t.type == "Oscillator":
        items = [COMMON_EVAL,
                 "Initial conditions are placed on the op-amp inputs (non-inverting 2.51 V, inverting "
                 "2.5 V) of the first `SingleStageOpamp` instance, and a 10 ms transient is run "
                 "(1 us step).",
                 "`Vout` is low-pass filtered (51-tap FIR, cut-off about 10 kHz). The design passes if there are "
                 "more than 3 peaks, the larger half of the peak-to-trough amplitudes are all above 1 uV, and "
                 "the standard deviation of the peak-to-peak periods is below 20% of their mean. In practice "
                 "the oscillation frequency should lie between about 0.5 kHz and 10 kHz."]
    elif t.type == "Integrator":
        items = [COMMON_EVAL,
                 "`R1` must exist, and `Cf` must connect the op-amp's inverting input to its output.",
                 "The testbench replaces the source on `Vin` with a square wave from 2.0 V to 3.0 V "
                 "(around the 2.5 V operating point, 20 ms period). It sets R1 = 10 kOhm and Cf = 3 uF, "
                 "then runs a 200 ms transient.",
                 "The slope of `Vout` on the last ramp must be within 30% of 0.5 V / (R1*Cf) = 16.7 V/s, "
                 "and the ramp must be linear (r^2 >= 0.9).",
                 "The same test is repeated with the op-amp removed. If the circuit still integrates "
                 "(slope within 50%) it is considered passive and fails."]
    elif t.type == "Differentiator":
        items = [COMMON_EVAL,
                 "`C1` must exist, and `Rf` must connect the op-amp's inverting input to its output.",
                 "The testbench replaces the source on `Vin` with a triangle wave from 2.0 V to 3.0 V "
                 "(100 ms period, slope +/-20 V/s). It sets Rf = 10 kOhm and C1 = 3 uF, then runs a "
                 "200 ms transient.",
                 "`Vout` must be a square wave centred on 2.5 V with an amplitude of 0.6 V "
                 "(= Rf*C1*20 V/s), within 20%, and symmetric within 20%.",
                 "The same test is repeated with the op-amp removed. If the circuit still produces that "
                 "square wave it is considered passive and fails."]
    elif t.type == "Adder":
        items = [COMMON_EVAL,
                 "All signals are referenced to the 2.5 V operating point: "
                 "Vout - 2.5 = -[(Vin1 - 2.5) + (Vin2 - 2.5)].",
                 "The testbench replaces the sources on `Vin1`/`Vin2`, sets Vin2 = 2.625 V and sweeps "
                 "Vin1 from 2.5 V to 3.0 V (DC, 10 mV steps). At every point `Vout` must match the expected "
                 "value within 20%."]
    elif t.type == "Subtractor":
        items = [COMMON_EVAL,
                 "Vout = Vin2 - Vin1 (absolute voltages, ground referenced).",
                 "The testbench replaces the sources on `Vin1`/`Vin2`, sets Vin2 = 5.0 V and sweeps Vin1 from "
                 "2.75 V to 3.25 V (DC, 50 mV steps). At every point `Vout` must match the expected value "
                 "within 20%."]
    elif t.type == "Schmitt":
        items = [COMMON_EVAL,
                 "Your `Vin` source is swept up (0 V to 5 V) and down (5 V to 0 V) in 0.1 V DC steps.",
                 "In both directions `Vout` must cross 2.5 V, rise by at least 2.5 V over the sweep, and "
                 "never decrease as Vin increases (non-inverting).",
                 "The input voltages where `Vout` first exceeds 2.5 V in the two sweeps (the switching "
                 "thresholds) must differ by more than 0.05 V (hysteresis)."]
    elif t.type == "VCO":
        vc = ", ".join(f"{v} V" for v in VCO_CONTROL)
        items = [COMMON_EVAL,
                 f"The testbench drives `Vin` with the control voltages {vc} (it replaces your source "
                 "on `Vin`). For each one it runs a 100 us transient (1 ns step).",
                 "Between 20 us and 100 us `Vout` must swing by at least 0.1 V and show at least 3 full "
                 "periods (frequency above about 40 kHz), with a period spread below 20%.",
                 "The oscillation frequency must change monotonically with `Vin` (in either direction), "
                 f"and f({VCO_CONTROL[-1]} V) and f({VCO_CONTROL[0]} V) must differ by at least 10% "
                 f"of f({VCO_CONTROL[1]} V)."]
    elif t.type == "PLL":
        items = ["The testbench drives `clk_ref` with a 0 V to 1 V clock (30 ns delay, 2% rise/fall "
                 "time, 48% high time). It replaces any source you put on `clk_ref`.",
                 COMMON_EVAL,
                 f"**Lock.** With a {PLL_REF / 1e6:g} MHz reference, a 10 us transient is run. Measured "
                 f"between 8 us and 10 us, `clk_p` must swing at least 0.5 V around its 0.5 V crossings, "
                 f"and its frequency must be within 5% of {PLL_REF / 1e6:g} MHz.",
                 f"**Tracking.** The same must hold with a {PLL_TRACK / 1e6:g} MHz reference.",
                 "**Hold-over.** The reference stops after 60 cycles (about 6 us). `clk_p` must keep "
                 "toggling between 6.2 us and 7.0 us, so the output must come from the loop's own "
                 "oscillator and not directly from `clk_ref`."]
    return b + "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))


def render(t):
    title = t.circuit[0].upper() + t.circuit[1:]
    out = [f"# Problem {t.id}: {title}", "",
           f"*Difficulty: {t.level} | Type: {t.type}*", "",
           "## Task", "",
           f"Design {t.circuit[0].lower() + t.circuit[1:]}.", "",
           node_line("Input", t.inputs) + "  ",
           node_line("Output", t.outputs), ""]
    if t.type in ("Amplifier", "Opamp", "Inverter", "CurrentMirror"):
        out.append(transistor_rules(t))
    elif t.type in ("Oscillator", "Integrator", "Differentiator", "Adder", "Subtractor", "Schmitt"):
        out.append(OPAMP_INFO)
        extra = {
            "Oscillator": ["- Increase the loop gain enough that the oscillation starts and keeps going."],
            "Integrator": ["- Name the input resistor `R1` and the feedback capacitor `Cf` "
                           "(`Cf` between the op-amp's inverting input and its output). The input "
                           "signal enters through `R1`."],
            "Differentiator": ["- Name the input capacitor `C1` and the feedback resistor `Rf` "
                               "(`Rf` between the op-amp's inverting input and its output). The input "
                               "signal enters through `C1`."],
            "Adder": ["- Drive `Vin1` and `Vin2` with DC voltage sources to ground."],
            "Subtractor": ["- Drive `Vin1` and `Vin2` with DC voltage sources to ground."],
            "Schmitt": ["- Drive `Vin` with a DC voltage source to ground. The trigger is "
                        "non-inverting: `Vout` goes high when `Vin` is high."],
        }[t.type]
        if t.type in ("Integrator", "Differentiator", "Schmitt"):
            extra = ["- Drive `Vin` with a DC voltage source to ground (2.5 V operating point)."] + extra \
                if t.type != "Schmitt" else extra
        out.append(opamp_rules(t, extra))
    elif t.type == "VCO":
        out.append(system_rules(t, [
            "- Choose your own supply voltage (at most 5 V) and add it as a DC source.",
            "- `Vin` is the control voltage. Drive it with a DC source to ground (for example "
            "`Vin Vin 0 0.7`). The testbench replaces this source with its own control voltages.",
            "- `Vout` must oscillate. Its frequency must depend on `Vin`.",
        ]))
    elif t.type == "PLL":
        out.append(system_rules(t, [
            "- Supply: 1.0 V on node `vdd` (`VDD vdd 0 1`). The reference clock swings from 0 V to 1 V.",
            "- `clk_ref` is the reference clock input, which the testbench provides. Do not drive it yourself.",
            "- `clk_p` is the PLL output clock, swinging around 0.5 V. It must lock to `clk_ref` with a "
            "1:1 frequency ratio.",
        ]))
    out += ["", SPICE_FORMAT, evaluation(t), ""]
    return "\n".join(out)


def main():
    os.makedirs(os.path.join(ROOT, "problems"), exist_ok=True)
    for t in TASKS.values():
        with open(t.problem_file, "w") as fh:
            fh.write(render(t))
        print("wrote", os.path.relpath(t.problem_file, ROOT))


if __name__ == "__main__":
    main()
