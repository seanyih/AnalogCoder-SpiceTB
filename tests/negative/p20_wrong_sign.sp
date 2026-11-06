* task: 20  expect: function   (Vout = Vin1 + Vin2 - 2.5 instead of -(...))
.include opamp.lib
Vinput1 Vin1 0 2.5
Vinput2 Vin2 0 2.5
R1 Vin1 Vinp 10k
R2 Vin2 Vinp 10k
Xop Vinp Vout Vout SingleStageOpamp
.end
