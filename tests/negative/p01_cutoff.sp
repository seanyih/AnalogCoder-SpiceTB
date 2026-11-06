* task: 1  expect: operating-point   (input bias below threshold and the sweep cannot help: gate tied to 0.2 V)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5
Vin Vin 0 0.2
Rg Vin 0 1k
M1 Vout Vin 0 0 nmos_model W=50u L=1u
M2 Vout Vb 0 0 nmos_model W=50u L=1u
Vb Vb 0 0.2
R1 Vout Vdd 1k
.end
