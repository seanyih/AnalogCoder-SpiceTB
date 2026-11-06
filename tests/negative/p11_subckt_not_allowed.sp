* task: 11  expect: netlist   (subcircuits are not allowed in problems 1-15)
.subckt half d g s
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
M1 d g s s nmos_model W=50u L=1u
.ends
Vdd Vdd 0 5
Vinp Vinp 0 2.5
Vinn Vinn 0 2.5
Vbias Vbias 0 1.5
X1 Voutp Vinp t half
X2 Vout Vinn t half
.end
