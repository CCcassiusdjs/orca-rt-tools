-- Header wait at one Hermes router (pkt-sim/hw/router/hermes), GHDL.
--
-- 3x3 mesh; five packets whose XY routes cross router 4 (x = 1, y = 1) on
-- pairwise disjoint links, so that the packets compete only for the
-- SwitchControl of router 4 (Hermes_switchcontrol.vhd): 3->5 and 5->3
-- (the two horizontal directions), 1->7 and 7->1 (the two vertical
-- directions), each with m = 2 hops, and 4->4 (LOCAL in, LOCAL out,
-- m = 0). Each packet enters router 4 by its own input port and leaves by
-- its own output port. Ideal sinks (credit_i = '1').
--
-- Generics: P payload flits, EN bitmask of the active packets (bit k for
-- packet k above), O0..O4 injection offsets in cycles (packet k starts at
-- cycle 10 + Ok).
--
-- Latency: cycles from the acceptance of the header at the LOCAL port of
-- the source to the consumption of the last flit at the LOCAL port of the
-- target; extra = latency - L0, L0 = 6(m+1) + P + 1 (make zll). The sink
-- checks the order and the content of every flit.
--
-- Output: one line per packet
-- "CONT k=.. m=.. p=.. off=.. start=.. latency=.. l0=.. extra=.. bad=..",
-- and "CONT timeout" if the packets do not arrive within TIMEOUT cycles.
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;
use work.HermesPackage.all;
use work.standards.all;

entity tb_cont is
  generic(P: integer := 4; EN: integer := 31;
          O0: integer := 0; O1: integer := 0; O2: integer := 0; O3: integer := 0; O4: integer := 0;
          TIMEOUT: integer := 3000);
end tb_cont;

architecture tb of tb_cont is
  constant XR : integer := 3; constant YR : integer := 3; constant N : integer := 9;
  type iarr is array(0 to 4) of integer;
  constant SRCV : iarr := (3, 5, 1, 7, 4);
  constant DSTV : iarr := (5, 3, 7, 1, 4);
  constant HOPV : iarr := (2, 2, 2, 2, 0);
  constant OFFV : iarr := (O0, O1, O2, O3, O4);
  signal clk : std_logic := '0';
  signal done : boolean := false;
  signal clkv : std_logic_vector(N-1 downto 0);
  signal reset : std_logic := '1';
  signal rxL, creditoL, txL, creditiL, clkrxL, clktxL : std_logic_vector(N-1 downto 0) := (others => '0');
  signal dinL, doutL : arrayNrot_regflit(N-1 downto 0) := (others => (others => '0'));
  signal cyc : integer := 0;
  type sarr is array(0 to 4) of std_logic;
  type farr is array(0 to 4) of regflit;
  signal rxI : sarr := (others => '0');
  signal dI : farr := (others => (others => '0'));
  signal t_start : iarr := (others => -1);
  signal fin : sarr := (others => '0');

  function header(d : integer) return regflit is
    variable f : regflit := (others => '0');
  begin
    f(15 downto 8) := conv_std_logic_vector(d mod XR, 8);
    f(7 downto 0)  := conv_std_logic_vector(d / XR, 8);
    return f;
  end function;
  function active(k : integer) return boolean is
  begin
    return ((EN / (2**k)) mod 2) = 1;
  end function;
begin
  process(rxI, dI) begin
    rxL <= (others => '0'); dinL <= (others => (others => '0'));
    for k in 0 to 4 loop
      rxL(SRCV(k)) <= rxI(k); dinL(SRCV(k)) <= dI(k);
    end loop;
  end process;
  clk <= not clk after 1 ns when not done else clk;
  clkv <= (others => clk);
  clkrxL <= (others => clk);
  creditiL <= (others => '1');

  noc: entity work.NOC generic map(X_ROUTERS => XR, Y_ROUTERS => YR)
    port map(clock => clkv, reset => reset, clock_rxLocal => clkrxL, rxLocal => rxL,
             data_inLocal => dinL, credit_oLocal => creditoL, clock_txLocal => clktxL,
             txLocal => txL, data_outLocal => doutL, credit_iLocal => creditiL);

  process(clk) begin
    if rising_edge(clk) then
      cyc <= cyc + 1;
      if cyc = 4 then reset <= '0'; end if;
    end if;
  end process;

  src: for k in 0 to 4 generate
    process(clk)
      variable idx : integer := 0;
    begin
      if rising_edge(clk) then
        if rxI(k) = '1' and creditoL(SRCV(k)) = '1' then
          if idx = 0 then t_start(k) <= cyc; end if;
          idx := idx + 1;
        end if;
        if active(k) and cyc >= 10 + OFFV(k) and idx < P + 2 then
          if idx = 0 then dI(k) <= header(DSTV(k));
          elsif idx = 1 then dI(k) <= conv_std_logic_vector(P, TAM_FLIT);
          else dI(k) <= conv_std_logic_vector(16#A000# + 256*k + idx - 2, TAM_FLIT);
          end if;
          rxI(k) <= '1';
        else
          rxI(k) <= '0';
        end if;
      end if;
    end process;
  end generate;

  snk: for k in 0 to 4 generate
    process(clk)
      variable cnt : integer := 0;
      variable bad : integer := 0;
      variable expect : regflit;
    begin
      if rising_edge(clk) and fin(k) = '0' then
        if txL(DSTV(k)) = '1' then
          if cnt = 0 then expect := header(DSTV(k));
          elsif cnt = 1 then expect := conv_std_logic_vector(P, TAM_FLIT);
          else expect := conv_std_logic_vector(16#A000# + 256*k + cnt - 2, TAM_FLIT);
          end if;
          if doutL(DSTV(k)) /= expect then bad := bad + 1; end if;
          cnt := cnt + 1;
          if cnt = P + 2 then
            report "CONT k=" & integer'image(k) & " m=" & integer'image(HOPV(k))
              & " p=" & integer'image(P) & " off=" & integer'image(OFFV(k))
              & " start=" & integer'image(t_start(k))
              & " latency=" & integer'image(cyc - t_start(k))
              & " l0=" & integer'image(6*(HOPV(k)+1) + P + 1)
              & " extra=" & integer'image(cyc - t_start(k) - (6*(HOPV(k)+1) + P + 1))
              & " bad=" & integer'image(bad);
            fin(k) <= '1';
          end if;
        end if;
      end if;
    end process;
  end generate;

  process(clk)
    variable alldone : boolean;
  begin
    if rising_edge(clk) then
      alldone := true;
      for k in 0 to 4 loop
        if active(k) and fin(k) = '0' then alldone := false; end if;
      end loop;
      if alldone and cyc > 20 then done <= true; end if;
      if cyc = TIMEOUT then report "CONT timeout"; done <= true; end if;
    end if;
  end process;
end tb;
