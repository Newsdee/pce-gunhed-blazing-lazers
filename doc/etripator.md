# Gunhed (Japan) — Etripator Disassembly Guide

> See also: [instructions.md](instructions.md) — full ROM analysis, sound driver RE, and volume patch records.

## Etripator Disassembly Guide

[Etripator](https://github.com/pce-devel/Etripator) is a PC Engine-specific HuC6280 disassembler. It takes a ROM file plus three JSON config files and outputs commented, labelled assembly source. It understands MPR bank mapping, so you specify which pages are loaded at which logical addresses when disassembling each section.

### Install

```bash
git clone https://github.com/pce-devel/Etripator
cd Etripator
cmake -B build && cmake --build build
# requires libjansson (apt install libjansson-dev / brew install jansson)
```

### Three-File System

| File | Purpose |
|------|---------|
| `gunhed.json` | Sections config - defines each code/data/binary region with logical address, page, MPR map, and size |
| `labels.json` | Symbol names - maps logical addresses to human-readable names |
| `comments.json` | Inline annotations - attaches comments to specific addresses |

### Workflow

**Step 1 - Bootstrap (generate skeleton configs)**
```bash
etripator -i Gunhed\ \(Japan\).pce gunhed.json
```
This emits a minimal `gunhed.json` covering only the interrupt vectors. Use it as the starting template.

**Step 2 - Full run**
```bash
etripator Gunhed\ \(Japan\).pce gunhed.json labels.json comments.json
```
Outputs one `.asm` file per section defined in `gunhed.json`.

---

### Starter `gunhed.json`

The MPR array `["ff","f8","12","13","00","00","00","00"]` maps logical pages 0-7:
- `ff` = I/O registers (`$0000-$1FFF`)
- `f8` = RAM (`$2000-$3FFF`)
- `12` = ROM bank `$12` (`$4000-$5FFF`)
- `13` = ROM bank `$13` (`$6000-$7FFF`) - sound driver
- `00` = ROM bank `$00` (`$8000-$FFFF`) - startup / vectors

**Key formula**: `file_offset = page x 8192 + (logical_address & 0x1FFF)`

```json
{
  "sections": [
    {
      "name": "reset",
      "type": "code",
      "logical": "E000",
      "page": "00",
      "mpr": ["ff","f8","00","00","00","00","00","00"],
      "size": 256
    },
    {
      "name": "irq2_brk_stub",
      "type": "code",
      "logical": "EA2D",
      "page": "00",
      "mpr": ["ff","f8","00","00","00","00","00","00"],
      "size": 4
    },
    {
      "name": "timer_irq",
      "type": "code",
      "logical": "EA2E",
      "page": "00",
      "mpr": ["ff","f8","00","00","00","00","00","00"],
      "size": 4
    },
    {
      "name": "dda_voice_streamer",
      "type": "code",
      "logical": "EA30",
      "page": "00",
      "mpr": ["ff","f8","00","00","00","00","00","00"],
      "size": 128
    },
    {
      "name": "irq_vectors",
      "type": "data",
      "logical": "FFF6",
      "page": "00",
      "size": 10
    },
    {
      "name": "sound_driver_tick",
      "type": "code",
      "logical": "6000",
      "page": "13",
      "mpr": ["ff","f8","12","13","00","00","00","00"],
      "size": 256
    },
    {
      "name": "waveform_loader",
      "type": "code",
      "logical": "6192",
      "page": "13",
      "mpr": ["ff","f8","12","13","00","00","00","00"],
      "size": 32
    },
    {
      "name": "channel_note_on",
      "type": "code",
      "logical": "6353",
      "page": "13",
      "mpr": ["ff","f8","12","13","00","00","00","00"],
      "size": 128
    },
    {
      "name": "channel_note_off",
      "type": "code",
      "logical": "6553",
      "page": "13",
      "mpr": ["ff","f8","12","13","00","00","00","00"],
      "size": 64
    },
    {
      "name": "frequency_table",
      "type": "data",
      "logical": "6B00",
      "page": "13",
      "size": 164
    },
    {
      "name": "waveform_pointer_table",
      "type": "data",
      "logical": "6BA4",
      "page": "13",
      "size": 32
    },
    {
      "name": "waveform_table_bank13",
      "type": "binary",
      "logical": "6C57",
      "page": "13",
      "size": 3136
    },
    {
      "name": "waveform_bank_0F",
      "type": "binary",
      "logical": "0000",
      "page": "0f",
      "size": 8192
    },
    {
      "name": "waveform_bank_10",
      "type": "binary",
      "logical": "0000",
      "page": "10",
      "size": 8192
    },
    {
      "name": "waveform_bank_11",
      "type": "binary",
      "logical": "0000",
      "page": "11",
      "size": 8192
    }
  ]
}
```

---

### Starter `labels.json`

```json
{
  "labels": [
    { "name": "PSG_CHANNEL_SELECT", "logical": "0800", "page": "ff" },
    { "name": "PSG_MAIN_AMP",       "logical": "0801", "page": "ff" },
    { "name": "PSG_FREQ_LO",        "logical": "0802", "page": "ff" },
    { "name": "PSG_FREQ_HI",        "logical": "0803", "page": "ff" },
    { "name": "PSG_CHAN_CTRL",       "logical": "0804", "page": "ff" },
    { "name": "PSG_STEREO_PAN",     "logical": "0805", "page": "ff" },
    { "name": "PSG_WAVE_DATA",      "logical": "0806", "page": "ff" },
    { "name": "PSG_NOISE_CTRL",     "logical": "0807", "page": "ff" },
    { "name": "PSG_LFO_FREQ",       "logical": "0808", "page": "ff" },
    { "name": "PSG_LFO_CTRL",       "logical": "0809", "page": "ff" },
    { "name": "VDC_STATUS",         "logical": "0000", "page": "ff" },
    { "name": "VDC_MAWR",           "logical": "0002", "page": "ff" },
    { "name": "VDC_DATA_LO",        "logical": "0003", "page": "ff" },
    { "name": "VDC_DATA_HI",        "logical": "0004", "page": "ff" },
    { "name": "TIMER_COUNTER",      "logical": "0C00", "page": "ff" },
    { "name": "TIMER_CTRL",         "logical": "0C01", "page": "ff" },
    { "name": "IRQ_DISABLE",        "logical": "1402", "page": "ff" },
    { "name": "IRQ_STATUS",         "logical": "1403", "page": "ff" },
    { "name": "reset",              "logical": "E000", "page": "00" },
    { "name": "dda_voice_streamer", "logical": "EA30", "page": "00" },
    { "name": "irq2_vector",        "logical": "FFF6", "page": "00" },
    { "name": "timer_vector",       "logical": "FFF8", "page": "00" },
    { "name": "nmi_vector",         "logical": "FFFA", "page": "00" },
    { "name": "reset_vector",       "logical": "FFFC", "page": "00" },
    { "name": "brk_vector",         "logical": "FFFE", "page": "00" },
    { "name": "sound_driver_tick",  "logical": "6000", "page": "13" },
    { "name": "waveform_loader",    "logical": "6192", "page": "13" },
    { "name": "channel_note_on",    "logical": "6353", "page": "13" },
    { "name": "channel_note_off",   "logical": "6553", "page": "13" },
    { "name": "frequency_table",    "logical": "6B00", "page": "13" },
    { "name": "waveform_ptr_table", "logical": "6BA4", "page": "13" },
    { "name": "zp_driver_guard",    "logical": "00D2", "page": "f8" },
    { "name": "zp_channel_ptr_lo",  "logical": "00D4", "page": "f8" },
    { "name": "zp_channel_ptr_hi",  "logical": "00D5", "page": "f8" },
    { "name": "zp_active_channels", "logical": "00D6", "page": "f8" },
    { "name": "zp_dda_ptr_lo",      "logical": "00E0", "page": "f8" },
    { "name": "zp_dda_ptr_hi",      "logical": "00E1", "page": "f8" },
    { "name": "zp_dda_len",         "logical": "00E2", "page": "f8" }
  ]
}
```

---

### Starter `comments.json`

```json
{
  "comments": [
    {
      "logical": "E000",
      "page": "00",
      "text": "Reset entry: HuC6280 startup. Sets speed, initialises I/O then jumps to main init."
    },
    {
      "logical": "EA30",
      "page": "00",
      "text": "DDA voice streamer IRQ handler. Feeds one sample byte per interrupt to PSG_CHAN_CTRL ($0804). ZP pointers at $E0/$E1, length at $E2."
    },
    {
      "logical": "6000",
      "page": "13",
      "text": "Sound driver tick - called once per frame (VBlank). Checks ZP $D2 guard byte; 10-channel loop."
    },
    {
      "logical": "6192",
      "page": "13",
      "text": "Waveform loader. CLY clears Y (HuC6280 opcode $C2). Writes R4=$40 (waveform-write mode, resets 32-sample counter), then stores 32 samples via PSG_WAVE_DATA ($0806)."
    },
    {
      "logical": "6BA4",
      "page": "13",
      "text": "Waveform pointer table - 16 two-byte entries pointing into waveform data in this bank and banks $0F/$10/$11."
    }
  ]
}
```

---

### Etripator Analysis Plan

Follow these steps to progressively disassemble the ROM:

#### Step 1 - Disassemble the sound driver (bank `$13`) and startup bank (`$00`)

Add sections to `gunhed.json` as entry points are identified. Start with the known entry points above, run Etripator, then trace JSRs in the output to find the next functions to add.

#### Step 2 - Disassemble game banks `$12` and `$13` together

The MPR for the sound driver maps both: `"12"` at `$4000-$5FFF`, `"13"` at `$6000-$7FFF`. Add code sections for bank `$12` entry points as the JSR graph expands.

#### Step 3 - Decode data tables

Mark frequency, pointer, and waveform data sections as `"type": "data"` or `"type": "binary"` so Etripator emits `.db` directives rather than treating bytes as instructions.

#### Step 4 - Graphics: scan for ST0/ST1/ST2 VDC sequences (CHR tile uploads)

VDC tile uploads follow this pattern: `ST0 #$00` (select MAWR), `ST1 lo`, `ST2 hi` (set write address), then bulk `ST1`/`ST2` pairs. Use the notebook to locate them:

```python
# Find ST0 #$00 / ST1 lo / ST2 hi sequences in ROM
hits = []
for i in range(len(data) - 5):
    if data[i] == 0x03 and data[i+1] == 0x00:      # ST0 #$00
        if data[i+2] == 0x13 and data[i+4] == 0x23: # ST1 lo; ST2 hi
            addr_word = data[i+3] | (data[i+5] << 8)
            bank = i // 0x2000
            print(f"ROM ${i:05X} (bank ${bank:02X}): MAWR=${addr_word:04X}")
            hits.append((i, bank, addr_word))
print(f"\n{len(hits)} VDC address-set sequences found")
```

Once MAWR addresses are known, extract the CHR data blocks and decode them as 4bpp PC Engine tiles (8x8, 4 bitplanes, 2 bytes per row per plane = 32 bytes/tile):

```python
def decode_pce_tile(raw_32):
    """Decode one 8x8 4bpp PC Engine CHR tile to a list of 64 palette indices."""
    pixels = []
    for row in range(8):
        p0 = raw_32[row]
        p1 = raw_32[row + 8]
        p2 = raw_32[row + 16]
        p3 = raw_32[row + 24]
        for bit in range(7, -1, -1):
            colour = ((p0 >> bit) & 1)       \
                   | (((p1 >> bit) & 1) << 1) \
                   | (((p2 >> bit) & 1) << 2) \
                   | (((p3 >> bit) & 1) << 3)
            pixels.append(colour)
    return pixels
```

#### Step 5 - Locate and extract palette data

Search for writes to VDC colour RAM: `ST0 #$13` (select colour register) followed by `ST1`/`ST2` colour word pairs. Each 9-bit colour entry encodes 3-bit R/G/B.

#### Step 6 - Build bank cross-reference from TAM graph

The TAM scan (Step 5 of notebook) shows which code banks swap in which data/music banks. Decode all `LDA #imm / TAM #page` pairs to build a full call-graph across banks:

```python
# Decode all TAM instructions in a bank to map bank-swap dependencies
import re

def find_tam_deps(data, bank):
    base = bank * 0x2000
    chunk = data[base:base + 0x2000]
    deps = []
    for i in range(len(chunk) - 3):
        # LDA #imm (A9 xx) followed by TAM #page (53 pp)
        if chunk[i] == 0xA9 and chunk[i+2] == 0x53:
            mapped_bank = chunk[i+1]
            page_mask   = chunk[i+3]
            deps.append((base + i, mapped_bank, page_mask))
    return deps

for b in range(0x30):
    deps = find_tam_deps(data, b)
    if deps:
        for off, mb, pm in deps:
            print(f"Bank ${b:02X} @ ROM ${off:05X}: TAM page ${pm:02X} <- bank ${mb:02X}")
```

