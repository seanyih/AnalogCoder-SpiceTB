* task: 8  expect: function   (no current source: current depends on the load)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vbias Vbias 0 1.5
M1 Vbias Vbias 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
R2 Vout 0 1k
.end
