# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Receipt printer adapter contract + ESC/POS simulator.

Honesty notes:
* No physical printer has been qualified. The simulator exercises protocol bytes and error
  handling only (docs/hardware/HARDWARE_COMPATIBILITY.md).
* Basic printers cannot prove exactly-once physical output. Results distinguish Spooled,
  Acknowledged (only when the device reports it), Failed (definitely not accepted), and
  Delivery Unknown (sent, outcome ambiguous).
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
CUT = GS + b"V\x41\x03"  # partial cut with feed
# Drawer kick on pin 2: ESC p m t1 t2
DRAWER_PULSE = ESC + b"p\x00\x19\xfa"


@dataclass
class PrintResult:
	status: str  # Spooled | Acknowledged | Failed | Delivery Unknown
	error: str | None = None
	drawer_pulse_sent: bool = False


class ReceiptPrinter(Protocol):
	name: str

	def send(self, text: str, open_drawer: bool) -> PrintResult: ...


def encode_escpos(text: str, open_drawer: bool) -> bytes:
	# M1 restricts receipts to ASCII; Amharic/Tigrinya need validated raster rendering (R-11).
	body = text.encode("ascii", errors="replace")
	out = INIT + body + b"\n\n\n" + CUT
	if open_drawer:
		out = DRAWER_PULSE + out
	return out


@dataclass
class SimulatedEscPosPrinter:
	"""Deterministic ESC/POS device simulator. `fault` is one of:
	None | 'paper_out' | 'offline' | 'timeout'."""

	name: str = "Simulated ESC/POS"
	fault: str | None = None
	# Bounded: the simulator runs inside a long-lived worker; keep only recent output.
	sent: deque = field(default_factory=lambda: deque(maxlen=200))

	def send(self, text: str, open_drawer: bool) -> PrintResult:
		data = encode_escpos(text, open_drawer)
		if self.fault == "offline":
			return PrintResult("Failed", "Printer offline: no connection was accepted.")
		if self.fault == "paper_out":
			# Device rejects the job before printing; drawer kick precedes the body and fires.
			self.sent.append(data[: len(DRAWER_PULSE)] if open_drawer else b"")
			return PrintResult("Failed", "Printer reports paper out.", drawer_pulse_sent=open_drawer)
		if self.fault == "timeout":
			self.sent.append(data)
			return PrintResult(
				"Delivery Unknown", "Data sent but the printer did not answer.", drawer_pulse_sent=open_drawer
			)
		self.sent.append(data)
		return PrintResult("Acknowledged", None, drawer_pulse_sent=open_drawer)

	@property
	def drawer_pulses(self) -> int:
		return sum(chunk.count(DRAWER_PULSE) for chunk in self.sent)


@dataclass
class DisabledPrinter:
	name: str = "Disabled"

	def send(self, text: str, open_drawer: bool) -> PrintResult:
		return PrintResult("Failed", "No receipt printer is configured for this register.")


_SIMULATOR = SimulatedEscPosPrinter()


def get_printer(adapter_name: str) -> ReceiptPrinter:
	if adapter_name == "Simulated ESC/POS":
		return _SIMULATOR
	return DisabledPrinter()


def simulator() -> SimulatedEscPosPrinter:
	"""Test/diagnostic access to the process-local simulator."""
	return _SIMULATOR
