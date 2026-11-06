* Non-inverting Schmitt trigger with positive feedback
.include opamp.lib
Xopamp non_inverting inverting Vout SingleStageOpamp
Rf non_inverting Vout 20k
R1 Vin non_inverting 10k
R2 inverting 0 10k
R3 Vdd inverting 10k
Vdd Vdd 0 5.0
Vin Vin 0 1.0
.end
