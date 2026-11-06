* CMOS logic inverter
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd Vdd 0 5.0
Vin Vin 0 2.5
M1 Vout Vin 0   0   nmos_model W=50u  L=1u
M2 Vout Vin Vdd Vdd pmos_model W=100u L=1u
.end
