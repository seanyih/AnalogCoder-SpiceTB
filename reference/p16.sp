* RC phase-shift oscillator
.include opamp.lib
V1 Vdc 0 2.5
R1 Vout  node1 10k
C1 node1 node2 10n
R2 node2 node3 10k
C2 node3 node4 10n
R3 node4 node5 10k
C3 node5 Vdc   10n
R5 node2 0     10k
Xop node5 Vdc Vout SingleStageOpamp
R4 node1 Vdc 10k
.end
