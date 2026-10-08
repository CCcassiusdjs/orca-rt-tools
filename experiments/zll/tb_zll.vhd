-- Zero-load latency of the Hermes NoC (pkt-sim/hw/router/hermes).
--
-- XR x YR mesh, one packet [header, size = P, P payload flits] injected at
-- the LOCAL port of node SRC towards node DST, ideal sinks (credit_i = '1'),
-- no other traffic. Node n sits at x = n mod XR, y = n / XR.
--
-- Latency: cycles from the acceptance of the header at the LOCAL port of
-- SRC (rx = '1' and credit_o = '1') to the consumption of the last flit at
-- the LOCAL port of DST (tx = '1' and credit_i = '1'). The sink checks the
-- order and the content of every flit.
--
-- Output: one line "ZLL src=.. dst=.. m=.. p=.. latency=.. flits=.. bad=..",
-- with m = |x_DST - x_SRC| + |y_DST - y_SRC| (hops). The clock stops after
-- the packet (or after TIMEOUT cycles), which ends the simulation.
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;
use work.HermesPackage.all;
use work.standards.all;

entity tb_zll is
  generic(XR: integer := 8; YR: integer := 3; SRC: integer := 0; DST: integer := 1;
          P: integer := 4; TIMEOUT: integer := 2000);
end tb_zll;

architecture tb of tb_zll is
  constant N : integer := XR*YR;
  signal clk : std_logic := '0';
  signal done : boolean := false;
  signal clkv : std_logic_vector(N-1 downto 0);
  signal reset : std_logic := '1';
  signal rxL, creditoL, txL, creditiL, clkrxL, clktxL : std_logic_vector(N-1 downto 0) := (others => '0');
  signal dinL, doutL : arrayNrot_regflit(N-1 downto 0) := (others => (others => '0'));
  signal cyc : integer := 0;
  signal rxI : std_logic := '0';
  signal dI : regflit := (others => '0');
  signal t_start : integer := -1;

  function header(d : integer) return regflit is
    variable f : regflit := (others => '0');
  begin
    f(15 downto 8) := conv_std_logic_vector(d mod XR, 8);
    f(7 downto 0)  := conv_std_logic_vector(d / XR, 8);
    return f;
  end function;

  function absi(v : integer) return integer is
  begin
    if v < 0 then return -v; else return v; end if;
  end function;

  constant HOPS : integer := absi(DST mod XR - SRC mod XR) + absi(DST / XR - SRC / XR);
begin
  process(rxI, dI) begin
    rxL <= (others => '0'); dinL <= (others => (others => '0'));
    rxL(SRC) <= rxI; dinL(SRC) <= dI;
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

  -- source: [header, size = P, payload A000 + i]
  process(clk)
    variable idx : integer := 0;
  begin
    if rising_edge(clk) then
      if rxI = '1' and creditoL(SRC) = '1' then
        if idx = 0 then t_start <= cyc; end if;
        idx := idx + 1;
      end if;
      if cyc >= 10 and idx < P + 2 then
        if idx = 0 then
          dI <= header(DST);
        elsif idx = 1 then
          dI <= conv_std_logic_vector(P, TAM_FLIT);
        else
          dI <= conv_std_logic_vector(16#A000# + idx - 2, TAM_FLIT);
        end if;
        rxI <= '1';
      else
        rxI <= '0';
      end if;
    end if;
  end process;

  -- sinks: order and content check, latency of the last flit
  process(clk)
    variable k : integer := 0;
    variable bad : integer := 0;
    variable expect : regflit;
  begin
    if rising_edge(clk) and not done then
      for i in 0 to N-1 loop
        if txL(i) = '1' and creditiL(i) = '1' then
          if i /= DST then
            bad := bad + 1;
          else
            if k = 0 then
              expect := header(DST);
            elsif k = 1 then
              expect := conv_std_logic_vector(P, TAM_FLIT);
            else
              expect := conv_std_logic_vector(16#A000# + k - 2, TAM_FLIT);
            end if;
            if doutL(i) /= expect then bad := bad + 1; end if;
            k := k + 1;
            if k = P + 2 then
              report "ZLL src=" & integer'image(SRC) & " dst=" & integer'image(DST)
                & " m=" & integer'image(HOPS) & " p=" & integer'image(P)
                & " latency=" & integer'image(cyc - t_start)
                & " flits=" & integer'image(k) & " bad=" & integer'image(bad);
              done <= true;
            end if;
          end if;
        end if;
      end loop;
      if cyc = TIMEOUT then
        report "ZLL src=" & integer'image(SRC) & " dst=" & integer'image(DST)
          & " m=" & integer'image(HOPS) & " p=" & integer'image(P)
          & " latency=-1 flits=" & integer'image(k) & " bad=" & integer'image(bad);
        done <= true;
      end if;
    end if;
  end process;
end tb;
