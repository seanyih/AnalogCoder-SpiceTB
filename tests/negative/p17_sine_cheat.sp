* task: 17  expect: netlist   (a sine source on the output is not an oscillator)
.include opamp.lib
Vfake Vout 0 SIN(2.5 1 1k)
Xop Vdc Vdc n1 SingleStageOpamp
V1 Vdc 0 2.5
.end
