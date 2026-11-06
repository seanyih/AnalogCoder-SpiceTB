* task: 19  expect: function   (Rf in the feedback path, but the circuit is a voltage follower)
.include opamp.lib
Vinput Vin 0 2.5
Xop Vin n1 Vout SingleStageOpamp
Rf Vout n1 10k
C1 n1 0 10n
.end
