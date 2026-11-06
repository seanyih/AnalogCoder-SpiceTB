* Op-amp adder (inverting summing amplifier)
.include opamp.lib
Vinput1 Vin1 0 1
Vinput2 Vin2 0 1
Xopamp Vinp Vinn Vout SingleStageOpamp
R1 Vin1 Vinn 10k
R2 Vin2 Vinn 10k
R3 Vinn Vout 10k
Vbias Vinp 0 2.5
Rground Vinn 0 1Meg
.end
