* Op-amp integrator with R1 and Cf
.include opamp.lib
Xopamp Vinp Vinn Vout SingleStageOpamp
Vinput Vin 0 2.5
R1 Vin Vinn 1k
Cf Vinn Vout 1u
Vref Vinp 0 2.5
.end
