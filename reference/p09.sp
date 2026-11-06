* Two-stage amplifier with Miller compensation capacitor
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd    Vdd    0 5
Vin    Vin    0 1.0
Vbias1 Vbias1 0 4
Vbias2 Vbias2 0 4
M1 Drain1 Vin    0   0   nmos_model W=50u  L=1u
M2 Drain1 Vbias1 Vdd Vdd pmos_model W=100u L=1u
M3 Vout   Drain1 0   0   nmos_model W=100u L=1u
M4 Vout   Vbias2 Vdd Vdd pmos_model W=100u L=1u
Cc Drain1 Vout 10p
.end
