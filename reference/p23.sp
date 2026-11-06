* Voltage-controlled oscillator built from two op-amps (integrator + comparator)
* Translated from AnalogCoder sample_design/p23.py (1 V supply).
.subckt op_amp_a vdd vss in_p in_n vout
.model nmos_m nmos level=1 kp=800e-6 vto=0.4
.model pmos_m pmos level=1 kp=800e-6 vto=-0.4
M1 v1   v2   vdd vdd pmos_m
M2 v2   v2   vdd vdd pmos_m
M3 vout v2   vdd vdd pmos_m
M4 v3   in_n v1  vdd pmos_m
M5 v4   in_p v1  vdd pmos_m
M6 v3   v3   vss vss nmos_m
M7 v4   v3   vss vss nmos_m
M8 v2   vdd  vss vss nmos_m
M9 vout v4   vss vss nmos_m
.ends op_amp_a
.subckt op_amp_b vdd vss in_p in_n vout
.model nmos_m nmos level=1 kp=280e-6 vto=0.4
.model pmos_m pmos level=1 kp=280e-6 vto=-0.4
M1 v1   v2   vdd vdd pmos_m
M2 v2   v2   vdd vdd pmos_m
M3 vout v2   vdd vdd pmos_m
M4 v3   in_n v1  vdd pmos_m
M5 v4   in_p v1  vdd pmos_m
M6 v3   v3   vss vss nmos_m
M7 v4   v3   vss vss nmos_m
M8 v2   vdd  vss vss nmos_m
M9 vout v4   vss vss nmos_m
.ends op_amp_b
.model nmos_model nmos level=1 kp=1000e-6 vto=0.4
VDD vdd 0 1
Vin vin 0 0.7
R1 vin op1_n 15k
R2 vin op1_p 30k
R3 nmos_g vout 1k
R4 op1_p 0 30k
R5 nmos_d op1_n 3k
R6 op2_p 0 30k
R7 op2_p vout 30k
C1 op1_n vout_1 0.5n
M1 nmos_d nmos_g 0 0 nmos_model
Cload vout 0 1p
X1 vdd 0 op1_p op1_n vout_1 op_amp_a
X2 vdd 0 op2_p vout_1 vout op_amp_b
.ic v(vout_1)=0.3 v(vout)=0.6
.end
