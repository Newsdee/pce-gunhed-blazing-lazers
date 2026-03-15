"""
HuC6280 Disassembler
====================

Full opcode table and disassembler for the HuC6280 CPU
(65C02 core + extras: CSH, CSL, TAM, TMA, ST0/ST1/ST2, SET,
TDD, TII, TIN, TIA, TAI, BSR, BBS/BBR, TST, etc.)

Used by: PC Engine / TurboGrafx-16 reverse engineering.

Usage::

    from huc6280_disasm import disasm, disasm_bank, OPCODES, BANK_SIZE

    rom = open('game.pce', 'rb').read()

    # Disassemble a range within a ROM bank
    print(disasm_bank(rom, bank_num=0, start_offset=0x0000, end_offset=0x0095,
                      page_logical=0xE000, annotations={0xE000: "reset vector"}))

    # Disassemble raw bytes at arbitrary logical addresses
    bank_data = rom[0:0x2000]
    print(disasm(bank_data, start_logical=0xE000, end_logical=0xE095,
                 page_base=0xE000))
"""

# ── Constants ─────────────────────────────────────────────────────────────────

BANK_SIZE = 0x2000  # 8 KB per bank

# ── Opcode table ──────────────────────────────────────────────────────────────
# Each entry: opcode -> (mnemonic, size_in_bytes, format_string)

OPCODES: dict[int, tuple[str, int, str]] = {}


def _op(opcode: int, mnem: str, size: int, fmt: str = "") -> None:
    OPCODES[opcode] = (mnem, size, fmt)


# ── Implied / Accumulator (1 byte) ───────────────────────────────────────────
for _oc, _mn in [
    (0x00, "BRK"), (0x08, "PHP"), (0x0A, "ASL A"), (0x18, "CLC"), (0x1A, "INC A"),
    (0x28, "PLP"), (0x2A, "ROL A"), (0x38, "SEC"), (0x3A, "DEC A"),
    (0x40, "RTI"), (0x48, "PHA"), (0x4A, "LSR A"), (0x58, "CLI"), (0x5A, "PHY"),
    (0x60, "RTS"), (0x68, "PLA"), (0x6A, "ROR A"), (0x78, "SEI"), (0x7A, "PLY"),
    (0x80, "BRA"), (0x88, "DEY"), (0x8A, "TXA"), (0x98, "TYA"), (0x9A, "TXS"),
    (0xA8, "TAY"), (0xAA, "TAX"), (0xB8, "CLV"), (0xBA, "TSX"),
    (0xC8, "INY"), (0xCA, "DEX"), (0xD4, "CSH"), (0xD8, "CLD"), (0xDA, "PHX"),
    (0xE8, "INX"), (0xEA, "NOP"), (0xF4, "SET"), (0xF8, "SED"), (0xFA, "PLX"),
    (0xCB, "WAI"), (0xDB, "STP"), (0x54, "CSL"),
    (0x02, "SXY"), (0x22, "SAX"), (0x42, "SAY"),
    (0xFC, "???"),
]:
    _sz = 1
    _ft = ""
    if _oc == 0x80:
        _sz = 2
        _ft = "{rel}"
    _op(_oc, _mn, _sz, _ft)

# ── Immediate (2 bytes) ──────────────────────────────────────────────────────
for _oc, _mn in [
    (0x09, "ORA"), (0x29, "AND"), (0x49, "EOR"), (0x69, "ADC"), (0x89, "BIT"),
    (0xA0, "LDY"), (0xA2, "LDX"), (0xA9, "LDA"), (0xC0, "CPY"), (0xC9, "CMP"),
    (0xE0, "CPX"), (0xE9, "SBC"),
]:
    _op(_oc, _mn, 2, "{mn} #${b1:02X}")

# ── Zero Page (2 bytes) ──────────────────────────────────────────────────────
for _oc, _mn in [
    (0x04, "TSB"), (0x05, "ORA"), (0x06, "ASL"), (0x14, "TRB"), (0x24, "BIT"),
    (0x25, "AND"), (0x26, "ROL"), (0x45, "EOR"), (0x46, "LSR"),
    (0x64, "STZ"), (0x65, "ADC"), (0x66, "ROR"), (0x84, "STY"), (0x85, "STA"),
    (0x86, "STX"), (0xA4, "LDY"), (0xA5, "LDA"), (0xA6, "LDX"),
    (0xC4, "CPY"), (0xC5, "CMP"), (0xC6, "DEC"), (0xE4, "CPX"), (0xE5, "SBC"),
    (0xE6, "INC"),
]:
    _op(_oc, _mn, 2, "{mn} ${b1:02X}")

# ── Zero Page,X (2 bytes) ────────────────────────────────────────────────────
for _oc, _mn in [
    (0x15, "ORA"), (0x16, "ASL"), (0x34, "BIT"), (0x35, "AND"), (0x36, "ROL"),
    (0x55, "EOR"), (0x56, "LSR"), (0x74, "STZ"), (0x75, "ADC"), (0x76, "ROR"),
    (0x94, "STY"), (0x95, "STA"), (0xB4, "LDY"), (0xB5, "LDA"),
    (0xD5, "CMP"), (0xD6, "DEC"), (0xF5, "SBC"), (0xF6, "INC"),
]:
    _op(_oc, _mn, 2, "{mn} ${b1:02X},X")

# ── Zero Page,Y (2 bytes) ────────────────────────────────────────────────────
for _oc, _mn in [(0x96, "STX"), (0xB6, "LDX")]:
    _op(_oc, _mn, 2, "{mn} ${b1:02X},Y")

# ── (Zero Page) indirect (2 bytes) ───────────────────────────────────────────
for _oc, _mn in [
    (0x12, "ORA"), (0x32, "AND"), (0x52, "EOR"), (0x72, "ADC"),
    (0x92, "STA"), (0xB2, "LDA"), (0xD2, "CMP"), (0xF2, "SBC"),
]:
    _op(_oc, _mn, 2, "{mn} (${b1:02X})")

# ── (ZP,X) indexed indirect (2 bytes) ────────────────────────────────────────
for _oc, _mn in [
    (0x01, "ORA"), (0x21, "AND"), (0x41, "EOR"), (0x61, "ADC"),
    (0x81, "STA"), (0xA1, "LDA"), (0xC1, "CMP"), (0xE1, "SBC"),
]:
    _op(_oc, _mn, 2, "{mn} (${b1:02X},X)")

# ── (ZP),Y indirect indexed (2 bytes) ────────────────────────────────────────
for _oc, _mn in [
    (0x11, "ORA"), (0x31, "AND"), (0x51, "EOR"), (0x71, "ADC"),
    (0x91, "STA"), (0xB1, "LDA"), (0xD1, "CMP"), (0xF1, "SBC"),
]:
    _op(_oc, _mn, 2, "{mn} (${b1:02X}),Y")

# ── Absolute (3 bytes) ───────────────────────────────────────────────────────
for _oc, _mn in [
    (0x0C, "TSB"), (0x0D, "ORA"), (0x0E, "ASL"), (0x1C, "TRB"), (0x2C, "BIT"),
    (0x2D, "AND"), (0x2E, "ROL"), (0x4D, "EOR"), (0x4E, "LSR"),
    (0x6D, "ADC"), (0x6E, "ROR"), (0x8C, "STY"), (0x8D, "STA"), (0x8E, "STX"),
    (0x9C, "STZ"), (0xAC, "LDY"), (0xAD, "LDA"), (0xAE, "LDX"),
    (0xCC, "CPY"), (0xCD, "CMP"), (0xCE, "DEC"), (0xEC, "CPX"), (0xED, "SBC"),
    (0xEE, "INC"),
]:
    _op(_oc, _mn, 3, "{mn} ${abs:04X}")

# ── Absolute,X (3 bytes) ─────────────────────────────────────────────────────
for _oc, _mn in [
    (0x1D, "ORA"), (0x1E, "ASL"), (0x3C, "BIT"), (0x3D, "AND"), (0x3E, "ROL"),
    (0x5D, "EOR"), (0x5E, "LSR"), (0x7D, "ADC"), (0x7E, "ROR"),
    (0x9D, "STA"), (0x9E, "STZ"), (0xBC, "LDY"), (0xBD, "LDA"),
    (0xDD, "CMP"), (0xDE, "DEC"), (0xFD, "SBC"), (0xFE, "INC"),
]:
    _op(_oc, _mn, 3, "{mn} ${abs:04X},X")

# ── Absolute,Y (3 bytes) ─────────────────────────────────────────────────────
for _oc, _mn in [
    (0x19, "ORA"), (0x39, "AND"), (0x59, "EOR"), (0x79, "ADC"),
    (0x99, "STA"), (0xB9, "LDA"), (0xBE, "LDX"), (0xD9, "CMP"), (0xF9, "SBC"),
]:
    _op(_oc, _mn, 3, "{mn} ${abs:04X},Y")

# ── JMP / JSR (3 bytes) ──────────────────────────────────────────────────────
_op(0x4C, "JMP", 3, "JMP ${abs:04X}")
_op(0x6C, "JMP", 3, "JMP (${abs:04X})")
_op(0x7C, "JMP", 3, "JMP (${abs:04X},X)")
_op(0x20, "JSR", 3, "JSR ${abs:04X}")

# ── Branches (2 bytes, relative) ─────────────────────────────────────────────
for _oc, _mn in [
    (0x10, "BPL"), (0x30, "BMI"), (0x50, "BVC"), (0x70, "BVS"),
    (0x90, "BCC"), (0xB0, "BCS"), (0xD0, "BNE"), (0xF0, "BEQ"),
]:
    _op(_oc, _mn, 2, "{rel}")

# ── BSR (HuC6280: branch to subroutine, relative) ────────────────────────────
_op(0x44, "BSR", 2, "{rel}")

# ── TAM / TMA (2 bytes) ──────────────────────────────────────────────────────
_op(0x53, "TAM", 2, "TAM #${b1:02X}")
_op(0x43, "TMA", 2, "TMA #${b1:02X}")

# ── ST0 / ST1 / ST2 (2 bytes) ────────────────────────────────────────────────
_op(0x03, "ST0", 2, "ST0 #${b1:02X}")
_op(0x13, "ST1", 2, "ST1 #${b1:02X}")
_op(0x23, "ST2", 2, "ST2 #${b1:02X}")

# ── Block transfers (7 bytes) ────────────────────────────────────────────────
for _oc, _mn in [
    (0x73, "TII"), (0xC3, "TDD"), (0xD3, "TIN"), (0xE3, "TIA"), (0xF3, "TAI"),
]:
    _op(_oc, _mn, 7, "{mn} ${src:04X},${dst:04X},#{ln:04X}")

# ── BBR / BBS (3 bytes: opcode, zp, rel) ─────────────────────────────────────
for _bit in range(8):
    _op(0x0F + _bit * 0x10, f"BBR{_bit}", 3, "bbr_bbs")
    _op(0x8F + _bit * 0x10, f"BBS{_bit}", 3, "bbr_bbs")

# ── TST #imm,ZP (3 bytes) and TST #imm,ABS (4 bytes) ────────────────────────
_op(0x83, "TST", 3, "TST #${b1:02X},${b2:02X}")
_op(0xA3, "TST", 3, "TST #${b1:02X},${b2:02X},X")
_op(0x93, "TST", 4, "TST #${b1:02X},${abs2:04X}")
_op(0xB3, "TST", 4, "TST #${b1:02X},${abs2:04X},X")

# Clean up module namespace
del _oc, _mn, _sz, _ft, _bit, _op


# ── Disassembler functions ────────────────────────────────────────────────────

def disasm(
    bank_data: bytes,
    start_logical: int,
    end_logical: int,
    page_base: int,
    annotations: dict[int, str] | None = None,
) -> str:
    """Disassemble ROM bank data from logical addresses.

    Args:
        bank_data:      Bytes of a single bank (or larger region).
        start_logical:  First logical address to disassemble.
        end_logical:    Last logical address (inclusive).
        page_base:      Logical base address of the bank (e.g. 0xE000 for page 7).
        annotations:    Optional dict  {logical_addr: comment_string}.

    Returns:
        Multi-line string with formatted disassembly.
    """
    if annotations is None:
        annotations = {}

    lines: list[str] = []
    pc = start_logical

    while pc <= end_logical:
        rom_off = pc - page_base  # offset within bank_data
        if rom_off < 0 or rom_off >= len(bank_data):
            lines.append(f"  ${pc:04X}  *** OUT OF RANGE ***")
            break

        op = bank_data[rom_off]

        if op not in OPCODES:
            lines.append(f"  ${pc:04X}  {op:02X}                    .db ${op:02X}")
            pc += 1
            continue

        mnem, size, fmt = OPCODES[op]
        if rom_off + size > len(bank_data):
            lines.append(f"  ${pc:04X}  {op:02X}                    .db ${op:02X}  ; truncated")
            break

        raw = bank_data[rom_off : rom_off + size]
        hex_str = " ".join(f"{b:02X}" for b in raw)

        # Format instruction
        if size == 1 and not fmt:
            instr = mnem
        elif fmt == "{rel}":
            offset = raw[1]
            if offset >= 0x80:
                offset -= 0x100
            target = pc + 2 + offset
            instr = f"{mnem} ${target:04X}"
        elif fmt == "bbr_bbs":
            zp_addr = raw[1]
            offset = raw[2]
            if offset >= 0x80:
                offset -= 0x100
            target = pc + 3 + offset
            instr = f"{mnem} ${zp_addr:02X},${target:04X}"
        elif size == 7:
            src = raw[1] | (raw[2] << 8)
            dst = raw[3] | (raw[4] << 8)
            ln = raw[5] | (raw[6] << 8)
            instr = f"{mnem} ${src:04X},${dst:04X},#${ln:04X}"
        elif size == 4:  # TST imm,abs
            b1 = raw[1]
            abs2 = raw[2] | (raw[3] << 8)
            suffix = ",X" if op == 0xB3 else ""
            instr = f"TST #${b1:02X},${abs2:04X}{suffix}"
        elif "{abs:04X}" in fmt:
            abs_addr = raw[1] | (raw[2] << 8)
            instr = fmt.format(
                mn=mnem, abs=abs_addr, b1=raw[1], b2=raw[2] if size > 2 else 0
            )
        elif size == 3 and fmt not in ("bbr_bbs",) and op not in (0x93, 0xB3):
            instr = fmt.format(mn=mnem, b1=raw[1], b2=raw[2])
        else:
            b1 = raw[1] if size > 1 else 0
            instr = fmt.format(mn=mnem, b1=b1)

        ann = annotations.get(pc, "")
        ann_str = f"  ; {ann}" if ann else ""

        lines.append(f"  ${pc:04X}  {hex_str:<20s}  {instr}{ann_str}")
        pc += size

    return "\n".join(lines)


def disasm_bank(
    rom_data: bytes,
    bank_num: int,
    start_offset: int,
    end_offset: int,
    page_logical: int = 0xE000,
    annotations: dict[int, str] | None = None,
) -> str:
    """Disassemble a range within a specific ROM bank.

    Args:
        rom_data:       Full ROM bytes.
        bank_num:       Bank number (0-based).
        start_offset:   Offset within the bank (0x0000–0x1FFF).
        end_offset:     End offset within the bank (inclusive).
        page_logical:   Logical base address this bank is mapped to.
        annotations:    Optional dict  {logical_addr: comment_string}.

    Returns:
        Multi-line string with formatted disassembly.
    """
    bank_rom = bank_num * BANK_SIZE
    bank_data = rom_data[bank_rom : bank_rom + BANK_SIZE]
    start_log = page_logical + start_offset
    end_log = page_logical + end_offset
    return disasm(bank_data, start_log, end_log, page_logical, annotations)


def get_bank(rom_data: bytes, bank_num: int) -> bytes:
    """Extract a single bank from the ROM.

    Args:
        rom_data:   Full ROM bytes.
        bank_num:   Bank number (0-based).

    Returns:
        8 KB bank as bytes.
    """
    offset = bank_num * BANK_SIZE
    return rom_data[offset : offset + BANK_SIZE]


def rom_info(rom_data: bytes) -> dict:
    """Return basic ROM info (size, banks, CRC32).

    Args:
        rom_data: Full ROM bytes.

    Returns:
        Dict with keys: size_kb, num_banks, crc32.
    """
    import zlib

    return {
        "size_kb": len(rom_data) // 1024,
        "num_banks": len(rom_data) // BANK_SIZE,
        "crc32": zlib.crc32(rom_data) & 0xFFFFFFFF,
    }


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"HuC6280 opcode table: {len(OPCODES)} opcodes defined")
    print(f"Bank size: {BANK_SIZE} bytes (0x{BANK_SIZE:04X})")
    print()

    # Quick sanity checks
    assert OPCODES[0xEA] == ("NOP", 1, ""), "NOP mismatch"
    assert OPCODES[0x20][0] == "JSR", "JSR mismatch"
    assert OPCODES[0x4C][0] == "JMP", "JMP mismatch"
    assert OPCODES[0x73][0] == "TII", "TII mismatch"
    assert OPCODES[0x53][0] == "TAM", "TAM mismatch"
    assert OPCODES[0x0F][0] == "BBR0", "BBR0 mismatch"
    assert OPCODES[0x8F][0] == "BBS0", "BBS0 mismatch"
    print("All sanity checks passed.")

    # Test disassembly with some known bytes
    test_bytes = bytes([
        0xD4,                   # CSH
        0x78,                   # SEI
        0xA9, 0xFF,             # LDA #$FF
        0x53, 0x02,             # TAM #$02
        0x20, 0x00, 0xF0,       # JSR $F000
        0x4C, 0x00, 0xE0,       # JMP $E000
    ])
    print()
    print("Test disassembly:")
    print(disasm(test_bytes, 0xE000, 0xE00B, 0xE000, {0xE000: "high speed mode"}))
