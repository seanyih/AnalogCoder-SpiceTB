* task: 1  expect: simulation   (gate node is floating -> no DC path)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vin Vin 0 1.5
C1 Vin g 1u
M1 Vout g 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
