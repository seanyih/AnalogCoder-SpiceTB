* task: 1  expect: netlist   (only level-1 MOSFET models)
.model nmos_model nmos level=49 vth0=0.5
Vdd Vdd 0 5
Vin Vin 0 1.5
M1 Vout Vin 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
