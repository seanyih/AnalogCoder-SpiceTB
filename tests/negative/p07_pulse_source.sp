* task: 7  expect: netlist   (time-varying sources are not allowed)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd Vdd 0 5
Vin Vin 0 PULSE(0 5 0 1n 1n 1u 2u)
M1 Vout Vin 0 0 nmos_model W=50u L=1u
M2 Vout Vin Vdd Vdd pmos_model W=100u L=1u
.end
