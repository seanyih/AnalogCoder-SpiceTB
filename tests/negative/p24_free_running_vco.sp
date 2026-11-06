* task: 24  expect: function   (free-running ring VCO trimmed to 10 MHz, no loop: cannot track 12 MHz)
* Same ring VCO as reference/p24.sp, but the PFD / charge pump / loop filter are replaced by a
* fixed control voltage that makes it run at 10 MHz.  The original 10 MHz-only check would accept it.
*
* ---------------- logic cells for the PFD (kp = 2000u) ----------------
.subckt inv_pfd vdd vss I O_delay
.model nmos_m nmos level=1 kp=2000e-6 vto=0.4
.model pmos_m pmos level=1 kp=2000e-6 vto=-0.4
M0 O I vdd vdd pmos_m
M1 O I vss vss nmos_m
R0 O O_delay 10
C0 O_delay vss 0.1p
.ends
.subckt tinv_pfd vdd vss I EN O_delay
.model nmos_m nmos level=1 kp=2000e-6 vto=0.4
.model pmos_m pmos level=1 kp=2000e-6 vto=-0.4
X0 vdd vss EN ENB inv_pfd
M0 vp I vdd vdd pmos_m
M1 vn I vss vss nmos_m
M2 O ENB vp vdd pmos_m
M3 O EN  vn vss nmos_m
R0 O O_delay 20
C0 O_delay vss 0.2p
.ends
.subckt nand_pfd vdd vss A B O_delay
.model nmos_m nmos level=1 kp=2000e-6 vto=0.4
.model pmos_m pmos level=1 kp=2000e-6 vto=-0.4
M0 O A vdd vdd pmos_m
M1 O B vdd vdd pmos_m
M2 O A v1 vss nmos_m
M3 v1 B vss vss nmos_m
R0 O O_delay 40
C0 O_delay vss 0.4p
.ends
.subckt dffr_pfd vdd vss D CLK RSTB Q
.model pmos_m pmos level=1 kp=2000e-6 vto=-0.4
X0 vdd vss CLK CLKB inv_pfd
X1 vdd vss D CLKB v1 tinv_pfd
M1 v1 RSTB vdd vdd pmos_m
X2 vdd vss v1 v1_b inv_pfd
X3 vdd vss v1_b CLK v1 tinv_pfd
X4 vdd vss v1_b CLK v2 tinv_pfd
M2 v2 RSTB vdd vdd pmos_m
X5 vdd vss v2 Q inv_pfd
X6 vdd vss Q CLKB v2 tinv_pfd
.ends
.subckt pfd vdd vss clk_ref clk_fb UP DN
X0 vdd vss vdd clk_ref rstb UP dffr_pfd
X1 vdd vss vdd clk_fb  rstb DN dffr_pfd
X2 vdd vss UP DN rstb nand_pfd
.ends
* ---------------- charge pump (kp = 1200u) ----------------
.subckt inv_cp vdd vss I O_delay
.model nmos_m nmos level=1 kp=1200e-6 vto=0.4
.model pmos_m pmos level=1 kp=1200e-6 vto=-0.4
M0 O I vdd vdd pmos_m
M1 O I vss vss nmos_m
R0 O O_delay 10
C0 O_delay vss 0.1p
.ends
.subckt charge_pump vdd vss up dn vctrl
.model nmos_m  nmos level=1 kp=1200e-6  vto=0.4
.model pmos_m  pmos level=1 kp=1200e-6  vto=-0.4
.model nmos_m2 nmos level=1 kp=12000e-6 vto=0.4
.model pmos_m2 pmos level=1 kp=12000e-6 vto=-0.4
I1 vdd vn1 300u
X0 vdd vss dn dn_inv inv_cp
M1  vp1   vp1    vdd  vdd pmos_m2
M4  m4_d  dn_inv vdd  vdd pmos_m
M6  vctrl vp1    m4_d vdd pmos_m
M8  vn1   vn1    vss  vss nmos_m2
M9  vp1   vn1    vss  vss nmos_m2
M12 m12_d up     vss  vss nmos_m
M14 vctrl vn1    m12_d vss nmos_m
.ends
* ---------------- loop filter ----------------
.subckt loop_filter vss i o
R0 i o 100
R1 o c1_up 3k
C1 c1_up vss 50p
C2 o vss 0.5p
.ends
* ---------------- ring VCO (kp = 400u) ----------------
.subckt inv_vco vdd vss I O_delay
.model nmos_m nmos level=1 kp=400e-6 vto=0.4
.model pmos_m pmos level=1 kp=400e-6 vto=-0.4
M0 O I vdd vdd pmos_m
M1 O I vss vss nmos_m
R0 O O_delay 10
C0 O_delay vss 0.1p
.ends
.subckt delay_line vdd vss in_p in_n vctrl out_p out_n
.model pmos_m pmos level=1 kp=400e-6 vto=-0.4
X0 vp1 vss in_p out_n inv_vco
M0 vp1 vctrl vdd vdd pmos_m
X1 vp2 vss in_n out_p inv_vco
M1 vp2 vctrl vdd vdd pmos_m
X2 vdd vss out_p out_n inv_vco
X3 vdd vss out_n out_p inv_vco
.ends
.subckt ring_vco vdd vss vctrl clk_p clk_n clk_p_45 clk_n_45 clk_p_90 clk_n_90 clk_p_135 clk_n_135
X1 vdd vss clk_p     clk_n     vctrl clk_p_45  clk_n_45  delay_line
X2 vdd vss clk_p_45  clk_n_45  vctrl clk_p_90  clk_n_90  delay_line
X3 vdd vss clk_p_90  clk_n_90  vctrl clk_p_135 clk_n_135 delay_line
X4 vdd vss clk_p_135 clk_n_135 vctrl clk_n     clk_p     delay_line
.ends
* ---------------- top level ----------------
VDD vdd 0 1
Vctl vctrl_delay 0 0.5059
Rref clk_ref 0 1k
Xvco  vdd 0 vctrl_delay clk_p clk_n clk_p_45 clk_n_45 clk_p_90 clk_n_90 clk_p_135 clk_n_135 ring_vco
.ic v(clk_p)=0.5 v(clk_n)=0.5 v(clk_p_45)=0.5 v(clk_n_45)=0.5
+ v(clk_p_90)=0.5 v(clk_n_90)=0.5 v(clk_p_135)=0.5 v(clk_n_135)=0.5
.end
