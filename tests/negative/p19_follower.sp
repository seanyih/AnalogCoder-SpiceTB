* task: 19  expect: netlist    (a voltage follower passes the triangle through instead of differentiating)
.include opamp.lib
Vinput Vin 0 2.5
Xop Vin Vout Vout SingleStageOpamp
Rf Vout 0 10k
C1 Vin 0 10n
.end
