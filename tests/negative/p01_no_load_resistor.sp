* task: 1  expect: operating-point   (PMOS current-source load instead of the resistor R)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd Vdd 0 5
Vin Vin 0 1
Vb Vb 0 4
M1 Vout Vin 0 0 nmos_model W=50u L=1u
M2 Vout Vb Vdd Vdd pmos_model W=50u L=1u
.end
