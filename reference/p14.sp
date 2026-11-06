* Two-stage differential opamp with active loads
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd    Vdd    0 5.0
Vbias1 Vbias1 0 1.0
Vbias2 Vbias2 0 4.0
Vbias3 Vbias3 0 4.0
Vinp   Vinp   0 1.25
Vinn   Vinn   0 1.25
M1 Drain1 Vinp   Source1 Source1 nmos_model W=50u L=1u
M2 Drain2 Vinn   Source1 Source1 nmos_model W=50u L=1u
M5 Source1 Vbias1 0      0       nmos_model W=50u L=1u
M6 Drain1 Drain1 Vdd     Vdd     pmos_model W=50u L=1u
M7 Drain2 Drain1 Vdd     Vdd     pmos_model W=50u L=1u
M3 Voutp  Drain1 0       0       nmos_model W=50u L=1u
M8 Voutp  Vbias2 Vdd     Vdd     pmos_model W=50u L=1u
M4 Vout   Drain2 0       0       nmos_model W=50u L=1u
M9 Vout   Vbias3 Vdd     Vdd     pmos_model W=50u L=1u
.end
