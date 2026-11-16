-- Packet latency at one output port of a Hermes router (pkt-sim/hw/router/hermes)
-- under event-triggered injection, GHDL.
--
-- 3x3 mesh; four sources at nodes 3, 5, 1 and 7 send packets to node 4, so
-- the packets enter router 4 by its four mesh input ports and compete for
-- its LOCAL output (one control unit polls the input ports,
-- Hermes_switchcontrol.vhd). Source k sends N<k> packets of P payload flits
-- back to back from cycle 10 + O<k>: all its packets are requested at that
-- cycle, as the queue of a DDMA that receives N<k> sends at once. Ideal
-- sink (credit_i = '1').
--
-- Latency of a packet: cycles from the first cycle at which its source
-- presents the header of its first packet (the request) to the consumption
-- of its last flit at the LOCAL port of node 4, with the convention of
-- tb_cont.vhd (without contention, latency = L0 = 6(m+1) + P + 1).
--
-- Output: one line per packet "POLL k=.. n=.. p=.. req=.. latency=.. bad=..",
-- and "POLL timeout" if the packets do not arrive within TIMEOUT cycles.
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;
use work.HermesPackage.all;
use work.standards.all;

entity tb_poll is
  generic(P: integer := 4;
          N0: integer := 1; N1: integer := 1; N2: integer := 1; N3: integer := 1;
          O0: integer := 0; O1: integer := 0; O2: integer := 0; O3: integer := 0;
          TIMEOUT: integer := 20000);
end tb_poll;

architecture tb of tb_poll is
  constant XR : integer := 3; constant YR : integer := 3; constant N : integer := 9;
  constant DST : integer := 4;
  type iarr is array(0 to 3) of integer;
  constant SRCV : iarr := (3, 5, 1, 7);
  constant NV   : iarr := (N0, N1, N2, N3);
  constant OFFV : iarr := (O0, O1, O2, O3);
  signal clk : std_logic := '0';
  signal done : boolean := false;
  signal clkv : std_logic_vector(N-1 downto 0);
  signal reset : std_logic := '1';
  signal rxL, creditoL, txL, creditiL, clkrxL, clktxL : std_logic_vector(N-1 downto 0) := (others => '0');
  signal dinL, doutL : arrayNrot_regflit(N-1 downto 0) := (others => (others => '0'));
  signal cyc : integer := 0;
  type sarr is array(0 to 3) of std_logic;
  type farr is array(0 to 3) of regflit;
  signal rxI : sarr := (others => '0');
  signal dI : farr := (others => (others => '0'));
  signal t_req : iarr := (others => -1);
  signal received : integer := 0;

  function header(d : integer) return regflit is
    variable f : regflit := (others => '0');
  begin
    f(15 downto 8) := conv_std_logic_vector(d mod XR, 8);
    f(7 downto 0)  := conv_std_logic_vector(d / XR, 8);
    return f;
  end function;
begin
  process(rxI, dI) begin
    rxL <= (others => '0'); dinL <= (others => (others => '0'));
    for k in 0 to 3 loop
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

  src: for k in 0 to 3 generate
    process(clk)
      variable idx : integer := 0;   -- flit index within the current packet
      variable pk  : integer := 0;   -- packet index
    begin
      if rising_edge(clk) then
        if rxI(k) = '1' and t_req(k) < 0 then t_req(k) <= cyc; end if;
        if rxI(k) = '1' and creditoL(SRCV(k)) = '1' then
          idx := idx + 1;
          if idx = P + 2 then idx := 0; pk := pk + 1; end if;
        end if;
        if cyc >= 10 + OFFV(k) and pk < NV(k) then
          if idx = 0 then dI(k) <= header(DST);
          elsif idx = 1 then dI(k) <= conv_std_logic_vector(P, TAM_FLIT);
          else dI(k) <= conv_std_logic_vector(4096*k + 256*pk + idx - 2, TAM_FLIT);
          end if;
          rxI(k) <= '1';
        else
          rxI(k) <= '0';
        end if;
      end if;
    end process;
  end generate;

  snk: process(clk)
    variable cnt : integer := 0;
    variable bad : integer := 0;
    variable w, k, pn : integer;
  begin
    if rising_edge(clk) then
      if txL(DST) = '1' then
        if cnt = 0 then
          if doutL(DST) /= header(DST) then bad := bad + 1; end if;
        elsif cnt = 1 then
          if conv_integer(doutL(DST)) /= P then bad := bad + 1; end if;
        else
          w := conv_integer(doutL(DST));
          if cnt = 2 then k := w / 4096; pn := (w mod 4096) / 256; end if;
          if w /= 4096*k + 256*pn + cnt - 2 then bad := bad + 1; end if;
        end if;
        cnt := cnt + 1;
        if cnt = P + 2 then
          report "POLL k=" & integer'image(k) & " n=" & integer'image(pn) & " p=" & integer'image(P)
            & " req=" & integer'image(t_req(k)) & " latency=" & integer'image(cyc - t_req(k))
            & " bad=" & integer'image(bad);
          cnt := 0; bad := 0;
          received <= received + 1;
        end if;
      end if;
    end if;
  end process;

  process(clk) begin
    if rising_edge(clk) then
      if received = N0 + N1 + N2 + N3 and cyc > 20 then done <= true; end if;
      if cyc = TIMEOUT then report "POLL timeout"; done <= true; end if;
    end if;
  end process;
end tb;
