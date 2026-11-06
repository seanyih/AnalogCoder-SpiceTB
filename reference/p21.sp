* Op-amp subtractor Vout = Vin2 - Vin1
.include opamp.lib
Vinput1 Vin1 0 2.75
Vinput2 Vin2 0 5.00
R1 Vin1 Vinn 10k
R2 Vin2 Vinp 10k
R3 Vinn Vout 10k
R4 Vinp 0    10k
Xopamp Vinp Vinn Vout SingleStageOpamp
.end
