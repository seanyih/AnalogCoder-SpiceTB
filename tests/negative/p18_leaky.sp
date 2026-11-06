* task: 18  expect: function   (1k resistor across Cf: a low-pass inverting amplifier, not an integrator)
.include opamp.lib
Xopamp Vinp Vinn Vout SingleStageOpamp
Vinput Vin 0 2.5
R1 Vin Vinn 1k
Cf Vinn Vout 1u
Rleak Vinn Vout 1k
Vref Vinp 0 2.5
.end
