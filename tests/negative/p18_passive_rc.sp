* task: 18  expect: netlist    (passive RC low-pass followed by a voltage follower)
.include opamp.lib
Vinput Vin 0 2.5
R1 Vin n1 1k
Cf n1 0 1u
Xop n1 Vout Vout SingleStageOpamp
.end
