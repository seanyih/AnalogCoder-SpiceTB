* task: 23  expect: function   (ring oscillator whose frequency does not depend on Vin)
.model n nmos level=1 kp=400e-6 vto=0.4
.model p pmos level=1 kp=400e-6 vto=-0.4
.subckt inv vdd a y
M1 y a 0 0 n
M2 y a vdd vdd p
C1 y 0 10p
.ends
VDD vdd 0 1
Vin Vin 0 0.7
Rin Vin 0 1k
X1 vdd Vout a inv
X2 vdd a b inv
X3 vdd b Vout inv
.ic v(Vout)=0 v(a)=1 v(b)=0
.end
