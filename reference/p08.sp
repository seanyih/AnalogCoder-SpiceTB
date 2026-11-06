* Simple NMOS constant current source with resistive load
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd   Vdd   0 5.0
Vbias Vbias 0 1.5
M1 Vout Vbias 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
