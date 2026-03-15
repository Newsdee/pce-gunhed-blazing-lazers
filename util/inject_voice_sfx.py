"""
inject_voice_sfx.py
====================
Inject custom WAV files into the Gunhed ROM as DDA voice SFX.

Workflow:
  1. Extract originals:       python extract_voice_sfx.py
  2. Copy to custom folder:   copy bin/voice_sfx/*.wav  bin/voice_sfx_custom/
  3. Edit in Audacity (normalize, compress, EQ, etc.)
  4. Export each file back as WAV (any format — see below)
  5. Inject:                  python inject_voice_sfx.py

Only WAV files named sound_XX.wav (XX = 33..3A hex) found in the input folder
are injected. Missing files → original ROM data is kept unchanged.

Accepted WAV formats (Audacity export):
  - Bit depth: 8-bit unsigned, 16-bit signed PCM, or 24-bit signed PCM
  - Sample rate: any (automatically resampled to 6991 Hz via linear interpolation)
  - Channels: mono or stereo (stereo is mixed down to mono)
  - *** 32-bit float WAV is NOT supported by Python's wave module ***
    → In Audacity: File → Export Audio → Format = WAV, Encoding = Signed 16-bit PCM

Recommended Audacity export settings for best results:
  - Format: WAV (Microsoft)
  - Encoding: Signed 16-bit PCM
  - Sample rate: 6991 Hz  (avoids resampling — keeps it exact)
  - Channels: Mono

Size constraint:
  Each sound has a fixed region in ROM (consecutive phrases within a bank).
  The injected sample must fit within the original byte count.
  If shorter → padded with silence (0x00).
  If longer → truncated (with warning).

Usage:
    python inject_voice_sfx.py [input_folder] [base_rom] [output_rom]

Defaults:
    input_folder:  bin/voice_sfx_custom
    base_rom:      bin/Gunhed_louder_v5.pce   (v5 = PSG register patches applied)
    output_rom:    bin/Gunhed_custom.pce
"""

import os
import sys
import struct
import wave
import zlib
import math

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INPUT_DIR = "../assets/voice_sfx_custom"
BASE_ROM  = "./Gunhed (Japan).pce"
OUT_ROM   = "./gunhed_custom.pce"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BANK_SIZE       = 0x2000    # 8 KB
PAGE6_BASE      = 0xC000
DDA_SAMPLE_RATE = 6991      # Hz
ORIGINAL_CRC32  = 0xA17D4D7E

DESC_TABLE_ROM  = 0x278D0
DESC_ENTRY_SIZE = 8
VOICE_SFX_FIRST = 16
VOICE_SFX_COUNT = 8

# Sound regions: (sound_id, rom_start, original_byte_length)
# original_byte_length = number of sample bytes before the 0x00 end marker
# These are computed from the original ROM and hardcoded for robustness.
# The max_bytes is the distance to the next phrase or bank end (minus 1 for
# the trailing 0x00 terminator).

SOUND_REGIONS = None  # computed at runtime from ROM


# ---------------------------------------------------------------------------
# WAV reading — handles 8/16/24-bit PCM, mono/stereo, any sample rate
# ---------------------------------------------------------------------------

def read_wav(path: str) -> tuple[list[float], int]:
    """
    Read a WAV file and return (samples, sample_rate).

    samples: list of float in [0.0, 1.0] range
             0.0 = minimum DAC output (nibble 0)
             1.0 = maximum DAC output (nibble 15)
             0.5 ≈ center / silence (nibble 7–8)

    Handles:
      - 8-bit unsigned PCM
      - 16-bit signed PCM
      - 24-bit signed PCM
      - Mono and stereo (stereo → mono mixdown)
    """
    with wave.open(path, 'r') as wf:
        nch = wf.getnchannels()
        sw  = wf.getsampwidth()
        sr  = wf.getframerate()
        nf  = wf.getnframes()
        raw = wf.readframes(nf)

    # Decode raw bytes to float [0.0, 1.0]
    if sw == 1:
        # 8-bit unsigned: 0–255 → 0.0–1.0
        samples = [b / 255.0 for b in raw]
    elif sw == 2:
        # 16-bit signed little-endian: -32768..+32767 → 0.0..1.0
        n = len(raw) // 2
        vals = struct.unpack(f'<{n}h', raw)
        samples = [(v + 32768) / 65535.0 for v in vals]
    elif sw == 3:
        # 24-bit signed little-endian: -8388608..+8388607 → 0.0..1.0
        samples = []
        for i in range(0, len(raw), 3):
            val = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if val & 0x800000:
                val -= 0x1000000  # sign-extend
            samples.append((val + 8388608) / 16777215.0)
    else:
        raise ValueError(
            f"Unsupported WAV sample width: {sw} bytes ({sw*8}-bit).\n"
            f"In Audacity: Export as 'Signed 16-bit PCM' WAV."
        )

    # Mix stereo → mono
    if nch > 1:
        mono = []
        for i in range(0, len(samples), nch):
            mono.append(sum(samples[i:i + nch]) / nch)
        samples = mono

    return samples, sr


# ---------------------------------------------------------------------------
# Resampling — linear interpolation (no scipy dependency)
# ---------------------------------------------------------------------------

def resample_linear(samples: list[float], src_rate: int, dst_rate: int) -> list[float]:
    """Resample via linear interpolation. No-op if rates match."""
    if src_rate == dst_rate:
        return samples
    if not samples:
        return []
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

def quantize_to_nibbles(samples: list[float], dither: bool = True) -> list[int]:
    """
    Convert float [0.0, 1.0] samples to 4-bit nibble values [0, 15].

    0.0 → nibble 0  (PCE DAC minimum)
    1.0 → nibble 15 (PCE DAC maximum)

    When dither=True, applies TPDF (triangular probability density function)
    dither before quantization. This replaces harsh quantization distortion
    with gentle uncorrelated noise — the standard technique for low-bit-depth
    audio. Without dithering, the hard 4-bit rounding creates audible
    correlated artifacts that sound "crunchy" or compressed.
    """
    import random
    result = []
    for s in samples:
        v = s * 15.0
        if dither:
            # TPDF dither: sum of two uniform random values [-0.5, +0.5]
            # This gives triangular distribution in [-1, +1] range,
            # which is the optimal dither amplitude for rounding quantization.
            d = random.random() - 0.5 + random.random() - 0.5
            v += d
        result.append(max(0, min(15, round(v))))
    return result


def pack_nibbles(nibbles: list[int]) -> bytes:
    """
    Pack nibble pairs into bytes: low nibble first, high nibble second.

    If odd number of nibbles, the last byte has hi nibble = 0.
    This matches the PCE DDA playback order:
      byte & 0x0F → first sample, (byte >> 4) & 0x0F → second sample.
    """
    if len(nibbles) % 2 != 0:
        nibbles = list(nibbles) + [0]  # pad odd nibble
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        lo = nibbles[i]
        hi = nibbles[i + 1]
        out.append((hi << 4) | lo)
    return bytes(out)


# ---------------------------------------------------------------------------
# ROM region computation
# ---------------------------------------------------------------------------

def find_end_rom(data: bytes, rom_start: int, scan_cap: int = 0x4000) -> int:
    """Scan for first 0x00 byte (silence floor / phrase boundary)."""
    limit = min(rom_start + scan_cap, len(data))
    for i in range(rom_start, limit):
        if data[i] == 0x00:
            return i
    return limit


def compute_sound_regions(original_rom: bytes) -> list[dict]:
    """
    Compute the ROM region for each voice SFX sound from the original ROM.

    For each sound, determines:
      - rom_start: first byte of sample data
      - orig_bytes: original sample byte count (up to 0x00 marker)
      - max_bytes: maximum injectable bytes (to next phrase or bank end)
    """
    # Parse descriptor table from original ROM
    descs = []
    for i in range(VOICE_SFX_FIRST, VOICE_SFX_FIRST + VOICE_SFX_COUNT):
        off = DESC_TABLE_ROM + i * DESC_ENTRY_SIZE
        ptr_lo   = original_rom[off + 2]
        ptr_hi   = original_rom[off + 3]
        bank     = original_rom[off + 6]
        ptr_logical = (ptr_hi << 8) | ptr_lo
        rom_start   = bank * BANK_SIZE + (ptr_logical - PAGE6_BASE)
        sound_id    = 0x33 + (i - VOICE_SFX_FIRST)
        end_rom     = find_end_rom(original_rom, rom_start)
        orig_bytes  = end_rom - rom_start
        descs.append({
            'sound_id':   sound_id,
            'bank':       bank,
            'rom_start':  rom_start,
            'orig_bytes': orig_bytes,
            'end_rom':    end_rom,
        })

    # Group by bank to compute max_bytes per sound
    from collections import defaultdict
    by_bank = defaultdict(list)
    for d in descs:
        by_bank[d['bank']].append(d)

    for bank, group in by_bank.items():
        group.sort(key=lambda d: d['rom_start'])
        bank_end = (bank + 1) * BANK_SIZE
        for gi, d in enumerate(group):
            if gi + 1 < len(group):
                # Max = up to next phrase start (leave room for 0x00 terminator)
                d['max_bytes'] = group[gi + 1]['rom_start'] - d['rom_start'] - 1
            else:
                # Last phrase in bank → up to bank end (minus 1 for 0x00)
                d['max_bytes'] = bank_end - d['rom_start'] - 1

    return descs


# ---------------------------------------------------------------------------
# Main injection
# ---------------------------------------------------------------------------

def inject(
    input_dir: str = INPUT_DIR,
    base_rom_path: str = BASE_ROM,
    out_rom_path: str = OUT_ROM,
) -> None:
    """
    Load base ROM, inject custom WAV files, write patched ROM.

    Only sound_XX.wav files found in input_dir are injected.
    Other sounds keep their base ROM data unchanged.
    """
    # --- Load original ROM (for region computation) ---
    orig_rom_path = os.path.join(os.path.dirname(base_rom_path), "Gunhed (Japan).pce")
    if not os.path.exists(orig_rom_path):
        # Try relative to script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        orig_rom_path = os.path.join(script_dir, "Gunhed (Japan).pce")

    print(f"Loading original ROM for region analysis: {orig_rom_path}")
    with open(orig_rom_path, 'rb') as f:
        original_rom = f.read()

    orig_crc = zlib.crc32(original_rom) & 0xFFFFFFFF
    if orig_crc != ORIGINAL_CRC32:
        print(f"  WARNING: CRC32 {orig_crc:08X} ≠ expected {ORIGINAL_CRC32:08X}")

    # --- Load base ROM (to patch into) ---
    print(f"Loading base ROM: {base_rom_path}")
    with open(base_rom_path, 'rb') as f:
        rom = bytearray(f.read())
    base_crc = zlib.crc32(rom) & 0xFFFFFFFF
    print(f"  Base ROM CRC32: {base_crc:08X}  ({len(rom):,} bytes)")

    # --- Compute sound regions from original ROM ---
    regions = compute_sound_regions(original_rom)

    print(f"\nSound regions (from original ROM):")
    print(f"  {'Sound':>6}  {'Bank':>4}  {'ROM start':>10}  {'Orig bytes':>10}  {'Max bytes':>9}  {'Orig ms':>7}")
    print(f"  {'─' * 60}")
    for r in regions:
        ms = r['orig_bytes'] * 2 * 1000 / DDA_SAMPLE_RATE  # 2 nibbles per byte
        print(f"  s${r['sound_id']:02X}   ${r['bank']:02X}   "
              f"${r['rom_start']:05X}     {r['orig_bytes']:>6}       {r['max_bytes']:>6}   {ms:>6.0f}")

    # --- Scan input folder for WAV files ---
    print(f"\nScanning input folder: {input_dir}")
    if not os.path.isdir(input_dir):
        print(f"  ERROR: folder not found: {input_dir}")
        print(f"  Create it and place sound_33.wav – sound_3A.wav inside.")
        sys.exit(1)

    wav_files = {}
    for fname in sorted(os.listdir(input_dir)):
        if not fname.lower().endswith('.wav'):
            continue
        # Parse sound_XX.wav pattern
        base = os.path.splitext(fname)[0].lower()
        if base.startswith('sound_') and len(base) == 8:
            try:
                sid = int(base[6:8], 16)
                if 0x33 <= sid <= 0x3A:
                    wav_files[sid] = os.path.join(input_dir, fname)
            except ValueError:
                pass

    if not wav_files:
        print(f"  No sound_XX.wav files found (expected: sound_33.wav – sound_3A.wav)")
        sys.exit(1)

    print(f"  Found {len(wav_files)} WAV file(s): "
          + ", ".join(f"s${sid:02X}" for sid in sorted(wav_files.keys())))

    # --- Inject each WAV ---
    print(f"\nInjecting:")
    print(f"  {'Sound':>6}  {'WAV rate':>8}  {'WAV samples':>11}  {'→ nibs @6991':>12}  "
          f"{'→ bytes':>7}  {'Orig bytes':>10}  {'Status':>12}  {'Peak':>4}")
    print(f"  {'─' * 95}")

    injected_count = 0
    for r in regions:
        sid = r['sound_id']
        if sid not in wav_files:
            print(f"  s${sid:02X}   {'—':>8}  {'—':>11}  {'—':>12}  {'—':>7}  "
                  f"{r['orig_bytes']:>10}  {'(original)':>12}")
            continue

        wav_path = wav_files[sid]

        # Read WAV
        try:
            samples_f, wav_rate = read_wav(wav_path)
        except Exception as e:
            print(f"  s${sid:02X}   ERROR reading {wav_path}: {e}")
            continue

        wav_sample_count = len(samples_f)

        # Resample to DDA_SAMPLE_RATE
        if wav_rate != DDA_SAMPLE_RATE:
            samples_f = resample_linear(samples_f, wav_rate, DDA_SAMPLE_RATE)

        # Quantize to 4-bit nibbles
        nibbles = quantize_to_nibbles(samples_f)
        nib_count = len(nibbles)
        peak_nib = max(nibbles) if nibbles else 0

        # Pack into bytes
        packed = pack_nibbles(nibbles)
        new_bytes = len(packed)

        # Check size constraint
        max_b = r['max_bytes']
        orig_b = r['orig_bytes']
        status = "OK"

        if new_bytes > max_b:
            # Hard limit — would overwrite next phrase
            packed = packed[:max_b]
            new_bytes = max_b
            status = f"TRUNCATED (max {max_b})"
        elif new_bytes > orig_b:
            status = f"longer +{new_bytes - orig_b}"
        elif new_bytes < orig_b:
            status = f"shorter -{orig_b - new_bytes}"
        else:
            status = "exact"

        # Patch ROM: write new sample data
        rom_start = r['rom_start']
        for i, b in enumerate(packed):
            rom[rom_start + i] = b

        # Pad remainder with 0x00 (silence) up to original end
        pad_end = rom_start + max(orig_b, new_bytes)
        for i in range(rom_start + new_bytes, pad_end):
            rom[i] = 0x00
        # Ensure 0x00 terminator at the end of the written region
        if rom_start + new_bytes < len(rom):
            rom[rom_start + new_bytes] = 0x00

        rate_str = f"{wav_rate}" if wav_rate != DDA_SAMPLE_RATE else f"{wav_rate} ✓"
        print(f"  s${sid:02X}   {rate_str:>8}  {wav_sample_count:>11}  {nib_count:>12}  "
              f"{new_bytes:>7}  {orig_b:>10}  {status:>12}  {peak_nib:>4}")
        injected_count += 1

    # --- Write output ROM ---
    os.makedirs(os.path.dirname(os.path.abspath(out_rom_path)), exist_ok=True)
    with open(out_rom_path, 'wb') as f:
        f.write(rom)

    out_crc = zlib.crc32(rom) & 0xFFFFFFFF
    total_diffs = sum(1 for a, b in zip(original_rom, rom) if a != b)

    print(f"\n{'═' * 60}")
    print(f"  Injected: {injected_count} sound(s)")
    print(f"  Output:   {out_rom_path}")
    print(f"  CRC32:    {out_crc:08X}")
    print(f"  Bytes changed vs original: {total_diffs:,}")
    print(f"{'═' * 60}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    input_dir = sys.argv[1] if len(sys.argv) > 1 else INPUT_DIR
    base_rom  = sys.argv[2] if len(sys.argv) > 2 else BASE_ROM
    out_rom   = sys.argv[3] if len(sys.argv) > 3 else OUT_ROM
    inject(input_dir, base_rom, out_rom)
