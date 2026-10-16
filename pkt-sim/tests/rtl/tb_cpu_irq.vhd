-- Interrupt return of crt0.s (_isr of ucx-os/arch/riscv/hf-riscv-e) on the
-- HF-RISC core (hw/cpu/core_rv32e) with the bus of tb_cpu_cycles.vhd.
-- extio_in(0) is the interrupt source: the testbench raises it, the handler
-- of cpu_irq.s lowers it with a store to 0x20000040, and the testbench
-- raises interrupts in pairs: the second interrupt of pair k comes
-- DELAY = 1 + (k mod SPAN) cycles after the acknowledge of the first, so it
-- arrives at every cycle offset of the return of the handler and of _isr;
-- the next pair starts QUIET cycles after the acknowledge of the second. MODE (read at 0x20000038) = 1:
-- the handler enables interrupts before it returns (_ei of the UCX-OS
-- handlers, _interrupt_tick of dispatch(), kernel built with -DUCX_ISR_NESTING);
-- 0: it does not (default of the kernel); 2: as 0, and the main loop also
-- returns through the return of _isr with interrupts disabled and the
-- interrupts of the testbench pending (yield() of UCX-OS that resumes a task
-- preempted by the tick); 3: as 0, and the main loop calls _interrupt_set(0)
-- after a wait of (counter mod 64) iterations and checks IRQ_STATUS about 20
-- cycles later. HEX: cpu_irq.hex (_isr and _interrupt_set
-- of crt0.s up to tag r11-rc3) or cpu_irq_guard.hex (crt0.s of this tree).
-- FAIL when the main loop stores to 0x20000030 (sp changed) or to 0x20000034
-- (mode 3: interrupts enabled after _interrupt_set(0)), stops storing
-- its counter for STALL cycles, a raised interrupt waits STALL cycles, the
-- program stores below PROGRAM (the code; mode 1: the sb of the return of
-- _isr with a5 of a nested interrupt) or fetches outside the program; PASS
-- after COUNT interrupts.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_cpu_irq is
	generic (HEX: string := "cpu_irq.hex"; MODE: integer := 1; COUNT: integer := 2000;
		SPAN: integer := 96; QUIET: integer := 300; STALL: integer := 3000;
		PROGRAM: integer := 4096);
end tb_cpu_irq;

architecture tb of tb_cpu_irq is
	constant WORDS: integer := 2048;
	type mem_t is array (0 to WORDS - 1) of std_logic_vector(31 downto 0);

	function hex_word(h: string) return std_logic_vector is
		variable w: std_logic_vector(31 downto 0);
		variable d: integer;
	begin
		for i in 0 to 7 loop
			case h(h'low + i) is
				when '0' to '9' => d := character'pos(h(h'low + i)) - character'pos('0');
				when 'a' to 'f' => d := character'pos(h(h'low + i)) - character'pos('a') + 10;
				when others => d := character'pos(h(h'low + i)) - character'pos('A') + 10;
			end case;
			w(31 - 4 * i downto 28 - 4 * i) := std_logic_vector(to_unsigned(d, 4));
		end loop;
		return w;
	end function;

	signal clk: std_logic := '0';
	signal rst: std_logic := '1';
	signal addr, data_i, data_o: std_logic_vector(31 downto 0);
	signal we: std_logic_vector(3 downto 0);
	signal mode_o: std_logic_vector(2 downto 0);
	signal extio_out: std_logic_vector(7 downto 0);
	signal extio_in: std_logic_vector(7 downto 0) := (others => '0');
	signal data_q: std_logic_vector(31 downto 0) := (others => '0');
	signal done: boolean := false;
begin
	clk <= not clk after 1 ns when not done;
	data_i <= data_q;

	cpu: entity work.processor
	port map(clk_i => clk, rst_i => rst, stall_i => '0',
		addr_o => addr, data_i => data_i, data_o => data_o, data_w_o => we,
		data_mode_o => mode_o, extio_in => extio_in, extio_out => extio_out);

	process(clk)
		file f: text;
		variable mem: mem_t := (others => (others => '0'));
		variable loaded: boolean := false;
		variable h: string(1 to 8);
		variable k, a: integer;
		variable l: line;
		variable cycle: integer := 0;
		variable started: boolean := false;
		variable raised, acks: integer := 0;
		variable wait_left: integer := -1;
		variable last_progress: integer := 0;
		variable delay: integer := 0;
		variable pending: integer := 0;
		procedure finish(ok: boolean; msg: string) is
		begin
			if ok then
				write(l, string'("PASS tb_cpu_irq MODE=")); write(l, MODE);
			else
				write(l, string'("FAIL tb_cpu_irq MODE=")); write(l, MODE);
				write(l, string'(" ")); write(l, msg);
			end if;
			write(l, string'(" interrupts=")); write(l, raised);
			write(l, string'(" acks=")); write(l, acks);
			write(l, string'(" last_delay=")); write(l, delay);
			write(l, string'(" cycle=")); write(l, cycle);
			writeline(output, l);
			done <= true;
		end procedure;
	begin
		if not loaded then
			file_open(f, HEX, read_mode);
			k := 0;
			while not endfile(f) and k < WORDS loop
				readline(f, l);
				read(l, h);
				mem(k) := hex_word(h);
				k := k + 1;
			end loop;
			file_close(f);
			loaded := true;
		end if;
		if rising_edge(clk) and rst = '0' and not done then
			cycle := cycle + 1;
			if addr = x"2000002C" and we /= "0000" then
				last_progress := cycle;
				if not started then
					started := true;
					wait_left := 10;
				end if;
			end if;
			if addr = x"20000030" and we /= "0000" then
				finish(false, "sp changed in the main loop");
			end if;
			if addr = x"20000034" and we /= "0000" then
				finish(false, "interrupts enabled after _interrupt_set(0)");
			end if;
			if we /= "0000" and unsigned(addr) < PROGRAM then
				finish(false, "store into the program");
			end if;
			if addr = x"20000040" and we /= "0000" then
				extio_in(0) <= '0';
				acks := acks + 1;
				if raised >= COUNT then
					finish(true, "");
				end if;
				if raised mod 2 = 1 then
					delay := 1 + ((raised / 2) mod SPAN);
					wait_left := delay;
				else
					wait_left := QUIET;
				end if;
			end if;
			if wait_left = 0 then
				extio_in(0) <= '1';
				raised := raised + 1;
				wait_left := -1;
			elsif wait_left > 0 then
				wait_left := wait_left - 1;
			end if;
			if extio_in(0) = '1' then
				pending := pending + 1;
			else
				pending := 0;
			end if;
			if pending > STALL then
				finish(false, "interrupt not taken");
			end if;
			if started and cycle - last_progress > STALL then
				finish(false, "main loop stalled");
			end if;
			if we = "0000" and unsigned(addr) >= WORDS * 4 and addr(31 downto 28) /= x"2" and addr(31 downto 28) /= x"f" then
				finish(false, "access outside the program");
			end if;
			a := to_integer(unsigned(addr(31 downto 2)));
			if unsigned(addr) < WORDS * 4 then
				for b in 0 to 3 loop
					if we(b) = '1' then
						mem(a)(8 * b + 7 downto 8 * b) := data_o(8 * b + 7 downto 8 * b);
					end if;
				end loop;
				data_q <= mem(a);
			elsif addr = x"20000038" then
				data_q <= std_logic_vector(to_unsigned(MODE, 8)) & x"000000";
			else
				data_q <= (others => '0');
			end if;
		end if;
	end process;

	process
	begin
		wait for 10 ns;
		rst <= '0';
		wait;
	end process;
end tb;
