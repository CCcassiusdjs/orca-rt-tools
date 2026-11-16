-- LOCAL to LOCAL route of the Hermes crossbar (hw/router/hermes/Hermes_crossbar.vhd).
--
-- The LOCAL output of the crossbar has a case for the LOCAL input
-- (tab_out(LOCAL) = "100"): a packet from a node to itself leaves by the
-- LOCAL port, which is then free for the next packet.
--
-- 3 x 3 mesh, ideal sink (credit_i = '1'). Case A: node 4 (1,1) to
-- itself, P = 4. Case B: node 0 (0,0) to node 8 (2,2), m = 4 hops; the
-- latency from header acceptance at the source to consumption of the last
-- flit at the destination is 6(m + 1) + P + 1.
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;
use work.HermesPackage.all;
use work.standards.all;

entity tb_hermes_local is
  generic(SRC: integer := 4; DST: integer := 4; P: integer := 4; M: integer := 0;
          NAME: string := "A");
end tb_hermes_local;

architecture tb of tb_hermes_local is
  constant XR : integer := 3;
  constant YR : integer := 3;
  constant N : integer := XR*YR;
  signal clk : std_logic := '0';
  signal clkv : std_logic_vector(N-1 downto 0);
  signal reset : std_logic := '1';
  signal rxL, creditoL, txL, creditiL, clkrxL, clktxL : std_logic_vector(N-1 downto 0) := (others => '0');
  signal dinL, doutL : arrayNrot_regflit(N-1 downto 0) := (others => (others => '0'));
  signal cyc : integer := 0;
  signal rxI : std_logic := '0';
  signal dI : regflit := (others => '0');
  signal t_start, t_end : integer := -1;
  signal nrcv : integer := 0;
  signal bad : integer := 0;
begin
  process(rxI, dI) begin
    rxL <= (others => '0'); dinL <= (others => (others => '0'));
    rxL(SRC) <= rxI; dinL(SRC) <= dI;
  end process;
  clk <= not clk after 1 ns;
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

  -- injetor: [header, size = P, payload A000 + i]
  process(clk)
    variable idx : integer := 0;
    variable flit : regflit;
  begin
    if rising_edge(clk) then
      if rxI = '1' and creditoL(SRC) = '1' then
        if idx = 0 then t_start <= cyc; end if;
        idx := idx + 1;
      end if;
      if cyc >= 10 and idx < P + 2 then
        if idx = 0 then
          flit := (others => '0');
          flit(15 downto 8) := conv_std_logic_vector(DST mod XR, 8);
          flit(7 downto 0)  := conv_std_logic_vector(DST / XR, 8);
        elsif idx = 1 then
          flit := conv_std_logic_vector(P, 32);
        else
          flit := conv_std_logic_vector(16#A000# + idx - 2, 32);
        end if;
        dI <= flit; rxI <= '1';
      else
        rxI <= '0';
      end if;
    end if;
  end process;

  -- sink with order check
  process(clk)
    variable k : integer := 0;
    variable expect : regflit;
  begin
    if rising_edge(clk) then
      for i in 0 to N-1 loop
        if txL(i) = '1' and creditiL(i) = '1' then
          if i /= DST then
            bad <= bad + 1;
            report "flit on wrong node " & integer'image(i);
          else
            if k = 0 then
              expect := (others => '0');
              expect(15 downto 8) := conv_std_logic_vector(DST mod XR, 8);
              expect(7 downto 0)  := conv_std_logic_vector(DST / XR, 8);
            elsif k = 1 then
              expect := conv_std_logic_vector(P, 32);
            else
              expect := conv_std_logic_vector(16#A000# + k - 2, 32);
            end if;
            if doutL(i) /= expect then
              bad <= bad + 1;
              report "flit " & integer'image(k) & " wrong";
            end if;
            k := k + 1;
            nrcv <= k;
            if k = P + 2 then t_end <= cyc; end if;
          end if;
        end if;
      end loop;
      if cyc = 300 then
        if bad = 0 and nrcv = P + 2 and t_end - t_start = 6 * (M + 1) + P + 1 then
          report "PASS tb_hermes_local_" & NAME & " latency=" & integer'image(t_end - t_start);
        else
          report "FAIL tb_hermes_local_" & NAME & " received=" & integer'image(nrcv)
            & " bad=" & integer'image(bad) & " latency=" & integer'image(t_end - t_start);
        end if;
      end if;
    end if;
  end process;
end tb;
