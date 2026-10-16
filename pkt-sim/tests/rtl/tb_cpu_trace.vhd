-- Cycle trace of a program on the HF-RISC core (hw/cpu/core_rv32e), with
-- the bus of tb_cpu_cycles.vhd (one memory port, read data one cycle
-- after the address, no wait state, stall_i = 0). The program (HEX: one
-- word per line, image from address 0, at most WORDS words) writes a
-- marker word to 0x2000002C; the testbench prints "MARK <cycle> <word>"
-- for each such store (cycle of the clock edge of the address, as
-- tb_cpu_cycles.vhd) and stops at a store to 0x20000030 ("DONE <cycle>")
-- or at MAX_CYCLES ("TIMEOUT").
--
-- Use: rttools.wcet tests (orca-rt-tools/tests/test_wcet_rtl.py) and
-- pkt-sim/tests/rtl/run.sh tb_cpu_trace, with the program wcet_bodies.c
-- (image wcet_bodies.hex): cycles of the bodies of rttools.ucxgen against
-- their static WCET.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_cpu_trace is
	generic (HEX: string := "wcet_bodies.hex"; WORDS: integer := 16384; MAX_CYCLES: integer := 4000000);
end tb_cpu_trace;

architecture tb of tb_cpu_trace is
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
	signal mode: std_logic_vector(2 downto 0);
	signal extio_out: std_logic_vector(7 downto 0);
	signal data_q: std_logic_vector(31 downto 0) := (others => '0');
	signal cycle: integer := 0;
	signal done: boolean := false;
begin
	clk <= not clk after 1 ns when not done;
	data_i <= data_q;

	cpu: entity work.processor
	port map(clk_i => clk, rst_i => rst, stall_i => '0',
		addr_o => addr, data_i => data_i, data_o => data_o, data_w_o => we,
		data_mode_o => mode, extio_in => (others => '0'), extio_out => extio_out);

	process(clk)
		file f: text;
		variable mem: mem_t := (others => (others => '0'));
		variable loaded: boolean := false;
		variable h: string(1 to 8);
		variable k: integer;
		variable a: integer;
		variable l: line;
		variable word: std_logic_vector(31 downto 0);
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
		if rising_edge(clk) then
			cycle <= cycle + 1;
			if we /= "0000" and not done then
				if addr = x"2000002C" then
					-- the core drives the store data in big-endian byte order
					word := data_o(7 downto 0) & data_o(15 downto 8) & data_o(23 downto 16) & data_o(31 downto 24);
					write(l, string'("MARK "));
					write(l, cycle);
					write(l, string'(" "));
					write(l, to_integer(unsigned(word(30 downto 0))));
					writeline(output, l);
				elsif addr = x"20000030" then
					write(l, string'("DONE "));
					write(l, cycle);
					writeline(output, l);
					done <= true;
				end if;
			end if;
			if cycle >= MAX_CYCLES and not done then
				write(l, string'("TIMEOUT"));
				writeline(output, l);
				done <= true;
			end if;
			a := to_integer(unsigned(addr(31 downto 2)));
			if unsigned(addr) < WORDS * 4 then
				for b in 0 to 3 loop
					if we(b) = '1' then
						mem(a)(8 * b + 7 downto 8 * b) := data_o(8 * b + 7 downto 8 * b);
					end if;
				end loop;
				data_q <= mem(a);
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
