* task: 17  expect: netlist   (the provided op-amp must not be redefined)
.include opamp.lib
.subckt SingleStageOpamp a b c
R1 a c 1k
.ends
Xop Vinp Vinn Vout SingleStageOpamp
Vbias Vinp 0 2.5
R2 Vinn 0 1k
.end
