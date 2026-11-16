-- Compare interrupt of TIMER1 (hw/peripherals/peripherals_minimal.vhd)
-- for the time-triggered injection (software/ucx-os/lib/noc_tt.c).
--
-- The testbench programs TIMER1 as _hardware_init (hal.c: TIMER1PRE =
-- TIMERPRE_DIV16, TIMER1 = TIMERSET, TIMER1 = 0, TIMER1CTC = CTC), then:
--   1. TIMERMASK = CTC cause (bit 2): the rise of irq_o at each tick; the
--      testbench toggles bit 2 of TIMERCAUSEINV after each rise, as
--      irq0_handler does;
--   2. TIMERMASK = OCR cause (bit 3), TIMERCAUSEINV bit 3 = 1, TIMER1OCR =
--      OCR: irq_o rises when TIMER1 reaches OCR (cause TIMER1 < TIMER1OCR,
--      inverted) and falls when TIMER1 returns to 0 at the next tick.
-- It passes when every rise of phase 2 comes 16 OCR cycles after a tick of
-- phase 1 (modulo the tick 16 (CTC + 1)), every fall at a tick, and,
-- with TIMER1OCR = 0, irq_o stays high (the cause TIMER1 < 0 never holds).
library IEEE;
use IEEE.std_logic_1164.all;
use IEEE.std_logic_unsigned.all;
use IEEE.std_logic_arith.all;

entity tb_timer1_ocr is
  generic(CTC: integer := 15; OCR: integer := 5; NT: integer := 3);
end tb_timer1_ocr;

architecture tb of tb_timer1_ocr is
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
    variable n : integer := 0;     -- rising edges since the release of reset
    procedure step is
    begin
      wait until rising_edge(clk);
      n := n + 1;
    end procedure;
    procedure wr32(a: std_logic_vector(31 downto 0); d: std_logic_vector(31 downto 0)) is
    begin
      step;
      addr <= a; din <= d; sel <= '1'; wr <= '1';
      step;
      sel <= '0'; wr <= '0';
    end procedure;
    constant P : integer := 16 * (CTC + 1);
    variable inv, tick, ticks, rises, falls, bad : integer := 0;
    variable prev : std_logic := '0';
  begin
    step;
    step;
    rst <= '0';
    wr32(x"e1024410", x"00000002");                     -- TIMER1PRE = TIMERPRE_DIV16
    wr32(x"e1024400", x"80000000");                     -- TIMER1 = TIMERSET
    wr32(x"e1024400", x"00000000");                     -- TIMER1 = 0
    wr32(x"e1024420", conv_std_logic_vector(CTC, 32));  -- TIMER1CTC
    -- 1. ticks: rise of irq_o with the CTC cause
    wr32(x"e1020c00", x"00000004");                     -- TIMERMASK = CTC
    prev := irq;
    while ticks < NT loop
      step;
      if irq = '1' and prev = '0' then
        tick := n;
        ticks := ticks + 1;
        report "TICK at " & integer'image(n);
        inv := 4 - inv;                                 -- toggle bit 2 (irq0_handler)
        wr32(x"e1020800", conv_std_logic_vector(inv, 32));
      end if;
      prev := irq;
    end loop;
    -- 2. compare register
    wr32(x"e1024430", conv_std_logic_vector(OCR, 32));  -- TIMER1OCR
    wr32(x"e1020800", conv_std_logic_vector(inv + 8, 32)); -- TIMERCAUSEINV bit 3
    wr32(x"e1020c00", x"00000008");                     -- TIMERMASK = OCR
    prev := irq;
    if OCR = 0 then
      for i in 1 to 3 * P loop
        step;
        if irq /= '1' then
          bad := bad + 1;
        end if;
      end loop;
      rises := NT;
    end if;
    while rises < NT loop
      step;
      if irq = '1' and prev = '0' then
        rises := rises + 1;
        report "OCR at " & integer'image(n) & ", " & integer'image((n - tick) mod P) & " cycles after the tick";
        if (n - tick) mod P /= 16 * OCR then
          bad := bad + 1;
        end if;
      elsif irq = '0' and prev = '1' then
        falls := falls + 1;
        if (n - tick) mod P /= 0 then
          bad := bad + 1;
        end if;
      end if;
      prev := irq;
    end loop;
    if bad = 0 then
      report "PASS tb_timer1_ocr (CTC " & integer'image(CTC) & ", OCR " & integer'image(OCR) & ")";
    else
      report "FAIL tb_timer1_ocr: " & integer'image(bad) & " edges off the expected cycle";
    end if;
    done <= '1';
    wait;
  end process;
end tb;
