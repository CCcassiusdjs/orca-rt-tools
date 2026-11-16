-- Cycles per instruction of the HF-RISC core (hw/cpu/core_rv32e) on the
-- bus of manycore_pe.sv: one memory port for fetch and data (cpu.vhd,
-- int_control.vhd), read data one cycle after the address (the RAM of
-- dual_port_ram.sv and single_port_ram.sv registers data_out, and the
-- multiplexer of manycore_pe.sv selects it by dly_address), writes at the
-- clock edge of the address, stall_i = 0 (manycore_pe.sv:
-- cpu_if.stall_in = 0). manycore_pe.sv writes the instrumentation
-- registers (0x20000028 to 0x20000038) at the clock edge of the address and
-- reads them through dly_address: the same timing as the RAM, without a
-- wait state.
--
-- The program (cpu_cycles.s, image cpu_cycles.hex) runs blocks of 16 equal
-- instructions (or sequences) between stores to 0x2000002C (marker). For
-- each block, the testbench prints "CPI <name> <cycles>": (cycles between
-- the markers of the block - cycles between two adjacent markers) / 16,
-- and compares it with EXPECTED. Output "PASS tb_cpu_cycles" or "FAIL".
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_cpu_cycles is
	generic (HEX: string := "cpu_cycles.hex");
end tb_cpu_cycles;

architecture tb of tb_cpu_cycles is
	constant WORDS: integer := 2048;
	constant REPEAT: integer := 16;
	constant BLOCKS: integer := 17;
	type mem_t is array (0 to WORDS - 1) of std_logic_vector(31 downto 0);
	subtype name_t is string(1 to 16);
	type names_t is array (0 to BLOCKS - 1) of name_t;
	type ints_t is array (0 to BLOCKS - 1) of integer;
	constant NAMES: names_t := (
		"empty           ", "alu             ", "lui             ", "lw              ",
		"lhu             ", "lbu             ", "sw              ", "sh              ",
		"sb              ", "sw_mmio         ", "lw_mmio         ", "branch_taken    ",
		"branch_not_taken", "jal             ", "call_ret        ", "call_body       ",
		"inc64           ");
	-- cycles per repetition: ALU and lui 1, load and store 3, taken branch
	-- and jump 3, branch not taken 1; call_ret = jal + jalr = 6;
	-- call_body = 3 + 1 + 3 + 3 + 3 = 13; inc64 = 1 + 3 + 3 + 1 + 1 + 1 + 3 + 3 = 16
	constant EXPECTED: ints_t := (0, 1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 3, 1, 3, 6, 13, 16);

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

	function trim(s: string) return string is
	begin
		for i in s'range loop
			if s(i) = ' ' then
				return s(s'low to i - 1);
			end if;
		end loop;
		return s;
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
		variable n: integer := 0;
		variable last: integer := 0;
		variable base: integer := 0;
		variable delta: integer;
		variable errors: integer := 0;
		variable l: line;
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
			if addr = x"2000002C" and we /= "0000" and not done then
				if n > 0 then
					delta := cycle - last;
					if n = 1 then
						base := delta;
					end if;
					write(l, string'("CPI "));
					write(l, trim(NAMES(n - 1)));
					write(l, string'(" "));
					write(l, (delta - base) / REPEAT);
					writeline(output, l);
					if delta - base /= EXPECTED(n - 1) * REPEAT then
						write(l, string'("FAIL "));
						write(l, trim(NAMES(n - 1)));
						write(l, string'(": "));
						write(l, delta - base);
						write(l, string'(" cycles for 16, expected "));
						write(l, EXPECTED(n - 1) * REPEAT);
						writeline(output, l);
						errors := errors + 1;
					end if;
				end if;
				last := cycle;
				n := n + 1;
				if n = BLOCKS + 1 then
					if errors = 0 then
						write(l, string'("PASS tb_cpu_cycles"));
					else
						write(l, string'("FAIL tb_cpu_cycles"));
					end if;
					writeline(output, l);
					done <= true;
				end if;
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
