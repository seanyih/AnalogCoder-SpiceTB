* task: 12  expect: netlist   (reference current derived from a resistor instead of a current source Iref)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5.0
Rref Vdd Iref 2.5k
M1 Iref    Iref Source2 Source2 nmos_model W=50u L=1u
M2 Source2 Iref 0       0       nmos_model W=50u L=1u
M3 Iout    Iref Source4 Source4 nmos_model W=50u L=1u
M4 Source4 Iref 0       0       nmos_model W=50u L=1u
R1 Iout Vdd 1k
.end
