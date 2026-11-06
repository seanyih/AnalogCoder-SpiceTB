* Single-stage telescopic cascode opamp
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd    Vdd    0 5.0
Vbias1 Vbias1 0 1.5
Vbias2 Vbias2 0 3.5
Vbias3 Vbias3 0 4.0
Vbias4 Vbias4 0 1.0
Vinp   Vinp   0 1.48
Vinn   Vinn   0 1.48
M1 Drain1 Vinp   Source1 Source1 nmos_model W=50u  L=1u
M2 Drain2 Vinn   Source1 Source1 nmos_model W=50u  L=1u
M3 Voutp  Vbias1 Drain1  Drain1  nmos_model W=50u  L=1u
M4 Vout   Vbias1 Drain2  Drain2  nmos_model W=50u  L=1u
M5 Voutp  Vbias2 Source3 Source3 pmos_model W=100u L=1u
M6 Vout   Vbias2 Source4 Source4 pmos_model W=100u L=1u
M7 Source3 Vbias3 Vdd    Vdd     pmos_model W=100u L=1u
M8 Source4 Vbias3 Vdd    Vdd     pmos_model W=100u L=1u
M9 Source1 Vbias4 0      0       nmos_model W=50u  L=1u
.end
