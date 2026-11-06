* Wien bridge oscillator
.include opamp.lib
Xop1 Vinp Vinn Vout SingleStageOpamp
R1 Vout n1   10k
C1 n1   Vinp 10n
R2 Vinp Vbias 10k
C2 Vinp Vbias 10n
Rf Vout Vinn  10k
Rb Vinn Vbias 1k
Vbias Vbias 0 2.5
.end
