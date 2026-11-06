* task: 10  expect: operating-point   (resistive load instead of a diode-connected PMOS)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vin Vin 0 1.5
M1 Vout Vin 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
