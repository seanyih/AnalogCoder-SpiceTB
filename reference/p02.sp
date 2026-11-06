* Three-stage amplifier (common-source stages with resistive loads)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5.0
Vin Vin 0 1.65
M1 Drain1 Vin    0 0 nmos_model W=50u L=1u
R1 Drain1 Vdd 1k
M2 Drain2 Drain1 0 0 nmos_model W=50u L=1u
R2 Drain2 Vdd 1k
M3 Vout   Drain2 0 0 nmos_model W=50u L=1u
R3 Vout Vdd 1k
.end
