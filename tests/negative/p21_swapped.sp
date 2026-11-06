* task: 21  expect: function   (computes Vin1 - Vin2)
.include opamp.lib
Vinput1 Vin1 0 2.75
Vinput2 Vin2 0 5.00
R1 Vin2 Vinn 10k
R2 Vin1 Vinp 10k
R3 Vinn Vout 10k
R4 Vinp 0    10k
Xopamp Vinp Vinn Vout SingleStageOpamp
.end
