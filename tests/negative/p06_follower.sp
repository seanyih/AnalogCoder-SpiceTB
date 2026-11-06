* task: 6  expect: function   (source follower does not invert)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vin Vin 0 1.0
M1 Vdd Vin Vout 0 nmos_model W=50u L=1u
R1 Vout 0 1k
.end
