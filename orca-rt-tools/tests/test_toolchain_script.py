"""Fix 28 (pkt-sim/software/toolchain/riscv64.sh).

1. Line 59 lacked a backslash: the binutils configure ran without
   --with-arch, --with-sysroot, --disable-nls e --disable-werror, e a
   line 60 became a nonexistent command.
2. ${nproc} is an empty variable: make -j ran without a limit; the correct form is
   $(nproc).
3. Without 'set -e', the script continued after a failing step.

The test runs the script with wget, tar, make and nproc replaced by
stubs (no network and no compilation) and checks the received arguments.
"""
import os
import stat
import subprocess

from tests.conftest import REPO_ROOT

SCRIPT = os.path.join(REPO_ROOT, "pkt-sim", "software", "toolchain", "riscv64.sh")

STUB_TAR = r'''#!/bin/sh
# tar -zxvf <file>: creates the source directory with a fake configure
f=$(basename "$2" .tar.gz)
mkdir -p "$f/contrib"
cat > "$f/configure" <<EOS
#!/bin/sh
echo "configure $f \$@" >> "$LOG"
EOS
printf '#!/bin/sh\necho prereq >> "$LOG"\n' > "$f/contrib/download_prerequisites"
chmod +x "$f/configure" "$f/contrib/download_prerequisites"
'''


def write_stub(d, name, body):
    p = d / name
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def run_script(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "log.txt"
    write_stub(bin_dir, "wget", '#!/bin/sh\necho "wget $@" >> "$LOG"\n')
    write_stub(bin_dir, "tar", STUB_TAR)
    write_stub(bin_dir, "make", '#!/bin/sh\necho "make $@" >> "$LOG"\n')
    write_stub(bin_dir, "nproc", "#!/bin/sh\necho 3\n")
    env = {"PATH": str(bin_dir) + ":/usr/bin:/bin", "LOG": str(log), "HOME": str(tmp_path)}
    r = subprocess.run(["sh", SCRIPT], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    return r, log.read_text().splitlines()


def test_binutils_configure_flags(tmp_path):
    r, log = run_script(tmp_path)
    assert "not found" not in r.stderr, r.stderr
    line = [l for l in log if l.startswith("configure binutils")][0]
    for flag in ("--with-arch=rv64i", "--with-sysroot", "--disable-nls", "--disable-werror"):
        assert flag in line


def test_make_uses_nproc(tmp_path):
    r, log = run_script(tmp_path)
    makes = [l for l in log if l.startswith("make ")]
    assert makes and all(" -j3 " in l + " " for l in makes if "install" not in l)


def test_script_stops_on_error(tmp_path):
    # a failing configure must stop the script
    bin_dir = tmp_path / "bin"
    r, log = run_script(tmp_path)
    assert r.returncode == 0, r.stderr
    write_stub(bin_dir, "wget", "#!/bin/sh\nexit 1\n")
    work = tmp_path / "work2"
    work.mkdir()
    env = {"PATH": str(bin_dir) + ":/usr/bin:/bin", "LOG": str(tmp_path / "log2.txt"), "HOME": str(tmp_path)}
    r2 = subprocess.run(["sh", SCRIPT], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    assert r2.returncode != 0
