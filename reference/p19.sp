* Op-amp differentiator with Rf and C1
.include opamp.lib
Vinput Vin 0 2.5
Vdc_bias Vdc 0 2.5
Xop Vdc n1 Vout SingleStageOpamp
Rf Vout n1 10k
C1 n1 Vin 10n
.end
