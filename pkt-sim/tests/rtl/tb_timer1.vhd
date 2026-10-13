-- Tick period of TIMER1 (hw/peripherals/peripherals_minimal.vhd).
--
-- The testbench writes the registers in the order of _hardware_init
-- (software/ucx-os/arch/riscv/hf-riscv-e/hal.c): TIMER1PRE = TIMERPRE_DIV16,
-- TIMER1 = TIMERSET, TIMER1 = 0, TIMER1CTC = CTC. PAALTCFG0 = 1 routes the
-- CTC interrupt flag (int_timer1_ctc, which toggles once per tick) to
-- gpioa_out(0). The testbench counts the clock cycles between successive
-- toggles and passes when the last NT intervals equal EXPECT.
-- The counter runs from 0 to CTC inclusive: one tick = 16 * (CTC + 1) cycles.
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;

entity tb_timer1 is
  generic(CTC: integer := 15624; EXPECT: integer := 250000; NT: integer := 3);
end tb_timer1;

architecture tb of tb_timer1 is
  signal clk : std_logic := '0';
  signal rst : std_logic := '1';
  signal done : std_logic := '0';
  signal addr, din, dout : std_logic_vector(31 downto 0) := (others => '0');
  signal sel, wr, irq : std_logic := '0';
  signal gin, gout, gddr : std_logic_vector(7 downto 0) := (others => '0');
begin
  clk <= not clk after 1 ns when done = '0' else clk;

  dut: entity work.peripherals_minimal port map(
    clk_i => clk, rst_i => rst, addr_i => addr, data_i => din, data_o => dout,
    sel_i => sel, wr_i => wr, irq_o => irq,
    gpioa_in => gin, gpioa_out => gout, gpioa_ddr => gddr);

  stim: process
    procedure wr32(a: std_logic_vector(31 downto 0); d: std_logic_vector(31 downto 0)) is
    begin
      wait until rising_edge(clk);
      addr <= a; din <= d; sel <= '1'; wr <= '1';
      wait until rising_edge(clk);
      sel <= '0'; wr <= '0';
    end procedure;
    variable last, n, toggles, bad : integer := 0;
    variable prev : std_logic;
  begin
    wait until rising_edge(clk);
    wait until rising_edge(clk);
    rst <= '0';
    wr32(x"e1024410", x"00000002");                     -- TIMER1PRE = TIMERPRE_DIV16
    wr32(x"e1024400", x"80000000");                     -- TIMER1 = TIMERSET
    wr32(x"e1024400", x"00000000");                     -- TIMER1 = 0
    wr32(x"e1024420", conv_std_logic_vector(CTC, 32));  -- TIMER1CTC
    wr32(x"e1004000", x"00000001");                     -- PAALTCFG0: int_timer1_ctc on gpioa_out(0)
    prev := gout(0);
    n := 0;
    -- the first toggle closes the interval that began before TIMER1CTC was
    -- written; the next NT intervals are whole ticks
    while toggles <= NT loop
      wait until rising_edge(clk);
      n := n + 1;
      if gout(0) /= prev then
        prev := gout(0);
        if toggles > 0 then
          report "TICK " & integer'image(n - last) & " cycles";
          if n - last /= EXPECT then
            bad := bad + 1;
          end if;
        end if;
        last := n;
        toggles := toggles + 1;
      end if;
    end loop;
    if bad = 0 then
      report "PASS tb_timer1 (CTC " & integer'image(CTC) & ", tick " & integer'image(EXPECT) & " cycles)";
    else
      report "FAIL tb_timer1: " & integer'image(bad) & " ticks differ from " & integer'image(EXPECT);
    end if;
    done <= '1';
    wait;
  end process;
end tb;
