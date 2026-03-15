"""
extract_voice_sfx.py
====================
Standalone extractor for Gunhed (Japan) DDA voice SFX samples.

Usage:
    python extract_voice_sfx.py

Outputs 8 WAV files (sound_33.wav – sound_3A.wav) into OUT_DIR.

--- TECHNICAL BACKGROUND ---

Hardware: PC Engine (TurboGrafx-16)
ROM:      Gunhed (Japan).pce
          CRC32: A17D4D7E, SHA-1: 87DC4B09F0CF28F57BCC4D9A6E285D65D9CFF27D
          384 KB = 48 banks × 8 KB

Audio hardware — PSG DDA (Direct D/A) mode
-------------------------------------------
The PC Engine's Programmable Sound Generator (HuC6280 PSG) has a Direct D/A mode
on any of its 6 channels. Activated by writing 0xC0 to R4 (channel control register).
Once active, each byte written to R6 (waveform data register) is immediately output
as a raw 4-bit D/A value (0–15).

Playback driver maps an 8 KB ROM bank to CPU page 6 ($C000–$DFFF) via the MPR register,
then streams nibble-packed sample bytes one at a time to R6. Playback loop:

    ; From DDA playback routine (ROM $EA48–$EA68):
    $EA48: A1 40   LDA ($40,X)   ; load sample byte (ZP ptr: lo=$40+X, hi=$41+X)
    $EA4A: 30 5E   BMI $EAA8     ; $80 end-of-sample marker → stop
    $EA4C: 8D 06 08 STA $0806    ; not needed directly, falls through
    $EA50: 29 0F   AND #$0F      ; extract LOW nibble
    $EA52: 8D 06 08 STA $0806    ; write low nibble to R6 (ch on page 0x0800+ch*16)
    $EA5A: F6 40   INC $40,X     ; advance pointer
    ...
    ; Second write uses (byte >> 4) & 0x0F for high nibble

Sample encoding format:
  - One byte = two 4-bit samples
  - Decode order: LOW nibble first, HIGH nibble second
  - 4-bit value 0–15 → 8-bit unsigned PCM: value × 17
  - End-of-stream marker: byte 0x80 (sign bit set → BMI branch triggers)
  - Sample rate: ~6,991 Hz (ZP rate counter $53,X = 0 → fire every IRQ)

Voice SFX descriptor table
---------------------------
Location: ROM $278D0 (bank $13 logical $58D0, always-mapped page 5)
Format:   8 bytes per entry, 28 valid entries total

Byte layout per entry:
  [0] flags      — $88 = DDA voice SFX group; $80 = PCM; other = PSG
  [1] len_lo     — sample byte length, low byte
  [2] ptr_lo     — sample pointer (page 6 = $C000), low byte
  [3] ptr_hi     — sample pointer, high byte
  [4] len_hi     — sample byte length, high byte
  [5] loop       — loop point or 0
  [6] bank       — ROM bank number to map to CPU page 6
  [7] reserved   — always 0

ROM offset formula:
  rom_offset = bank * 0x2000 + (ptr_logical - 0xC000)

  Page 6 maps $C000–$DFFF → offset within bank = ptr - $C000.

Sound IDs and confirmed descriptor mapping (sounds $33–$3A = descriptors [16]–[23]):
  desc[16] = s$33  → confirmed by user listening to extracted sound_33.wav
  desc[23] = s$3A  → last in group

Bank layout — consecutive phrases separated by $00 silence-floor bytes
----------------------------------------------------------------------
Each bank packs speech phrases back-to-back. Each descriptor points to the START of
its own unique phrase. A $00 byte (both nibbles = 0, PCM = 0 = silence floor) marks
the end of each phrase. The DDA playback BMI loop fires on the $80 terminator that
follows, but the audible break begins at the $00 byte.

  bank $09  ROM $12000–$13FFF  (3 phrases, ~2303 bytes total)
    s$33  desc[16]  ROM $12000–$12BC0   861 ms
    s$35  desc[18]  ROM $12BC1–$134F1   673 ms
    s$38  desc[21]  ROM $134F2–$13F72   769 ms

  bank $12  ROM $24000–$25FFF  (1 phrase + driver tables)
    s$34  desc[17]  ROM $25462–$25F52   801 ms

  bank $17  ROM $2E000–$2FFFF  (4 phrases, ~8080 bytes total)
    s$36  desc[19]  ROM $2E000–$2E9D0   719 ms
    s$37  desc[20]  ROM $2E9D1–$2F3D1   732 ms
    s$39  desc[22]  ROM $2F3D2–$2F8F2   375 ms
    s$3A  desc[23]  ROM $2F8F3–$2FF93   485 ms

Volume notes (v5 + v6 patches)
-------------------------------
Correct extraction ($00 phrase-end detection) reveals voice samples peak at
nibble 13/15 — NOT 15/15 as earlier ($80-detection) analysis suggested.
The $80 approach overshot bank boundaries into adjacent ROM data (waveforms/code)
which happened to have high nibble values, giving a false 15/15 reading.

  v5  CRC32 11D4936D  3-byte PSG register patch  (DDA vol floor 15/31)
  v6  CRC32 CB4B2670  v5 + sample boost ×1.154   (peak 13→15, others 12→14 / 11→13)

v6 is the definitive final patch.

Patch locations (v5 base, shared by v6):
  ROM $261A9: $80 → $8F  (music ORA #$8F)
  ROM $26571: $C0 → $CF  (DDA ch-vol ORA #$CF)
  ROM $2687A: $C0 → $CF  (DDA amplitude ORA #$CF)
  + v6 only: 18,807 nibble-data bytes across 8 voice SFX regions

"""

import os
import struct
import wave

# ---------------------------------------------------------------------------
# Configuration — edit ROM_PATH and OUT_DIR as needed
# ---------------------------------------------------------------------------

ROM_PATH = "Gunhed (Japan).pce"   # Path to the ORIGINAL Gunhed ROM (not the v5 patch)
OUT_DIR  = "bin/voice_sfx"       # Output directory for WAV files

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BANK_SIZE         = 0x2000    # 8 KB per ROM bank
PAGE6_BASE        = 0xC000    # CPU page 6 base address (logical)
DDA_SAMPLE_RATE   = 6991      # Hz — matches ZP rate counter = 0 (fire every IRQ ~7 kHz)
SCAN_CAP          = 0x4000    # Maximum bytes to scan past entry for $80 end-marker

DESC_TABLE_ROM    = 0x278D0   # ROM address of voice SFX descriptor table
DESC_ENTRY_SIZE   = 8
VOICE_SFX_FIRST   = 16        # First voice SFX descriptor index (0-based)
VOICE_SFX_COUNT   = 8         # s$33 through s$3A
VOICE_SFX_FLAGS   = {0x88}        # flags bytes for voice SFX group (all 8 are $88)

# ---------------------------------------------------------------------------
# Voice SFX descriptor data (hardcoded from notebook analysis for robustness)
# These match the live descriptor parse — use as fallback or to cross-check.
# ---------------------------------------------------------------------------
#
# Format: (sound_id, bank, ptr_logical, approx_byte_length)
#
# The approx_byte_length is from the descriptor's len_hi:len_lo field.
# For inner stream entries (e.g. s$36/$38/$39/$37) this may be the REMAINING
# bytes from that entry to the stream end, or 0 (as desc[20] = s$36 has len=0).
# It is NOT used for extraction — end_rom (first $80 byte) governs truncation.
#
VOICE_SFX_HARDCODED = [
    # sound_id  bank   ptr_logical  nibble_count  bank_layout
    (0x33,      0x09,  0xC000,      6016),        # bank $09 phrase 1
    (0x34,      0x12,  0xD462,      5600),        # bank $12 phrase 1 (standalone)
    (0x35,      0x09,  0xCBC1,      4704),        # bank $09 phrase 2
    (0x36,      0x17,  0xC000,      5024),        # bank $17 phrase 1
    (0x37,      0x17,  0xC9D1,      5120),        # bank $17 phrase 2
    (0x38,      0x09,  0xD4F2,      5376),        # bank $09 phrase 3
    (0x39,      0x17,  0xD3D2,      2624),        # bank $17 phrase 3
    (0x3A,      0x17,  0xD8F3,      3392),        # bank $17 phrase 4
]

# ---------------------------------------------------------------------------
# Descriptor table parser
# ---------------------------------------------------------------------------

def parse_descriptor_table(rom: bytes) -> list[dict]:
    """
    Parse the voice SFX descriptor table at DESC_TABLE_ROM.

    Returns a list of dicts for the 8 voice SFX entries (desc[17]–[24]).
    Each dict:
        sound_id     : int  — $33..$3A (VOICE_SFX_FIRST + index)
        bank         : int  — ROM bank number
        ptr_logical  : int  — logical sample pointer in page 6 ($C000–$DFFF)
        length       : int  — byte length from descriptor field
        rom_sample   : int  — ROM byte offset of first sample byte
        desc_idx     : int  — 0-based descriptor index in table
    """
    results = []
    base = DESC_TABLE_ROM
    for i in range(VOICE_SFX_FIRST, VOICE_SFX_FIRST + VOICE_SFX_COUNT):
        off = base + i * DESC_ENTRY_SIZE
        flags    = rom[off + 0]
        len_lo   = rom[off + 1]
        ptr_lo   = rom[off + 2]
        ptr_hi   = rom[off + 3]
        len_hi   = rom[off + 4]
        loop     = rom[off + 5]
        bank     = rom[off + 6]
        _        = rom[off + 7]

        ptr_logical = (ptr_hi << 8) | ptr_lo
        length      = (len_hi << 8) | len_lo
        rom_sample  = bank * BANK_SIZE + (ptr_logical - PAGE6_BASE)
        sound_id    = 0x33 + (i - VOICE_SFX_FIRST)

        results.append({
            "sound_id":    sound_id,
            "bank":        bank,
            "ptr_logical": ptr_logical,
            "length":      length,
            "rom_sample":  rom_sample,
            "desc_idx":    i,
            "flags":       flags,
        })
    return results


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def find_end_rom(rom: bytes, rom_start: int, scan_cap: int = SCAN_CAP) -> int:
    """
    Scan forward from rom_start for the first 0x00 byte (phrase boundary).

    A 0x00 byte means both nibbles = 0 → PCM value 0 → audio drops to -100%
    (silence floor). This is the inter-phrase separator within each bank's
    consecutive speech layout. The DDA playback loop's BMI fires on the 0x80
    terminator byte that follows, but the audible break begins at the 0x00.

    Returns the ROM offset of the first 0x00 byte.
    Raises ValueError if no 0x00 is found within the scan window.
    """
    limit = min(rom_start + scan_cap, len(rom))
    for i in range(rom_start, limit):
        if rom[i] == 0x00:
            return i
    raise ValueError(
        f"No 0x00 phrase-end marker found within {scan_cap} bytes of ROM ${rom_start:05X}"
    )


def decode_range(rom: bytes, start_rom: int, end_rom: int) -> bytes:
    """
    Decode DDA nibble-packed PCM from ROM[start_rom:end_rom] to 8-bit unsigned PCM.

    Each ROM byte → two output samples:
      sample_a = (byte & 0x0F) * 17       # low nibble first
      sample_b = ((byte >> 4) & 0x0F) * 17  # high nibble second

    Multiplier 17 maps 0–15 → 0–255 (exact fit: 15 × 17 = 255).
    Output is raw 8-bit unsigned PCM, ready to write into a WAV file.
    """
    out = bytearray()
    for b in rom[start_rom:end_rom]:
        out.append((b & 0x0F) * 17)          # low nibble
        out.append(((b >> 4) & 0x0F) * 17)   # high nibble
    return bytes(out)


def write_wav_u8(pcm: bytes, path: str, sample_rate: int = DDA_SAMPLE_RATE) -> None:
    """Write raw 8-bit unsigned mono PCM as a WAV file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)       # mono
        wf.setsampwidth(1)       # 8-bit = 1 byte per sample
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_all(rom_path: str = ROM_PATH, out_dir: str = OUT_DIR) -> None:
    """
    Load the Gunhed ROM and extract all 8 voice SFX as WAV files.

    Process:
    1. Parse descriptor table → get rom_sample for each sound
    2. Scan from rom_sample for first 0x00 byte (silence floor) → end_rom
    3. Decode [rom_sample, end_rom) as nibble pairs → 8-bit unsigned PCM
    4. Write WAV at 6,991 Hz
    """
    print(f"Loading ROM: {rom_path}")
    with open(rom_path, "rb") as f:
        rom = f.read()

    expected_size = 48 * BANK_SIZE  # 384 KB
    if len(rom) != expected_size:
        print(
            f"  WARNING: ROM size {len(rom):,} bytes, expected {expected_size:,}. "
            "Proceeding anyway — may indicate wrong ROM or header."
        )

    print(f"Parsing descriptor table at ROM ${DESC_TABLE_ROM:05X} ...")
    descriptors = parse_descriptor_table(rom)

    print(f"\n{'Sound':>6}  {'Desc':>4}  {'Bank':>4}  {'ROM Start':>10}  "
          f"{'ROM End':>9}  {'Bytes':>6}  {'ms':>6}  Output")
    print("-" * 85)

    os.makedirs(out_dir, exist_ok=True)

    for d in descriptors:
        sound_id   = d["sound_id"]
        rom_start  = d["rom_sample"]

        # Cross-check against hardcoded table
        hc = VOICE_SFX_HARDCODED[sound_id - 0x33]
        if d["bank"] != hc[1] or d["ptr_logical"] != hc[2]:
            print(
                f"  NOTE s${sound_id:02X}: descriptor says bank=${d['bank']:02X} "
                f"ptr=${d['ptr_logical']:04X}, hardcoded says bank=${hc[1]:02X} "
                f"ptr=${hc[2]:04X}. Using parsed descriptor values."
            )

        # Find end-of-stream marker
        end_rom = find_end_rom(rom, rom_start)

        # Decode and write
        pcm    = decode_range(rom, rom_start, end_rom)
        ms     = len(pcm) * 1000 // DDA_SAMPLE_RATE
        out_fn = os.path.join(out_dir, f"sound_{sound_id:02X}.wav")
        write_wav_u8(pcm, out_fn)

        print(
            f"  s${sound_id:02X}   [{d['desc_idx']:2d}]  "
            f"${d['bank']:02X}   ${rom_start:05X}–${end_rom:05X}  "
            f"{end_rom - rom_start:6d} B  {ms:5d}  {out_fn}"
        )

    print(f"\nDone — {len(descriptors)} WAV files written to '{out_dir}/'")
    print()
    print("Bank layout reference:")
    print("  bank $09  s$33 / s$35 / s$38  (3 consecutive phrases)")
    print("  bank $12  s$34               (standalone)")
    print("  bank $17  s$36 / s$37 / s$39 / s$3A  (4 consecutive phrases)")
    print()
    print("Volume: samples peak at nibble 13/15 (13% headroom).")
    print("v6 patch (CRC32 CB4B2670) applies ×1.154 boost — peak 13→15.")
    print("v5 patch (CRC32 11D4936D) is PSG-register-only (no sample boost).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    rom  = sys.argv[1] if len(sys.argv) > 1 else ROM_PATH
    out  = sys.argv[2] if len(sys.argv) > 2 else OUT_DIR
    extract_all(rom, out)
