* task: 13  expect: function   (Vinn is not connected to the amplifier: no differential behaviour)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5.0
Vinp Vinp 0 1.5
Vinn Vinn 0 1.5
Rn Vinn 0 1k
M1 Vout Vinp 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 10k
.end
