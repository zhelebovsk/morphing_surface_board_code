"""
Shared OpenOCD utilities for HW_tests.
Requires: openocd + arm-none-eabi-nm on PATH, ST-LINK connected, firmware running.
"""

import os
import struct
import subprocess
import socket
import time

ELF_PATH = os.path.join(os.path.dirname(__file__), "..", "build", "STM32_code.elf")
OPENOCD_CFG = ["interface/stlink.cfg", "target/stm32g4x.cfg"]
OPENOCD_HOST = "localhost"
OPENOCD_PORT = 4444


def get_symbol_address(elf_path, symbol_name):
    result = subprocess.run(["arm-none-eabi-nm", elf_path], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == symbol_name:
            return int(parts[0], 16)
    return None


class OpenOCDProcess:
    """Context manager: starts openocd, yields, then kills it."""

    def __init__(self, cfg_files=None):
        self.cfg_files = cfg_files or OPENOCD_CFG
        self._proc = None

    def __enter__(self):
        args = ["openocd"]
        for f in self.cfg_files:
            args += ["-f", f]
        args += ["-c", "tcl_port disabled", "-c", "init", "-c", "halt"]
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        return self

    def __exit__(self, *_):
        if self._proc:
            self._proc.terminate()
            self._proc.wait()


class OpenOCDTelnet:
    """Telnet connection to a running OpenOCD instance."""

    PROMPT = b"> "

    def __init__(self, host=OPENOCD_HOST, port=OPENOCD_PORT, timeout=15):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self._drain()

    def _drain(self):
        buf = b""
        while not buf.endswith(self.PROMPT):
            buf += self.sock.recv(4096)
        return buf.decode(errors="replace")

    def cmd(self, command):
        self.sock.sendall((command + "\n").encode())
        return self._drain()

    def halt(self):
        self.cmd("halt")

    def resume(self):
        self.cmd("resume")

    def read_uint16_array(self, base_addr, count):
        """Read `count` uint16 values from `base_addr`. Target must be halted."""
        # mdh reads 16-bit halfwords; request all at once
        resp = self.cmd(f"mdh 0x{base_addr:08X} {count}")
        values = []
        for line in resp.splitlines():
            if ":" in line:
                hex_parts = line.split(":")[1].strip().split()
                for h in hex_parts:
                    try:
                        values.append(int(h, 16))
                    except ValueError:
                        pass
        return values[:count]

    def read_float_array(self, base_addr, count):
        """Read `count` IEEE-754 floats from `base_addr`. Target must be halted."""
        resp = self.cmd(f"mdw 0x{base_addr:08X} {count}")
        values = []
        for line in resp.splitlines():
            if ":" in line:
                hex_parts = line.split(":")[1].strip().split()
                for h in hex_parts:
                    try:
                        raw = int(h, 16)
                        values.append(struct.unpack("f", struct.pack("I", raw))[0])
                    except (ValueError, struct.error):
                        pass
        return values[:count]

    def read_uint16(self, addr):
        vals = self.read_uint16_array(addr, 1)
        return vals[0] if vals else None

    def read_float(self, addr):
        vals = self.read_float_array(addr, 1)
        return vals[0] if vals else None

    def close(self):
        try:
            self.sock.sendall(b"exit\n")
        except Exception:
            pass
        self.sock.close()
