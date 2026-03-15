"""
patch_gunhed.py — Standalone Gunhed ROM Patcher
================================================
Patches the original Gunhed (Japan) ROM with:

  1. Louder volume — PSG register patches (music + DDA at hardware max)
  2. Custom WAV injection — replaces DDA voice SFX with edited WAVs
  3. (Optional) Sound test boot — boots directly to SOUND 01 menu

No external dependencies beyond Python stdlib.

Usage:
    python patch_gunhed.py [options]

Options:
    --boot              Enable sound test direct-boot (default: off)
    --wav-dir DIR       Custom WAV folder (default: bin/voice_sfx_custom)
    --rom PATH          Source ROM path (default: Gunhed (Japan).pce)
    --output PATH       Output ROM path (default: bin/Gunhed_patched.pce)

Examples:
    python patch_gunhed.py                          # louder + custom WAVs
    python patch_gunhed.py --boot                   # + boot to sound test
    python patch_gunhed.py --wav-dir my_wavs/       # custom WAV folder
    python patch_gunhed.py --output my_rom.pce      # custom output path
"""

import os
import sys
import struct
import wave
import zlib
import random
from collections import defaultdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_CRC32  = 0xA17D4D7E
BANK_SIZE       = 0x2000     # 8 KB
PAGE6_BASE      = 0xC000
DDA_SAMPLE_RATE = 6991       # Hz
DESC_TABLE_ROM  = 0x278D0
DESC_ENTRY_SIZE = 8
VOICE_SFX_FIRST = 16
VOICE_SFX_COUNT = 8

# ---------------------------------------------------------------------------
# Patch definitions
# ---------------------------------------------------------------------------

# Louder volume — 3 PSG register byte changes
LOUDER_PATCHES = [
    (0x261A9, 0x80, 0x8F, "Music ORA #$8F — vol floor 15/31"),
    (0x26571, 0xC0, 0xCF, "DDA voice ORA #$CF — vol 15/31, pan L15/R15"),
    (0x2687A, 0xC0, 0xCF, "DDA music ORA #$CF — vol 15/31"),
]

# Sound test direct-boot — two-site patch (9 bytes)
BOOT_PATCHES = [
    (0x10024,
     bytes([0x20, 0x22, 0xEF, 0x00, 0xC2, 0x49]),
     bytes([0xEA, 0xEA, 0xEA, 0xEA, 0xEA, 0xEA]),
     "NOP x6 — skip far-call stop sound"),
    (0x10047,
     bytes([0xA9, 0x00, 0x93]),
     bytes([0x4C, 0x62, 0x41]),
     "JMP $4162 — skip intro, jump to menu"),
]

# ---------------------------------------------------------------------------
# WAV reading — handles 8/16/24-bit PCM, mono/stereo, any sample rate
# ---------------------------------------------------------------------------

def read_wav(path):
    with wave.open(path, 'r') as wf:
        nch = wf.getnchannels()
        sw  = wf.getsampwidth()
        sr  = wf.getframerate()
        nf  = wf.getnframes()
        raw = wf.readframes(nf)

    if sw == 1:
        samples = [b / 255.0 for b in raw]
    elif sw == 2:
        n = len(raw) // 2
        vals = struct.unpack(f'<{n}h', raw)
        samples = [(v + 32768) / 65535.0 for v in vals]
    elif sw == 3:
        samples = []
        for i in range(0, len(raw), 3):
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if val & 0x800000:
                val -= 0x1000000
            samples.append((val + 8388608) / 16777215.0)
    else:
        raise ValueError(
            f"Unsupported WAV bit depth: {sw * 8}-bit. "
            f"Export as 'Signed 16-bit PCM' in Audacity."
        )

    if nch > 1:
        mono = []
        for i in range(0, len(samples), nch):
            mono.append(sum(samples[i:i + nch]) / nch)
        samples = mono

    return samples, sr

# ---------------------------------------------------------------------------
# Resampling — linear interpolation
# ---------------------------------------------------------------------------

def resample_linear(samples, src_rate, dst_rate):
    if src_rate == dst_rate or not samples:
        return samples
    out_len = max(1, round(len(samples) * dst_rate / src_rate))
    ratio = src_rate / dst_rate
    result = []
    for i in range(out_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(samples):
            val = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        else:
            val = samples[min(idx, len(samples) - 1)]
        result.append(val)
    return result

# ---------------------------------------------------------------------------
# Quantize + pack
# ---------------------------------------------------------------------------

def quantize_to_nibbles(samples, dither=True):
    result = []
    for s in samples:
        v = s * 15.0
        if dither:
            v += random.random() - 0.5 + random.random() - 0.5
        result.append(max(0, min(15, round(v))))
    return result


def pack_nibbles(nibbles):
    if len(nibbles) % 2 != 0:
        nibbles = list(nibbles) + [0]
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        out.append((nibbles[i + 1] << 4) | nibbles[i])
    return bytes(out)

# ---------------------------------------------------------------------------
# ROM region computation
# ---------------------------------------------------------------------------

def compute_sound_regions(original_rom):
    descs = []
    for i in range(VOICE_SFX_FIRST, VOICE_SFX_FIRST + VOICE_SFX_COUNT):
        off = DESC_TABLE_ROM + i * DESC_ENTRY_SIZE
        ptr_lo   = original_rom[off + 2]
        ptr_hi   = original_rom[off + 3]
        bank     = original_rom[off + 6]
        ptr_logical = (ptr_hi << 8) | ptr_lo
        rom_start   = bank * BANK_SIZE + (ptr_logical - PAGE6_BASE)
        sound_id    = 0x33 + (i - VOICE_SFX_FIRST)

        # Scan for 0x00 end marker
        end_rom = rom_start
        limit = min(rom_start + 0x4000, len(original_rom))
        for j in range(rom_start, limit):
            if original_rom[j] == 0x00:
                end_rom = j
                break
        else:
            end_rom = limit

        descs.append({
            'sound_id':   sound_id,
            'bank':       bank,
            'rom_start':  rom_start,
            'orig_bytes': end_rom - rom_start,
            'end_rom':    end_rom,
        })

    by_bank = defaultdict(list)
    for d in descs:
        by_bank[d['bank']].append(d)

    for bank, group in by_bank.items():
        group.sort(key=lambda d: d['rom_start'])
        bank_end = (bank + 1) * BANK_SIZE
        for gi, d in enumerate(group):
            if gi + 1 < len(group):
                d['max_bytes'] = group[gi + 1]['rom_start'] - d['rom_start'] - 1
            else:
                d['max_bytes'] = bank_end - d['rom_start'] - 1

    return descs

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    boot = False
    wav_dir = os.path.join("..", "assets", "voice_sfx_custom")
    rom_path = os.path.join(SCRIPT_DIR, "Gunhed (Japan).pce")
    output = os.path.join(SCRIPT_DIR, "Gunhed_patched.pce")

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--boot':
            boot = True
        elif args[i] == '--wav-dir' and i + 1 < len(args):
            i += 1
            wav_dir = args[i]
        elif args[i] == '--rom' and i + 1 < len(args):
            i += 1
            rom_path = args[i]
        elif args[i] == '--output' and i + 1 < len(args):
            i += 1
            output = args[i]
        elif args[i] in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown option: {args[i]}")
            print("Use --help for usage.")
            sys.exit(1)
        i += 1

    return boot, wav_dir, rom_path, output

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    boot, wav_dir, rom_path, output_path = parse_args()

    # --- Load original ROM ---
    print(f"Loading ROM: {rom_path}")
    with open(rom_path, 'rb') as f:
        rom = bytearray(f.read())

    crc = zlib.crc32(rom) & 0xFFFFFFFF
    if crc != ORIGINAL_CRC32:
        print(f"  WARNING: CRC32 {crc:08X} != expected {ORIGINAL_CRC32:08X}")
    else:
        print(f"  CRC32: {crc:08X}  ({len(rom):,} bytes)")

    original_rom = bytes(rom)  # keep unpatched copy for region computation

    # =====================================================================
    # 1. Louder volume patches
    # =====================================================================
    print(f"\n{'─' * 60}")
    print("1. Louder volume patches (3 bytes)")
    print(f"{'─' * 60}")

    for offset, orig, patched, desc in LOUDER_PATCHES:
        actual = rom[offset]
        if actual != orig:
            print(f"  ERROR at ${offset:05X}: expected ${orig:02X}, found ${actual:02X}")
            sys.exit(1)
        rom[offset] = patched
        print(f"  ${offset:05X}: ${orig:02X} -> ${patched:02X}  {desc}")

    # =====================================================================
    # 2. Sound test boot patch (optional)
    # =====================================================================
    print(f"\n{'─' * 60}")
    if boot:
        print("2. Sound test boot patch (9 bytes)")
    else:
        print("2. Sound test boot patch — SKIPPED (use --boot to enable)")
    print(f"{'─' * 60}")

    if boot:
        for offset, orig_bytes, patch_bytes, desc in BOOT_PATCHES:
            actual = bytes(rom[offset:offset + len(orig_bytes)])
            if actual != orig_bytes:
                print(f"  ERROR at ${offset:05X}: expected {orig_bytes.hex(' ').upper()}, "
                      f"found {actual.hex(' ').upper()}")
                sys.exit(1)
            rom[offset:offset + len(patch_bytes)] = patch_bytes
            print(f"  ${offset:05X}: {orig_bytes.hex(' ').upper()} -> {patch_bytes.hex(' ').upper()}")
            print(f"           {desc}")

    # =====================================================================
    # 3. Custom WAV injection
    # =====================================================================
    print(f"\n{'─' * 60}")
    print("3. Custom WAV injection")
    print(f"{'─' * 60}")

    if not os.path.isdir(wav_dir):
        print(f"  WAV folder not found: {wav_dir}")
        print(f"  Skipping WAV injection.")
    else:
        regions = compute_sound_regions(original_rom)

        # Find WAV files
        wav_files = {}
        for fname in sorted(os.listdir(wav_dir)):
            if not fname.lower().endswith('.wav'):
                continue
            base = os.path.splitext(fname)[0].lower()
            if base.startswith('sound_') and len(base) == 8:
                try:
                    sid = int(base[6:8], 16)
                    if 0x33 <= sid <= 0x3A:
                        wav_files[sid] = os.path.join(wav_dir, fname)
                except ValueError:
                    pass

        if not wav_files:
            print(f"  No sound_XX.wav files found in {wav_dir}")
        else:
            print(f"  Found {len(wav_files)} WAV(s): "
                  + ", ".join(f"s${sid:02X}" for sid in sorted(wav_files.keys())))
            print()
            print(f"  {'Sound':>6}  {'Rate':>6}  {'Samples':>8}  "
                  f"{'Bytes':>6}  {'Max':>5}  {'Status':>12}  {'Peak':>4}")
            print(f"  {'─' * 60}")

            injected = 0
            for r in regions:
                sid = r['sound_id']
                if sid not in wav_files:
                    print(f"  s${sid:02X}   {'—':>6}  {'—':>8}  "
                          f"{'—':>6}  {r['max_bytes']:>5}  {'(original)':>12}")
                    continue

                try:
                    samples_f, wav_rate = read_wav(wav_files[sid])
                except Exception as e:
                    print(f"  s${sid:02X}   ERROR: {e}")
                    continue

                wav_count = len(samples_f)
                if wav_rate != DDA_SAMPLE_RATE:
                    samples_f = resample_linear(samples_f, wav_rate, DDA_SAMPLE_RATE)

                nibbles = quantize_to_nibbles(samples_f)
                peak = max(nibbles) if nibbles else 0
                packed = pack_nibbles(nibbles)
                new_bytes = len(packed)
                max_b = r['max_bytes']

                status = "OK"
                if new_bytes > max_b:
                    packed = packed[:max_b]
                    new_bytes = max_b
                    status = "TRUNCATED"
                elif new_bytes < r['orig_bytes']:
                    status = f"-{r['orig_bytes'] - new_bytes}"
                elif new_bytes > r['orig_bytes']:
                    status = f"+{new_bytes - r['orig_bytes']}"
                else:
                    status = "exact"

                rom_start = r['rom_start']
                for i, b in enumerate(packed):
                    rom[rom_start + i] = b
                pad_end = rom_start + max(r['orig_bytes'], new_bytes)
                for i in range(rom_start + new_bytes, pad_end):
                    rom[i] = 0x00
                if rom_start + new_bytes < len(rom):
                    rom[rom_start + new_bytes] = 0x00

                print(f"  s${sid:02X}   {wav_rate:>6}  {wav_count:>8}  "
                      f"{new_bytes:>6}  {max_b:>5}  {status:>12}  {peak:>4}")
                injected += 1

            print(f"\n  Injected: {injected} sound(s)")

    # =====================================================================
    # Write output
    # =====================================================================
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(rom)

    out_crc = zlib.crc32(rom) & 0xFFFFFFFF
    total_diffs = sum(1 for a, b in zip(original_rom, rom) if a != b)
    patches = "louder + custom WAVs" + (" + boot" if boot else "")

    print(f"\n{'=' * 60}")
    print(f"  Output:   {output_path}")
    print(f"  CRC32:    {out_crc:08X}")
    print(f"  Changed:  {total_diffs:,} bytes (vs original)")
    print(f"  Patches:  {patches}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
