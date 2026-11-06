* Single-stage differential common-source opamp with resistive loads and tail current
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd   Vdd   0 5.0
Vbias Vbias 0 1.0
Vinp  Vinp  0 0.93
Vinn  Vinn  0 0.93
M1 Drain1 Vinp  SourceCommon SourceCommon nmos_model W=50u  L=1u
M2 Drain2 Vinn  SourceCommon SourceCommon nmos_model W=50u  L=1u
M3 SourceCommon Vbias 0 0                 nmos_model W=100u L=1u
R1 Drain1 Vdd 10k
R2 Drain2 Vdd 10k
Rload Vout Drain1 1
.end
