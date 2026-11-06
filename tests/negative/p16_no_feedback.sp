* task: 16  expect: function   (op-amp with an RC network but no feedback loop: no oscillation)
.include opamp.lib
V1 Vdc 0 2.5
R1 Vdc n1 10k
C1 n1 0 10n
Xop n1 Vdc Vout SingleStageOpamp
.end
