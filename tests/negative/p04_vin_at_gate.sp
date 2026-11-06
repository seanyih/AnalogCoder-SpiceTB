* task: 4  expect: operating-point   (input applied at the gate: common-source, not common-gate)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vbias Vbias 0 0
Vin Vin 0 1.5
M1 Vout Vin Vbias Vbias nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
