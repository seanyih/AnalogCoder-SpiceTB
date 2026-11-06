* Differential opamp with active PMOS current-mirror load and tail current source
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd   Vdd   0 5.0
Vbias Vbias 0 1.5
Vinp  Vinp  0 2.5
Vinn  Vinn  0 2.5
M1 Voutp Vinp  Source3 Source3 nmos_model W=50u  L=1u
M2 Vout  Vinn  Source3 Source3 nmos_model W=50u  L=1u
M3 Source3 Vbias 0     0       nmos_model W=100u L=1u
M4 Voutp Voutp Vdd     Vdd     pmos_model W=100u L=1u
M5 Vout  Voutp Vdd     Vdd     pmos_model W=100u L=1u
.end
