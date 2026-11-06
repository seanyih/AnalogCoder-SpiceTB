* task: 24  expect: function   (clk_p is just a buffered copy of clk_ref)
.model n nmos level=1 kp=400e-6 vto=0.4
.model p pmos level=1 kp=400e-6 vto=-0.4
VDD vdd 0 1
M1 a clk_ref 0 0 n
M2 a clk_ref vdd vdd p
M3 clk_p a 0 0 n
M4 clk_p a vdd vdd p
.end
