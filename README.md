# AnalogCoder-SpiceTB

A **SPICE-netlist** version of the 24-problem analog circuit design benchmark from
[AnalogCoder: Analog Circuit Design via Training-Free Code Generation](https://arxiv.org/abs/2405.14918)
(Lai et al., AAAI 2025, [original repo](https://github.com/laiyao1/AnalogCoder)).

In the original benchmark, the LLM writes **PySpice** (Python) code. Here it writes a plain
**ngspice netlist** instead, and the testbenches are re-implemented around the ngspice
command-line simulator. This repository contains:

| Path | Contents |
|---|---|
| `problems/p01.md` ... `problems/p24.md` | The 24 problem descriptions: the original task text, node names, design rules, and what the testbench checks. These are what the model sees. |
| `problems/lib/opamp.lib` | The `SingleStageOpamp` subcircuit provided for problems 16 to 22. |
| `checkers/check_p01.py` ... `check_p24.py` | One independent checker entry point per problem. |
| `spicetb/` | The shared testbench: netlist reader and rule checks, ngspice runner, and the 24 checks (`spicetb/tasks.py`). |
| `reference/p01.sp` ... `p24.sp` | Reference solutions translated from AnalogCoder's `sample_design/`. All pass. |
| `tests/` | Self-test: every reference must pass, and every netlist in `tests/negative/` (wrong designs and cheating attempts) must fail at the expected stage. |
| `run_opencode.py` | Benchmark harness for [opencode](https://opencode.ai) agents, with optional feedback loops. |
| `agent/AGENTS.md` | Default agent instructions (background, deliverable, no-cheating rules). Customisable. |
| `scripts/install_ngspice.sh` | Installs ngspice: package manager first, otherwise a source build into `third_party/ngspice`. |
| `scripts/gen_problems.py` | Regenerates `problems/*.md` from the task registry. |

## Requirements

- Python 3.10 or newer, with `numpy` and `scipy` (`pip install -r requirements.txt`).
- [ngspice](https://ngspice.sourceforge.io), open source (BSD-3-Clause). The testbench was
  developed with ngspice 42. Install it with `apt install ngspice`, `brew install ngspice`,
  `conda install -c conda-forge ngspice`, or `scripts/install_ngspice.sh`. That script falls back
  to building the official source release into `third_party/ngspice/`, which the testbench finds
  automatically. You can also point `$NGSPICE` at any ngspice binary.
- Only for the agent harness: [opencode](https://opencode.ai) (`npm i -g opencode-ai`), configured
  with a model provider.

## Quick start

```bash
pip install -r requirements.txt
```

```bash
scripts/install_ngspice.sh
```

```bash
python -m spicetb list
```

```bash
python -m spicetb show -t 9
```

```bash
python checkers/check_p09.py my_design.sp
```

```bash
python -m spicetb check -t 9 my_design.sp --json
```

```bash
python -m spicetb selftest
```

```bash
python -m pytest tests
```

`list` prints the 24 problems and `show -t 9` prints a problem description. The two
`check` commands are equivalent: one uses the problem's own entry point, the other the
unified CLI. `selftest` checks all 24 reference designs, and `pytest` runs the references
plus the negative cases.

A checker exits with status **0 = pass**, **1 = fail**, or **2 = usage/environment error**. It
prints a report: which stage failed, plus the simulator errors or the diagnostic from the failed
check. `--keep DIR` keeps every generated ngspice deck and log for debugging.

From Python:

```python
from spicetb import check
res = check(9, open("my_design.sp").read())
res.passed, res.stage, res.feedback(), res.metrics
```

## The problems

| Id | Level | Circuit | Inputs | Outputs | Check type |
|---|---|---|---|---|---|
| 1 | Easy | Single-stage common-source amplifier with resistive load R | Vin | Vout | Amplifier |
| 2 | Easy | Three-stage amplifier (common-source stages with resistive loads) | Vin | Vout | Amplifier |
| 3 | Easy | Common-drain amplifier (source follower) with resistive load R | Vin | Vout | Amplifier |
| 4 | Easy | Common-gate amplifier with resistive load R (Vin at the source) | Vin, Vbias | Vout | Amplifier |
| 5 | Easy | Single-stage cascode amplifier (two NMOS) with resistive load R | Vin, Vbias | Vout | Amplifier |
| 6 | Easy | NMOS inverter with resistive load R | Vin | Vout | Inverter |
| 7 | Easy | Logical inverter with 1 NMOS and 1 PMOS | Vin | Vout | Inverter |
| 8 | Easy | Simple NMOS constant current source with resistive load R | Vbias | Vout | Current source |
| 9 | Medium | Two-stage amplifier with Miller compensation capacitor | Vin | Vout | Amplifier |
| 10 | Medium | Common-source amplifier with PMOS diode-connected load | Vin | Vout | Amplifier |
| 11 | Medium | Differential opamp, active PMOS mirror load, tail current, two outputs | Vinp, Vinn, Vbias | Voutp, Vout | Opamp |
| 12 | Medium | Cascode current mirror (4 MOSFETs), reference current Iref, load R | Iref | Iout | Current mirror |
| 13 | Medium | Differential common-source opamp, dual resistive loads, tail current | Vinp, Vinn | Vout | Opamp |
| 14 | Hard | Two-stage differential opamp with active loads | Vinp, Vinn, Vbias1-3 | Voutp, Vout | Opamp |
| 15 | Hard | Telescopic cascode opamp, two outputs | Vinp, Vinn, Vbias1-4 | Voutp, Vout | Opamp |
| 16 | Hard | RC phase-shift oscillator | - | Vout | Oscillator (op-amp) |
| 17 | Hard | Wien bridge oscillator | - | Vout | Oscillator (op-amp) |
| 18 | Hard | Op-amp integrator with R1 and Cf | Vin | Vout | Integrator |
| 19 | Hard | Op-amp differentiator with Rf and C1 | Vin | Vout | Differentiator |
| 20 | Hard | Op-amp adder, Vout = -(Vin1 + Vin2) | Vin1, Vin2 | Vout | Adder |
| 21 | Hard | Op-amp subtractor, Vout = Vin2 - Vin1 | Vin1, Vin2 | Vout | Subtractor |
| 22 | Hard | Non-inverting Schmitt trigger with positive feedback | Vin | Vout | Schmitt |
| 23 | Hard | Voltage-controlled oscillator | Vin | Vout | VCO |
| 24 | Hard | Phase-locked loop | clk_ref | clk_p | PLL |

Problems 1 to 15 are transistor-level circuits (level-1 MOSFETs, 5 V supply, no subcircuits).
Problems 16 to 22 are built around the provided op-amp (`.include opamp.lib`). Problems 23 and 24
are transistor-level systems where the designer may define their own subcircuits.

## What a submission looks like

A complete ngspice netlist. The first line is the title. Analysis cards are ignored.

```spice
* single-stage common-source amplifier
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5.0
Vin Vin 0 1.5
M1 Vout Vin 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
```

## How the testbenches work

Every check generates its own ngspice decks: your netlist, plus testbench sources and modified
values, plus one analysis. ngspice runs each deck in batch mode and the results are read from the
binary raw file. Stages, in order:

1. **netlist**: the file is parsed and the problem's rules are enforced (see below).
2. **simulation**: the DC operating point must solve without simulator errors. For problems 1 to 15,
   a node without a DC path (`singular matrix: check node X`) also fails here. The input and output
   node names must exist.
3. **operating-point** (problems 1 to 15, except the inverters): a port of AnalogCoder's
   `check_netlist`. Every MOSFET is checked for V_DS polarity, V_GS beyond threshold, and gate not
   tied to source, plus the topology rules: a resistor must be present, the common-gate input must
   be at the source, the common-drain output must be at the source, the Miller capacitor must sit
   between the first-stage output and Vout, and the diode-connected load must exist. For amplifiers
   and opamps, the input is first auto-biased by a 0 to 5 V DC sweep, choosing the input voltage
   that puts Vout closest to 2.5 V, as in the original.
4. **function**: the per-type functional test.

| Type | Functional test (summary; full details in each `problems/pNN.md`) |
|---|---|
| Amplifier | All MOSFETs have I_D ≥ 10 µA. AC gain at 100 Hz with 1 µV on Vin is > 1e-5. |
| Opamp | All MOSFETs have I_D ≥ 10 µA. Differential gain > common-mode gain at 100 Hz, and differential gain > 1e-5. |
| Inverter | Vout(Vin = 5 V) ≤ 2.5 V, Vout(Vin = 0 V) ≥ 2.5 V, difference ≥ 1 V. |
| Current source/mirror | Load swept over 100 to 1000 Ω: current > 10 µA and constant to within 1 µA. Problem 12 only: Iref → 1.55 mA must change the output current. |
| Oscillator | 10 ms transient from a small initial imbalance on the op-amp inputs. More than 3 filtered peaks, period spread < 20 %, amplitude > 1 µV. |
| Integrator | R1 = 10 k, Cf = 3 µ, ±0.5 V square wave around 2.5 V. Ramp slope 16.7 V/s ± 30 %, r² ≥ 0.9. Must stop integrating with the op-amp removed. |
| Differentiator | Rf = 10 k, C1 = 3 µ, ±20 V/s triangle wave. Output is a square wave 2.5 ± 0.6 V (± 20 %). Must stop working with the op-amp removed. |
| Adder | Vout − 2.5 = −[(Vin1 − 2.5) + (Vin2 − 2.5)] within 20 %, for Vin2 = 2.625 V and Vin1 swept 2.5 to 3.0 V. |
| Subtractor | Vout = Vin2 − Vin1 within 20 %, for Vin2 = 5 V and Vin1 swept 2.75 to 3.25 V. |
| Schmitt | Up and down DC sweeps: thresholds differ by > 50 mV, output swing ≥ 2.5 V, monotonic non-inverting. |
| VCO | Vin = 0.6, 0.7, 0.8 V: Vout oscillates (≥ 3 periods in 20 to 100 µs, swing ≥ 0.1 V, regular). Frequency monotonic in Vin with ≥ 10 % tuning. |
| PLL | clk_ref provided by the testbench. clk_p locks to 10 MHz and to 12 MHz (within 5 %, measured over 8 to 10 µs). Keeps toggling after the reference stops (hold-over). |

### Rules enforced on submissions (anti-cheating)

- No `.control` blocks (they can run shell commands), no `.option(s)`/`.temp`, and no `.include`/`.lib`
  of anything except the problem's own library files.
- Independent sources must be DC only: no `AC`, `PULSE`, `SIN`, `PWL`, etc. Otherwise an "oscillator"
  could just be a sine source.
- Allowed element types: R, C, L, M, V, I. X (subcircuit instances) is additionally allowed for
  problems 16 to 24: only `SingleStageOpamp` in 16 to 22, user-defined subcircuits in 23 and 24.
  Controlled and behavioural sources (E, F, G, H, B), switches, XSPICE models, diodes and BJTs are
  rejected, so an ideal VCVS cannot stand in for an amplifier.
- MOSFET models must be level 1. The provided op-amp cannot be redefined.
- Problems 18 and 19 require the feedback element (`Cf` or `Rf`) between the op-amp's inverting
  input and its output. They also re-run the test with the op-amp removed, to reject passive RC
  networks.
- Problem 24 rejects a buffered copy of `clk_ref` (hold-over test) and a free-running VCO trimmed to
  10 MHz (12 MHz tracking test). Both would pass the original 10 MHz-only check.

The negative test cases in `tests/negative/` show each of these in action.

## Running agents with opencode

`run_opencode.py` evaluates an opencode agent on any subset of the problems.

```bash
npm i -g opencode-ai
```

```bash
python run_opencode.py -m anthropic/claude-sonnet-4-5 --all --trials 5 --jobs 4
```

```bash
python run_opencode.py -m openai/gpt-5 -t 9 -t 14 --feedback binary --max-rounds 5
```

```bash
python run_opencode.py -m opencode/big-pickle --all --feedback error --max-rounds 5
```

```bash
python run_opencode.py -m anthropic/claude-sonnet-4-5 --all --agents my_rules.md --allow-bash
```

In order: install opencode; run one round with no feedback; use binary feedback; use full
testbench feedback; and use custom agent rules while letting the agent run ngspice itself.

**What the model sees.** Each run gets a fresh workspace in the system temp directory. It is
outside this repository and is its own git root, so the agent cannot reach the testbench or the
reference designs. The workspace contains only:

- `AGENTS.md`: the agent rules (default `agent/AGENTS.md`, or the file passed with `--agents`).
  opencode loads it automatically as project instructions. The default gives a generic analog-design
  background, the deliverable (write `solution.sp`), a SPICE example, and the no-cheating rules.
- `opencode.json`: permissions. Editing is allowed. Web fetch, web search, access outside the
  workspace and questions to the user are denied. Shell commands are denied unless `--allow-bash`
  is given, in which case a note saying that ngspice may be used is appended to the workspace
  `AGENTS.md`.
- The library files the problem provides (`opamp.lib` for problems 16 to 22).

The **only user message** is the problem description, `problems/pNN.md`.

**Feedback modes** (`--feedback`). Each later round continues the same opencode session.

| Mode | Behaviour |
|---|---|
| `none` (default) | One round. The agent's `solution.sp` is checked once. |
| `binary` | On failure the agent receives exactly the one word `wrong`: no reason, no diagnosis. Repeats up to `--max-rounds`. |
| `error` | On failure the agent receives the testbench report: the failed stage, simulator error messages (for example floating nodes or syntax errors), and the failed check's diagnostic (for example the operating-point violations or the measured vs. expected values). Repeats up to `--max-rounds`. |

**Outputs** go to `runs/<timestamp>/` (or `--out`):

- `pNN/trialK/roundR_solution.sp`, `roundR_result.json`, `roundR_opencode.jsonl` (the opencode
  event log, for auditing) and `roundR_feedback.txt`.
- `results.jsonl`, plus `summary.md` with Pass@1 (first round), pass rate within the round budget,
  and #Solved per problem.

Note that opencode still reads your global configuration and global rules
(`~/.config/opencode/`). Keep those neutral when benchmarking.

## Differences from the original AnalogCoder testbench

The checks follow `gpt_run.py` and `problem_check/*.py` in the original repository, including
their (lenient) thresholds. Deliberate changes:

1. **Language and simulator.** The design is a SPICE netlist, simulated with the ngspice CLI, not
   PySpice code. Elements are found by **node** (for example "the voltage source on node Vin") rather
   than by substring matches on PySpice element names. Input/output node presence is an exact match.
2. **Element and construct restrictions** (listed above). The original accepted any PySpice code.
3. **Op-amp bias.** Problems 16 to 22 use a fixed 2.5 V operating point (the original took it from a
   retrieval step or the model's own source). The provided op-amp is AnalogCoder's `SingleStageOpamp`
   (`subcircuit_lib/p11_lib.py`).
4. **Floating nodes** are fatal only for the DC/AC problems 1 to 15. ngspice 42 falls back to a
   transient operating point otherwise. AnalogCoder's own RC phase-shift sample has such a node and
   oscillates fine.
5. **Current mirror.** The load is the resistor attached to the output node (the original took the
   first resistor in the netlist). Current magnitudes are compared. The Iref test uses the intended
   500 Ω load (the original divided by 1000 Ω). Problem 12 requires the Iref current source to exist
   (the original silently passed without one).
6. **Miller capacitor check** (problem 9) accepts any capacitor between any Vin-driven drain and Vout
   (the original looked only at the last capacitor and the last such MOSFET).
7. **Integrator and differentiator.** Elements must be named exactly `R1`/`Cf` and `Rf`/`C1` (the
   original matched name prefixes). The feedback element must close the op-amp feedback loop (new).
   The passive-circuit re-test removes all op-amp instances. The differentiator's passive re-test had
   inverted exit codes in the original and is fixed. "Square wave" is judged relative to the 2.5 V
   bias, because the original absolute comparison also accepted a triangle wave passed straight
   through.
8. **Oscillator.** The FIR filter is applied to Vout resampled on a uniform 1 µs grid (the original
   applied it to raw, non-uniform simulator time points).
9. **Schmitt trigger.** The monotonicity test tolerates 1 µV of numerical noise.
10. **VCO (23) and PLL (24).** The original pipeline never ran `VCO.py`/`PLL.py` automatically, and
    both scripts were specific to the sample circuits (hard-coded internal node names and initial
    conditions). `VCO.py`'s period comparison did not test monotonicity, and `PLL.py` exited 0 even on
    failure. They are replaced by the general tests above. The control voltages (0.6 to 0.8 V), the
    1 V PLL supply and clock swing, the 10 MHz reference and the 10 µs window follow the originals.
    The MOSFET region check is not applied to these two problems.

## Reference designs

`reference/*.sp` are hand translations of AnalogCoder's `sample_design/p*.py`, with the same
devices, sizes and bias values. Changes:

- **p23**: adds a 1 pF load capacitor on `vout`. Without it, ngspice 42 aborts the comparator's hard
  switching at some control voltages with "timestep too small".
- **p24**: the PySpice class hierarchy (PFD, D flip-flops, NAND, charge pump, loop filter, ring VCO)
  is flattened into uniquely named `.subckt`s. Per-instance `kp` values become separate subcircuits.
  The checker's original initial conditions are included as an `.ic` card.

## Citation

If you use this benchmark, please cite the original AnalogCoder paper:

```bibtex
@article{lai2025analogcoder,
  title   = {AnalogCoder: Analog Circuit Design via Training-Free Code Generation},
  author  = {Lai, Yao and Lee, Sungyoung and Chen, Guojin and Poddar, Souradip and Hu, Mengkang and Pan, David Z. and Luo, Ping},
  journal = {Proceedings of the AAAI Conference on Artificial Intelligence},
  volume  = {39}, number = {1}, pages = {379--387}, year = {2025},
  doi     = {10.1609/aaai.v39i1.32016}
}
```

The problem set, sample designs and op-amp subcircuit come from
[laiyao1/AnalogCoder](https://github.com/laiyao1/AnalogCoder) (MIT License).
