* task: 18  expect: netlist   (R1 / Cf naming is required by the testbench)
.include opamp.lib
Xopamp Vinp Vinn Vout SingleStageOpamp
Vinput Vin 0 2.5
Rin Vin Vinn 1k
Cfb Vinn Vout 1u
Vref Vinp 0 2.5
.end
