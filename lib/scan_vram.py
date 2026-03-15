#!/usr/bin/env python3
"""Scan Gunhed ROM bank $08 for VRAM-related opcodes."""

import struct

# HuC6280 instruction lengths
op_len = [1] * 256

# 2-byte: immediate, zp, zpx, (zp,x), (zp),y, (zp), relative, ST0/ST1/ST2
for op in [0x09,0x29,0x49,0x69,0x89,0xA0,0xA2,0xA9,0xC0,0xC9,0xE0,0xE9,
           0x05,0x06,0x24,0x25,0x26,0x45,0x46,0x64,0x65,0x66,0x84,0x85,0x86,
           0xA4,0xA5,0xA6,0xC4,0xC5,0xC6,0xE4,0xE5,0xE6,
           0x15,0x16,0x34,0x35,0x36,0x55,0x56,0x74,0x75,0x76,0x94,0x95,
           0xB4,0xB5,0xD5,0xD6,0xF5,0xF6, 0x96,0xB6,
           0x01,0x21,0x41,0x61,0x81,0xA1,0xC1,0xE1,  # (zp,x)
           0x11,0x31,0x51,0x71,0x91,0xB1,0xD1,0xF1,  # (zp),y
           0x12,0x32,0x52,0x72,0x92,0xB2,0xD2,0xF2,  # (zp)
           0x10,0x30,0x50,0x70,0x90,0xB0,0xD0,0xF0,0x80,  # branches
           0x03,0x13,0x23,  # ST0, ST1, ST2
           0x04,0x14,  # TSB/TRB zp
           0x44,  # BSR
           0x53,0x43,  # TAM, TMA
           ]:
    op_len[op] = 2

# 3-byte: absolute addressing modes, JSR, JMP
for op in [0x0D,0x0E,0x0C,0x1C,0x2C,0x2D,0x2E,0x4D,0x4E,0x4C,0x6D,0x6E,
           0x8C,0x8D,0x8E,0xAC,0xAD,0xAE,0xCC,0xCD,0xCE,0xEC,0xED,0xEE,
           0x1D,0x1E,0x3D,0x3E,0x5D,0x5E,0x7D,0x7E,0x9D,0xBD,0xBC,0xBE,
           0xDD,0xDE,0xFD,0xFE,
           0x19,0x39,0x59,0x79,0x99,0xB9,0xD9,0xF9,  # abs,y
           0x20,  # JSR
           0x6C,  # JMP (abs)
           0x9C,  # STZ abs
           ]:
    op_len[op] = 3

# BBR/BBS: 3-byte (zp, relative)
for op in range(0x0F, 0x100, 0x10):
    op_len[op] = 3

# Block transfers: 7-byte
for op in [0xE3, 0x73, 0xD3, 0xC3, 0xF3]:
    op_len[op] = 7

# 1-byte implied
for op in [0x22, 0x42, 0x82, 0x62, 0x02, 0xD4, 0x54]:
    op_len[op] = 1

# VDC register names
VDC_REGS = {
    0x00: "MAWR (VRAM write address)",
    0x01: "MARR (VRAM read address)",
    0x02: "VWR (VRAM data write)",
    0x05: "CR (Control)",
    0x06: "RCR (Raster Counter)",
    0x07: "BXR (BG X-scroll)",
    0x08: "BYR (BG Y-scroll)",
    0x09: "MWR (Memory Access Width)",
    0x0A: "HSR (Horiz Sync)",
    0x0B: "HDR (Horiz Display)",
    0x0C: "VPR (Vert Position)",
    0x0D: "VDW (Vert Display Width)",
    0x0E: "VCR (Vert Display End)",
    0x0F: "DCR (DMA Control)",
    0x10: "SOUR (DMA Source)",
    0x11: "DESR (DMA Destination)",
    0x12: "LENR (DMA Length)",
    0x13: "DVSSR (VRAM-SATB src)",
}

BANK_BASE = 0x10000  # ROM offset for bank $08
LOG_BASE = 0x4000    # Logical address base

with open(r"E:\ProjectsGe\Coding\PCEngine\RE\Gunhed\Gunhed (Japan).pce", "rb") as f:
    rom = f.read()

print(f"ROM size: {len(rom)} bytes ({len(rom)//1024} KB)")
print()

# Ranges to scan
ranges = [
    (0x10005, 0x10162, "$4005-$4162 (main code region)"),
    (0x10162, 0x10260, "$4162-$4260 (menu setup region)"),
]

all_results = []

for rstart, rend, label in ranges:
    print(f"{'='*70}")
    print(f"  SCANNING: {label}")
    print(f"  ROM offsets: 0x{rstart:05X} - 0x{rend:05X}")
    print(f"{'='*70}")
    print()
    
    i = rstart
    section_results = []
    
    while i <= rend:
        op = rom[i]
        log_addr = LOG_BASE + (i - BANK_BASE)
        ilen = op_len[op]
        
        entry = None
        
        # ST0 - Select VDC register
        if op == 0x03 and i + 1 <= rend:
            imm = rom[i + 1]
            reg_name = VDC_REGS.get(imm, f"reg #{imm:02X}")
            vram_related = "*** VRAM ***" if imm in (0x00, 0x01, 0x02, 0x10, 0x11, 0x12, 0x0F, 0x13) else ""
            entry = {
                'rom': i, 'log': log_addr, 'bytes': f'03 {imm:02X}',
                'asm': f'ST0 #${imm:02X}',
                'desc': f'Select VDC register: {reg_name} {vram_related}'
            }
        
        # ST1 - Write low byte to VDC
        elif op == 0x13 and i + 1 <= rend:
            imm = rom[i + 1]
            entry = {
                'rom': i, 'log': log_addr, 'bytes': f'13 {imm:02X}',
                'asm': f'ST1 #${imm:02X}',
                'desc': f'Write low byte ${imm:02X} to selected VDC register'
            }
        
        # ST2 - Write high byte to VDC
        elif op == 0x23 and i + 1 <= rend:
            imm = rom[i + 1]
            entry = {
                'rom': i, 'log': log_addr, 'bytes': f'23 {imm:02X}',
                'asm': f'ST2 #${imm:02X}',
                'desc': f'Write high byte ${imm:02X} to selected VDC register'
            }
        
        # TIA - Block transfer to I/O
        elif op == 0xE3 and i + 6 <= rend:
            src = rom[i+1] | (rom[i+2] << 8)
            dst = rom[i+3] | (rom[i+4] << 8)
            length = rom[i+5] | (rom[i+6] << 8)
            raw = ' '.join(f'{rom[i+j]:02X}' for j in range(7))
            note = ""
            if dst == 0x0002:
                note = " *** WRITES TO VDC DATA PORT 0 (like repeated ST1) ***"
            elif dst == 0x0003:
                note = " *** WRITES TO VDC DATA PORT 1 (like repeated ST2) ***"
            entry = {
                'rom': i, 'log': log_addr, 'bytes': raw,
                'asm': f'TIA ${src:04X}, ${dst:04X}, ${length:04X}',
                'desc': f'Block transfer {length} bytes from ${src:04X} to ${dst:04X}{note}'
            }
        
        # TII - Block transfer increment
        elif op == 0x73 and i + 6 <= rend:
            src = rom[i+1] | (rom[i+2] << 8)
            dst = rom[i+3] | (rom[i+4] << 8)
            length = rom[i+5] | (rom[i+6] << 8)
            raw = ' '.join(f'{rom[i+j]:02X}' for j in range(7))
            note = ""
            if dst == 0x0002:
                note = " *** WRITES TO VDC DATA PORT 0 ***"
            elif dst == 0x0003:
                note = " *** WRITES TO VDC DATA PORT 1 ***"
            entry = {
                'rom': i, 'log': log_addr, 'bytes': raw,
                'asm': f'TII ${src:04X}, ${dst:04X}, ${length:04X}',
                'desc': f'Block transfer (inc) {length} bytes from ${src:04X} to ${dst:04X}{note}'
            }
        
        # JSR - Jump to subroutine
        elif op == 0x20 and i + 2 <= rend:
            target = rom[i+1] | (rom[i+2] << 8)
            note = ""
            if target >= 0xF000:
                note = " [BIOS/System]"
            elif target >= 0xE000:
                note = " [Library $E000+]"
            elif 0x4000 <= target <= 0x5FFF:
                note = " [Bank $08 local]"
            entry = {
                'rom': i, 'log': log_addr, 'bytes': f'20 {rom[i+1]:02X} {rom[i+2]:02X}',
                'asm': f'JSR ${target:04X}',
                'desc': f'Call subroutine at ${target:04X}{note}'
            }
        
        # JMP absolute
        elif op == 0x4C and i + 2 <= rend:
            target = rom[i+1] | (rom[i+2] << 8)
            note = ""
            if target >= 0xF000:
                note = " [BIOS/System]"
            elif target >= 0xE000:
                note = " [Library $E000+]"
            elif 0x4000 <= target <= 0x5FFF:
                note = " [Bank $08 local]"
            entry = {
                'rom': i, 'log': log_addr, 'bytes': f'4C {rom[i+1]:02X} {rom[i+2]:02X}',
                'asm': f'JMP ${target:04X}',
                'desc': f'Jump to ${target:04X}{note}'
            }
        
        if entry:
            section_results.append(entry)
            all_results.append(entry)
        
        i += ilen
    
    # Print results for this range
    for e in section_results:
        print(f"  0x{e['rom']:05X}  ${e['log']:04X}  [{e['bytes']:20s}]  {e['asm']:30s}  {e['desc']}")
    print()

# Summary: group VRAM write sequences
print()
print(f"{'='*70}")
print("  VRAM WRITE SEQUENCE ANALYSIS")
print(f"{'='*70}")
print()

# Find ST0/ST1/ST2 clusters
vdc_ops = [r for r in all_results if r['asm'].startswith('ST0') or r['asm'].startswith('ST1') or r['asm'].startswith('ST2')]
print(f"Total VDC direct operations (ST0/ST1/ST2): {len(vdc_ops)}")
for e in vdc_ops:
    print(f"  ${e['log']:04X}: {e['asm']:20s} — {e['desc']}")

print()
tia_ops = [r for r in all_results if r['asm'].startswith('TIA') or r['asm'].startswith('TII')]
print(f"Total block transfers (TIA/TII): {len(tia_ops)}")
for e in tia_ops:
    print(f"  ${e['log']:04X}: {e['asm']:40s} — {e['desc']}")

print()
jsr_ops = [r for r in all_results if r['asm'].startswith('JSR')]
print(f"Total JSR calls: {len(jsr_ops)}")
for e in jsr_ops:
    print(f"  ${e['log']:04X}: {e['asm']:20s} — {e['desc']}")

print()
jmp_ops = [r for r in all_results if r['asm'].startswith('JMP')]
print(f"Total JMP jumps: {len(jmp_ops)}")
for e in jmp_ops:
    print(f"  ${e['log']:04X}: {e['asm']:20s} — {e['desc']}")
