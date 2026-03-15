# Gunhed (Japan) - PC Engine ROM Reverse Engineering

## ROM Identity

| Field | Value |
|-------|-------|
| File | `Gunhed (Japan).pce` |
| Size | 393,216 bytes (384 KB) |
| Banks | 48 x 8 KB |
| CRC32 | `A17D4D7E` |
| Developer | Compile |
| Publisher | Hudson Soft (1989) |
| Also released as | Blazing Lazers (TurboGrafx-16, NTSC-U) |
| Music | Takayuki Hirono |
| Format | HuCard (no CD-ROM² hardware) |

> **Note**: CRC `A17D4D7E` does not match the commonly documented `2B11E0B0` - this is likely a different regional pressing or revision. Verify against No-Intro database before assuming a canonical dump.

---

## Bank Map

| Bank(s) | ROM Range | Contents (known/inferred) |
|---------|-----------|--------------------------|
| `$00` | `$00000-$01FFF` | **Always-mapped** (page 7, `$E000-$FFFF`). Interrupt vectors, reset/init code, DDA voice streamer, waveform loader caller |
| `$01` | `$02000-$03FFF` | **Sound test renderer / sprite manager** — confirmed executed: `$A270` sprite manager, `$BC85` screen clear+setup, `$BD5C` scrolling text renderer, `$BEA4` display update loop |
| `$02-$07` | `$04000-$0FFFF` | Game code / level data (inferred) |
| `$08` | `$10000-$11FFF` | **Sound test UI** — confirmed executed: `$4005` main loop, `$4162` play/OK branch, `$4217` screen init, `$4302` menu navigation, `$4414` script interpreter |
| `$09` | `$12000-$13FFF` | **Voice SFX PCM data** — sounds `$33` (ROM `$12000`), `$35` (ROM `$12BC1`), `$38` (ROM `$134F2`); three consecutive phrases separated by `$00` silence-floor bytes |
| `$0A-$0E` | `$14000-$1DFFF` | Game code / level data (inferred) |
| `$0F` | `$1E000-$1FFFF` | **Waveform data set A** - 235 waveforms (4 groups, packed from bank start) |
| `$10` | `$20000-$21FFF` | **Waveform data set B** - 189 waveforms (3 groups) |
| `$11` | `$22000-$23FFF` | **Waveform data set C** - 104 waveforms (1 group, bank start) |
| `$12` | `$24000-$25FFF` | Sound driver support tables (channel state arrays, note/freq tables); **also voice SFX PCM data** — sound `$34` (ROM `$25462`) |
| `$13` | `$26000-$27FFF` | **Sound driver** - 22 PSG register accesses, instrument table, frequency table, 98+5 waveforms; **voice SFX descriptor table** at ROM `$278D0` |
| `$14-$16` | `$28000-$2DFFF` | Game code / graphics / level data (inferred) |
| `$17` | `$2E000-$2FFFF` | **Voice SFX PCM data** — sounds `$36` (ROM `$2E000`), `$37` (ROM `$2E9D1`), `$39` (ROM `$2F3D2`), `$3A` (ROM `$2F8F3`); four consecutive phrases separated by `$00` silence-floor bytes |
| `$18-$2B` | `$30000-$57FFF` | Game code / graphics / level data (inferred) |

> Banks `$0F`-`$11` begin waveform data at their very first byte — they are dedicated waveform banks mapped in at runtime.
> Voice SFX PCM data (sounds `$33–$3A`) lives in banks `$09`, `$12`, and `$17`. An early hypothesis placed it in bank `$10` (based on a stale mid-play ZP read) — this was incorrect and has been superseded by descriptor table analysis.

---

## Interrupt Vectors (ROM `$01FF6-$01FFF`)

| ROM Offset | Vector | Logical | Handler |
|-----------|--------|---------|---------|
| `$01FF6` | IRQ2/BRK | `$EA2D` | Shared with NMI - likely `RTI` stub |
| `$01FF8` | IRQ1 (VDC) | `$EB03` | VDC interrupt handler — see §IRQ1 below |
| `$01FFA` | Timer | `$EA2E` | Sound driver tick entry point |
| `$01FFC` | NMI | `$EA2D` | Shared with IRQ2 |
| `$01FFE` | RESET | `$E000` | Cold start entry point |

### IRQ1 Handler (`$EB03`) — Normal ISR, NOT a Hijack

The IRQ1 handler is a **standard interrupt service routine** that returns via RTI. It does **not** hijack the main thread's program counter. It reads the VDC status register to determine which interrupt fired and dispatches accordingly:

```
$EB03: PHA/PHX/PHY     ; save registers (3 bytes)
$EB06: LDA $0000       ; read VDC status register (clears IRQ)
$EB09: BIT #$20        ; test bit 5 = VBLANK?
$EB0B: BNE → $EB59     ; yes → VBLANK handler
$EB0D: BIT #$02        ; bit 1 = overflow?
$EB0F: BNE → overflow  ; yes → handle overflow
$EB11: BIT #$04        ; bit 2 = scanline?
$EB13: BNE → scanline  ; yes → handle scanline
$EB15: JMP → exit      ; none matched → restore regs, RTI
```

**VBLANK handler** (`$EB59`):
```
$EB5A: INC $10         ; ★ increment VBLANK counter (ZP $10)
                       ;   $F29B polls this for frame sync
$EB5C–$EB72:           ; SATB DMA, scroll register updates
$EB73: LDA $29 / PHA   ; save current mode
$EB8E: LDA $B3         ; load brightness (ZP $B3 = $0F)
$EB90: JSR $EEFF        ; set_mode(A) — maps banks for this mode
$EB93: JSR $C000        ; call page 6 per-frame handler
$EB96: LDA #$00
$EB98: JSR $EEF9        ; set_mode_sei($00) = sound driver banks
$EB9B: JSR $4000        ; call page 2 per-frame handler (sound driver tick)
$EB9E: PLA
$EB9F: JSR $EEF9        ; restore original mode banks
$EBA2–$EBAD:            ; restore VWR, registers, RTI
```

The handler calls `$C000` (page 6) and `$4000` (page 2) every VBLANK. These are **per-frame update routines** for whatever mode is currently active (ZP `$29`). For mode `$32` (sound test), page 2 = bank `$08`, so `$4000` in bank `$08` is the sound test's per-frame handler.

**Key insight**: The main thread continues normally after the handler returns via RTI. The game's state machine advances through the per-frame `JSR $4000`/`JSR $C000` calls inside the ISR, while the main thread typically sits in a VBLANK wait loop at `$F29B`.

### VBLANK Sync (`$F299`/`$F29B`)

```
$F299: STZ $10         ; clear VBLANK counter
$F29B: LDA $10         ; read counter
$F29D: CMP #$01        ; ≥ 1?
$F29F: BCC $F29B       ; no → spin (wait for IRQ1 to INC $10)
$F2A1: STZ $10         ; clear counter
$F2A3: RTS
```

This is the standard frame-sync primitive. **Requires VBLANK IRQ to be enabled** in the VDC CR (bit 3) AND IRQs unmasked (CLI). If either is missing, `$10` never increments and the loop spins forever.

---

## Reset / Startup Sequence (bank `$00`, `$E000`)

The boot sequence is **linear** — it falls straight through from hardware init to sound test entry at `$E092`. The IRQ1 handler is a normal ISR that returns via RTI; it does NOT hijack the main thread's program counter.

```
$E000: D4         CSH              ; switch to high-speed mode (7.16 MHz)
$E001: 78         SEI              ; disable interrupts
$E002: D8         CLD              ; clear decimal mode
$E003: A2 FF      LDX #$FF
$E005: 9A         TXS              ; initialise stack pointer → $21FF
$E006: A9 FF      LDA #$FF
$E008: 53 01      TAM #$01         ; MPR0=$FF → page 0 ($0000-$1FFF) = I/O
$E00A: A9 F8      LDA #$F8
$E00C: 53 02      TAM #$02         ; MPR1=$F8 → page 1 ($2000-$3FFF) = work RAM
$E00E: A9 00      LDA #$00
$E010: 53 80      TAM #$80         ; MPR7=$00 → page 7 ($E000-$FFFF) = ROM bank $00
$E012: 20 B0 F8   JSR $F8B0        ; HuC6260 VCE init (dot clock, palette)
$E015:            ; warm/cold boot check: 'JES!' at $E026 vs $2353
$E024:            ; BEQ → warm boot (skip RAM clear)
$E02A:            ; COLD BOOT: TII clears RAM $2000-$3FFF, stamps signature
$E042: 20 C4 F8   JSR $F8C4        ; HuC6270 VDC init (12 registers from table)
$E045: 9C 01 0C   STZ $0C01        ; stop HuC6280 timer
$E048: 9C 03 14   STZ $1403        ; ack timer IRQ
$E04B: 9C 02 14   STZ $1402        ; IRQ disable = 0 (all IRQs enabled at CPU level)
$E052:            ; init flags: ZP $24=1, ZP $B3=$0F (full brightness)
$E05D:            ; MODE $00 → map sound driver banks, JSR $49A3 (sound init)
$E065:            ; MODE $05 → map title/gameplay banks
$E06A:            ; TII: clear work RAM $2280-$22AF
$E074: 20 73 F1   JSR $F173        ; init tables (SATB, palette, BAT shadow)
$E077: 20 22 F9   JSR $F922        ; VDC CR |= $0A → enable VBLANK+OVF, then CLI
$E07A:            ; clear $236A-$236D (score/state variables)
$E086: 78         SEI              ; ── SOUND TEST ENTRY ── disable interrupts
$E087: A2 FF      LDX #$FF
$E089: 9A         TXS              ; reset stack pointer
$E08A: 20 26 F9   JSR $F926        ; VDC CR &= $F0 → disable ALL VDC IRQ sources
$E08D:            ; MODE $32 → map sound test banks ($08,$09,$05,$01,$02)
$E092: 20 05 40   JSR $4005        ; enter sound test (bank $08, page 2)
$E095: 9A         TXS              ; cleanup after sound test returns
```

**Critical IRQ state transitions during boot:**
1. `$E001: SEI` — all IRQs masked
2. `$E04B: STZ $1402` — IRQ disable register = 0 (IRQ1, IRQ2, Timer all allowed when CPU unmasks)
3. `$E077: JSR $F922` — VDC CR |= $0A (VBLANK+overflow IRQ sources enabled), then **CLI** → IRQ1 handler `$EB03` starts firing on VBLANK
4. `$E086: SEI` — IRQs masked again
5. `$E08A: JSR $F926` — VDC CR &= $F0 → **all VDC IRQ sources disabled** (VBLANK, scanline, overflow, collision all off)
6. Inside bank $08 at `$4023: CLI` — IRQs unmasked, but VDC sources still disabled → no VBLANK fires
7. `$4044: JSR $F922` (intro) — re-enables VBLANK+OVF sources → IRQ1 fires again

Between steps 3 and 4, a few VBLANK frames fire with mode $05 banks mapped. The IRQ1 handler runs mode-dependent per-frame updates (§IRQ1 below), but returns via RTI — the main thread at `$E07A` continues normally.

---

## Sound Driver - Bank `$13`

### Entry Point

| Address | ROM Offset | Description |
|---------|-----------|-------------|
| `$2000` (page 1) | `$26000` | **Main driver tick** - called from Timer IRQ (`$EA2E` -> JSR into bank `$13`) |
| `$2192` | `$26192` | **Waveform loader** - writes 32 samples to PSG waveform RAM |
| `$2353` | `$26353` | **Channel init / note-on** (inferred from `STA $0800` at `$2613F`) |
| `$2553` | `$26553` | **Note-off / silence** (`STY $0800`, `STZ $0806`, `STZ $0807` sequence) |
| `$2673` | `$26873` | **Channel amplitude** (`STY $0800`, `STA $0804`) |

### Driver Tick (ROM `$26000`, first 256 bytes)

```
$26000: A5 D2       LDA $D2         ; load driver status byte (ZP)
$26002: 89 04       BIT #$04        ; test bit 2
$26004: F0 01       BEQ +1          ; skip if clear
$26006: 60          RTS             ; driver idle - return immediately
$26007: 09 04       ORA #$04        ; set bit 2 (re-entrancy guard)
$26009: 85 D2       STA $D2
$2600B: F0 19       BEQ ...
$2600D: 29 FE       AND #$FE
$2600F: 85 D2       STA $D2
$26011: 20 D9 49    JSR $49D9       ; update music sequence (page 2, bank $12)
$26014: 62 20       ...
$26015: FF 49       JSR $49FF       ; (another music update step)
$26018: 82          ...             ; (HuC6280 extension op)
$26019: BD 6B 24    LDA $246B,X     ; load channel flags (table in bank $12)
$2601C: 09 40       ORA #$40
$2601E: 9D 6B 24    STA $246B,X
$26021: E8          INX
$26022: E0 0A       CPX #$0A        ; 10 channels (0-9)
$26024: D0 F3       BNE $26019      ; loop
$26026: 20 4F 48    JSR $484F       ; PSG output update
```

**Key observations:**
- `ZP $D2` = driver status/guard flag
- 10 active channels (indices 0-9)
- Channel state table at logical `$246B` (page 2 / bank `$12` area)
- Music sequence processor at `$49D9` and `$49FF` (page 2)
- PSG output update at `$484F`

### Waveform Loader (ROM `$26192`)

```
$26192: A9 40       LDA #$40
$26194: 8D 04 08    STA $0804       ; R4=$40 -> chON=0, DDA=1 (waveform-write mode)
                                    ; Resets PSG's internal 32-entry address counter
$26197: 9C 04 08    STZ $0804       ; R4=0 (clear)
$2619A: C2          CLY             ; Y <- 0  (HuC6280 CLY opcode)
$2619B: B1 CE       LDA ($CE),Y     ; load sample from ZP pointer $CE:$CF
$2619D: 8D 06 08    STA $0806       ; write to R6 (waveform data register)
$261A0: C8          INY             ; Y++
$261A1: C0 20       CPY #$20        ; 32 samples?
$261A3: D0 F6       BNE $2619B      ; loop until all 32 written
$261A5: BD CF 23    LDA $23CF,X     ; load next byte from instrument table
$261A8: 09 80       ORA #$80
$261AA: 8D 04 08    STA $0804       ; R4 |= $80 -> chON=1 (activate channel)
```

**Waveform pointer**: ZP `$CE:$CF` (set from instrument table at logical `$23CF`,X before this routine)

### Instrument / Note Table (bank `$12`, ROM `$24000-$25FFF`)

Referenced by driver at `$23CF`,X, `$23F3`,X, `$23D5`,X etc.:
- **Frequency table**: ROM `$26B00-$26BA0` - 64 x 2-byte descending period values (`$01FF` down to `$0004`), equal-tempered scale
- **Waveform pointer table**: ROM `$26BA4-$26BB8` - 16-bit logical pointers (`$4BBC`, `$4BD4`...) pointing into page 2 (waveform banks mapped there)
- **Note sequence entries**: ROM `$26BB8+` - 3-byte records `[waveform_idx, note_lo, note_hi]`
- **Channel state array**: logical `$246B,X` - per-channel flags, 10 entries

### PSG Register Write Summary (by bank)

| Bank | Hits | Role |
|------|------|------|
| `$00` | 5 | DDA voice streaming (`$EA4C`, `$EA6B`, `$EA91`, `$EAAC`) + channel select |
| `$05` | 4 | Init / test code |
| `$13` | 22 | **Sound driver** - all PSG registers covered |
| `$15` | 5 | Music sequence data (only `CH_SELECT` writes - Compile sequence format) |
| `$16` | 3 | Music sequence data |
| `$2A` | 1 | Isolated `STX $0800` - possibly SFX trigger |

---

## DDA Voice Streaming - Bank `$00` (`$EA30-$EAAC`)

Gunhed is a **HuCard** - no CD-ROM² ADPCM hardware exists. Voice/sample playback uses PSG **DDA mode**:
- R4 = `$C0` (chON=1, DDA=1): streaming active; every write to R6 goes directly to D/A
- R4 = `$80` (chON=1, DDA=0): returns channel to waveform playback mode

### DDA Streamer Subroutine (`$EA30`)

```
$EA30: 9C 03 14    STZ $1403       ; clear sample playback flag
$EA33: EA          NOP
$EA34: 43 40       TMA #$40        ; read current page 6 MPR into A  <- save
$EA36: 48          PHA             ; push saved bank
$EA37: A2 04       LDX #$04        ; X = channel index
$EA39: B5 3A       LDA $3A,X       ; load channel control byte
$EA3B: F0 63       BEQ $EAA0       ; skip if inactive
$EA3D: B5 4C       LDA $4C,X       ; load sample bank number from ZP table
$EA3F: 53 40       TAM #$40        ; map sample bank to page 6 ($C000-$DFFF)
$EA41: 8E 00 08    STX $0800       ; select PSG channel (R0)
$EA44: B5 3B       LDA $3B,X       ; load packed nibble flag
$EA46: 30 1A       BMI ...         ; branch: upper-nibble mode
;; Lower nibble path:
$EA48: A1 40       LDA ($40,X)     ; load sample byte (indirect, ZP $40+X = ptr lo)
$EA4A: 30 5E       BMI $EAA8       ; $80 = end-of-sample marker
$EA4C: 8D 06 08    STA $0806       ; write low nibble to R6 (DDA stream)
$EA4F: B5 53       LDA $53,X       ; load playback rate counter
$EA51: F0 07       BEQ ...         ; if zero, advance pointer
$EA53: 18          CLC
$EA54: 75 58       ADC $58,X       ; add fractional advance
$EA56: 95 58       STA $58,X
$EA58: 90 46       BCC $EAA0       ; no overflow - hold same sample
$EA5A: F6 40       INC $40,X       ; advance sample pointer lo byte
$EA5C: D0 42       BNE $EAA0
$EA5E: F6 41       INC $41,X       ; advance sample pointer hi byte
```

**Nibble packing**: samples are 4-bit, packed two per byte:
- Lower nibble: `AND #$0F` -> write to R6
- Upper nibble: `AND #$F0 / LSR / LSR / LSR` -> write to R6

**ZP layout for voice channels**:
| ZP Address | Contents |
|-----------|----------|
| `$3A,X` | Channel active flag |
| `$3B,X` | Nibble mode flag (bit 7 = upper nibble) |
| `$40,X-$41,X` | Sample read pointer (lo/hi in page 6) |
| `$4C,X` | Bank number mapped to page 6 for this channel |
| `$53,X` | Playback rate counter |
| `$58,X` | Fractional advance accumulator |

End-of-sample marker: `$80` in sample data stream.

---

### Sound Test Menu — Voice SFX Call Chain (banks `$08` + `$13`)

The sound test menu runs in bank `$08` (mapped to page 2, `$4000-$5FFF`) with the renderer in bank `$01`. MPR layout during sound test:

| Page | Logical | Bank |
|------|---------|------|
| 2 | `$4000-$5FFF` | `$08` — sound test UI |
| 3 | `$6000-$7FFF` | `$09` — support code |
| 4 | `$8000-$9FFF` | `$05` |
| 5 | `$A000-$BFFF` | `$01` — renderer |
| 6 | `$C000-$DFFF` | `$02` |
| 7 | `$E000-$FFFF` | `$00` — always |

**Per-frame call chain** (voice SFX trigger path):

```
$41E6  (bank $08) per-frame loop
  → JSR $F29B                ; wait-for-vblank / VDC sync (bank $00)
  → VDC IRQ fires → $EB03    ; VDC interrupt handler (bank $00)
      → JSR $4000            ; re-enter bank $08 init
          → JSR $4262        ; DDA voice command dispatcher (bank $13)
              → $44FE        ; note-on handler
                  → $4570    ; ORA #$CF / STA $0804  ← v5 patch site
```

Logical `$4262` (bank `$13` mapped to page 1 / `$2000-$3FFF`):
- Reads command byte from (`$CC`),Y
- Dispatches via table at `$429F,X`

Logical `$44FE` — DDA channel note-on:
1. Reads 8-byte descriptor from `$58D0,X` (descriptor table — see below)
2. Copies sample pointer, bank, and length to ZP
3. Writes `$40` to R4 (`STA $0804`): waveform-clear pulse
4. Sets R5=`$FF` (pan = L15/R15 = maximum stereo)
5. Executes `ORA #$CF / STA $0804` at ROM `$26570–$26572` → R4 = `$CF` (chON=1, DDA=1, vol=15)
6. Starts Timer for sample streaming

**The `$2879` path** (ROM `$2687A`, second `ORA #$C0`) is a **separate amplitude-update routine** used only for music channels. It was tested exhaustively — breakpoint never fired during sounds `$33–$3A`. It does not participate in voice SFX playback.

---

### Voice SFX Descriptor Table (Bank `$13`, ROM `$278D0`)

Located at logical `$58D0` when bank `$13` is mapped to page 1. Each entry is **8 bytes**. Sounds `$33–$3A` map to 8 consecutive entries.

| Byte offset | Field | Notes |
|-------------|-------|-------|
| `+0` | flags / priority | bit 7 = loop flag |
| `+1` | length lo | sample length, low byte |
| `+2` | sample_ptr lo | pointer within page 6 (`$C000-$DFFF`) |
| `+3` | sample_ptr hi | |
| `+4` | length hi / loop ptr lo? | |
| `+5` | loop point hi? | |
| `+6` | bank number | bank mapped to page 6 during playback (e.g. `$10` for sounds near `$33`) |
| `+7` | PSG channel index | `2` for all voice SFX confirmed |

**Confirmed sound → descriptor mapping** (user-verified by listening to extracted WAVs):

| Sound | Desc idx | flags | Bank | ptr (page 6) | ROM offset | Duration |
|-------|----------|-------|------|-------------|------------|----------|
| `$33` | [16] | `$88` | `$09` | `$C000` | `$12000` | 861 ms |
| `$34` | [17] | `$88` | `$12` | `$D462` | `$25462` | 801 ms |
| `$35` | [18] | `$88` | `$09` | `$CBC1` | `$12BC1` | 673 ms |
| `$36` | [19] | `$88` | `$17` | `$C000` | `$2E000` | 719 ms |
| `$37` | [20] | `$88` | `$17` | `$C9D1` | `$2E9D1` | 732 ms |
| `$38` | [21] | `$88` | `$09` | `$D4F2` | `$134F2` | 769 ms |
| `$39` | [22] | `$88` | `$17` | `$D3D2` | `$2F3D2` | 375 ms |
| `$3A` | [23] | `$88` | `$17` | `$D8F3` | `$2F8F3` | 485 ms |

**ROM offset formula**: `bank * 0x2000 + (ptr_logical - 0xC000)` — page 6 maps `$C000–$DFFF`, so the offset within the bank is `ptr - $C000`.

**All 8 descriptors are `flags=$88`** — the previous `$83` observation was from desc[24], which is outside the voice SFX group. desc[15] is s$32 candidate (same flag group). Desc[16] = sound `$33` confirmed by user listening to `sound_33.wav`.

**ZP channel 2 layout** (X=2 throughout):

| ZP Address | Role |
|-----------|------|
| `$3C` (`$3A+2`) | Channel 2 active flag |
| `$3D` (`$3B+2`) | Channel 2 nibble mode |
| `$42:$43` (`$40+2:$41+2`) | Channel 2 sample read pointer |
| `$4E` (`$4C+2`) | Channel 2 sample bank |

---

## Waveform Data

### Overview

| Bank | ROM Range | Waveforms | Groups | Notes |
|------|-----------|-----------|--------|-------|
| `$0F` | `$1E000-$1FD99` | 235 | 4 | Starts at bank boundary - dedicated waveform bank |
| `$10` | `$20000-$2196B` | 189 | 3 | Starts at bank boundary - dedicated waveform bank |
| `$11` | `$22000-$22CFF` | 104 | 1 | Starts at bank boundary - dedicated waveform bank |
| `$13` | `$26B5F-$27B06` | 103 | 5 | Embedded in driver bank: instrument waveforms + special shapes |

**Total**: 631 candidate waveform blocks across 977 scanned candidates.

### Driver Bank Waveform Groups (bank `$13`)

| Group | ROM Range | Count | Description |
|-------|-----------|-------|-------------|
| 38 | `$26B5F-$26B9E` | 2 | Special shapes (silence/noise init?) |
| 39 | `$26C57-$27896` | 98 | **Main waveform table** - indexed by instrument table at `$23CF` |
| 40 | `$27A4A-$27A69` | 1 | Isolated waveform |
| 41 | `$27A8E-$27AAD` | 1 | Isolated waveform |
| 42 | `$27AE7-$27B06` | 1 | Isolated waveform |

### Waveform Format

- 32 x 5-bit samples per waveform (PSG R6, bits 4-0)
- Values: `$00`-`$1F`
- Stored as packed bytes (one sample per byte, upper 3 bits unused/zero)
- Sequential in ROM - no gaps between waveforms in a group
- Waveform pointer table at ROM `$26BA4` provides 16-bit logical pointers indexed by instrument ID

### Access Pattern

```
Instrument select:
  LDA $23CF,X    ; instrument table[channel] -> waveform index
  TAX
  LDA wave_lo,X  ; pointer table lo byte  (ROM $26BA4)
  STA $CE
  LDA wave_hi,X  ; pointer table hi byte
  STA $CF
  JSR waveform_loader  ; writes 32 bytes from ($CE) to PSG R6
```

Full extraction and visualisation of all 98 driver waveforms is in `waveforms.md`.

---

## Memory Map (Runtime, typical page assignment)

| Page | Logical | Bank(s) | Contents |
|------|---------|---------|----------|
| 0 | `$0000-$1FFF` | `$FF` (I/O mirrors) | Hardware registers |
| 1 | `$2000-$3FFF` | `$12` or `$13` | Driver / support tables |
| 2 | `$4000-$5FFF` | `$0F`-`$11` (swapped) | Waveform data banks |
| 3 | `$6000-$7FFF` | variable | Game data |
| 4 | `$8000-$9FFF` | variable | Game data / code |
| 5 | `$A000-$BFFF` | variable | Game data / code |
| 6 | `$C000-$DFFF` | variable | DDA voice sample bank (ZP `$4C,X`) |
| 7 | `$E000-$FFFF` | `$00` | Always-mapped: init, interrupt handlers, streamer |

Page assignments are dynamic - the TAM scan found 46 TAM instructions in bank `$00` alone.

---

## Key Zero-Page Variables

| Address | Name (inferred) | Description |
|---------|----------------|-------------|
| `$D2` | `driver_status` | Driver re-entrancy guard + active flag |
| `$CE:$CF` | `wave_ptr` | Waveform data pointer (set before waveform loader) |
| `$CC:$CD` | `cmd_ptr` | DDA voice command stream pointer (bank `$13` reads via `($CC),Y`) |
| `$3A,X` | `ch_active[X]` | Voice channel active flag (X = channel 0-4) |
| `$3B,X` | `ch_nibble[X]` | Sample nibble-packing mode flag |
| `$3C` | `ch_active[2]` | **Channel 2 active flag** — set when voice SFX is playing |
| `$40,X-$41,X` | `ch_ptr[X]` | Sample read pointer in page 6 |
| `$42:$43` | `ch_ptr[2]` | **Channel 2 sample read pointer** (lo:hi) — loaded from descriptor `+2/+3` |
| `$4C,X` | `ch_bank[X]` | Sample bank mapped to page 6 |
| `$4E` | `ch_bank[2]` | **Channel 2 sample bank** — set from descriptor byte `+6` before each sample plays (`$09`, `$12`, or `$17` for sounds `$33–$3A`) |
| `$53,X` | `ch_rate[X]` | DDA playback rate counter |
| `$58,X` | `ch_frac[X]` | Fractional advance accumulator |

---

## Files

| File | Description |
|------|-------------|
| `Gunhed (Japan).pce` | Source ROM |
| `bin/Gunhed_louder_v5.pce` | **Best patch** — PSG-register-only (CRC `11D4936D`), base for custom injection |
| `bin/Gunhed_louder_v6.pce` | v5 + algorithmic sample boost ×1.154 (CRC `CB4B2670`) — **abandoned** (no audible improvement in-game) |
| `bin/Gunhed_custom.pce` | **Current output** — v5 base + custom WAV injection (CRC varies with edits) |
| `Gunhed-RE.ipynb` | Analysis notebook (all scan/extraction code) |
| `bin/voice_sfx/sound_XX.wav` | DDA voice sample WAV exports (8 files, 6991 Hz mono, 8-bit unsigned PCM). One per sound ID `$33`–`$3A`. |
| `bin/voice_sfx_custom/` | **Custom WAVs for injection** — edit these in Audacity, then run `inject_voice_sfx.py` |
| `bin/voice_sfx_preview/` | Preview outputs from `preview_voice_sfx.py` — 4-bit quantized, exactly what the PCE plays |
| `extract_voice_sfx.py` | Standalone extraction script — no notebook needed, all context embedded |
| `inject_voice_sfx.py` | **WAV injection script** — reads custom WAVs, converts to 4-bit nibbles with TPDF dithering, patches into ROM |
| `preview_voice_sfx.py` | **4-bit preview script** — produces WAV files showing exactly what the PCE DAC will output after quantization |
| `huc6280_disasm.py` | Standalone HuC6280 disassembler module — 218 opcodes, exports `disasm()`, `disasm_bank()`, `get_bank()`, `rom_info()` |
| `Gunhed-Disasm.ipynb` | Boot sequence / bank $08 disassembly notebook (patch development) |
| `extracts/gunhed_boot_pseudocode.c` | Annotated C pseudocode of boot sequence and key subroutines |
| `bin/Gunhed_soundtest_boot_v6.pce` | ✅ **Sound test direct-boot** — boots to SOUND 01 menu, bypassing title/intro (CRC `5EBCA528`) |
| `patch_soundtest_boot_v4.py` | Standalone script to create sound test direct-boot patch (see §13) |
| `waveforms.md` | All 98 driver waveforms with hex values and visualisations |
| `etripator.md` | Etripator disassembler setup, starter JSON configs, progressive analysis plan |
| `instructions.md` | This file |

---

## Further Analysis - Suggested Next Steps

### 1. Complete Driver Disassembly

The driver tick at ROM `$26000` calls subroutines at `$49D9`, `$49FF`, `$484F`, `$4262`, `$471C`, `$478F`, `$483B` (all logical addresses in page 1/2 range). These are in bank `$12` (`$24000-$25FFF`) and upper bank `$13`.

**Approach**:
- Set a breakpoint at `$EA2E` (Timer IRQ -> driver) in Geargrafx
- Single-step through the ISR to trace the full call graph
- Disassemble `$24000-$27FFF` (banks `$12`-`$13`) as a single logical unit

```python
# Notebook: disassemble driver banks $12-$13
# Use mcp_geargrafx_get_disassembly with start=$2000, end=$3FFF
# after confirming page 1 maps bank $13
```

### 2. Music Sequence Format (banks `$15`-`$16`)

Banks `$15` and `$16` contain only `STA $0800` (channel select) writes with no other PSG register writes - this is characteristic of a **command-byte stream** where the driver reads sequence data and dispatches to PSG subroutines itself.

**Approach**:
- Break on `LDA $23xx,X` reads from the note table (ROM `$26000` area)
- Trace back to where the sequence pointer is loaded
- Look for `$FF` bytes (common Compile stream terminator) as phrase boundaries
- Scan banks `$15`-`$16` for repeating patterns of 3-byte note entries

### 3. SFX Trigger Mechanism

The isolated `STX $0800` at ROM `$542A0` (bank `$2A`) is suspicious. Saint Dragon used a table lookup with a single-byte SFX ID. Compile likely uses a similar approach.

**Approach**:
- Set a memory write breakpoint on `$0800` in Geargrafx during gameplay
- Note the call stack - the JSR chain leading here is the SFX trigger path
- Look for `LDA #sfx_id / JSR sfx_play` patterns near the isolated PSG write

### 4. DDA Voice Sample Banks

The voice streamer at `$EA3D` loads `LDA $4C,X` to get the sample bank at runtime. Static analysis cannot resolve this - emulator tracing is needed.

**Approach**:
- Break on `TAM #$40` (`53 40`) in bank `$00` during gameplay/attract mode
- Read the accumulator value at break - that is the sample bank number
- Dump that bank and scan for `$80` end-of-sample markers and nibble-packed data
- Typical Compile sample rate: ~8 kHz -> ~7160000 / (rate_counter x 2) Hz

### 5. Graphics Extraction

PC Engine background tiles are stored as **4bpp planar CHR** (4 bitplanes, 8x8 pixels, 32 bytes per tile). Sprites use a similar format.

**Known VRAM layout clues from TAM scans**:
- Banks `$01`-`$0E` (ROM `$02000-$1DFFF`) are likely game code and graphics data
- The VDC IRQ at `$EB03` handles raster splits and DMA - tracing this reveals VRAM load addresses

**Approach**:
- Scan entire ROM for the **CHR signature**: 32-byte blocks where every 4 bytes follow the bitplane pattern (each byte pair represents one row of 2bpp data)
- A simpler heuristic: scan for 32-byte runs where bytes appear in correlated pairs at offsets +0/+1 and +2/+3 (bitplane pairs)
- Alternatively, set a VDC DMA breakpoint (`ST0`/`ST1`/`ST2` writes to VDC register `$12` = VRAM write address, `$13` = DMA source)

```python
# Notebook cell: find VDC DMA transfers
# Scan for ST0 (03 00), ST1 (13 xx), ST2 (23 xx) sequences
# ST0 #$12 followed by ST1/ST2 pairs = VRAM write address setup
# ST0 #$10 followed by ST1 lo / ST2 hi = DMA source address
VDC_ST0 = bytes([0x03])
# Then scan for: 03 12 13 xx 23 xx (VRAM write address)
# and:          03 10 13 xx 23 xx (DMA src lo / hi)
```

- Once DMA source addresses are known, dump those ROM regions and decode as 4bpp planar CHR
- Tools: the existing `bitmap_buffer.c` pipeline in this workspace can render CHR tiles

### 6. Tilemap / BAT Layout

The PC Engine BAT (Background Attribute Table) is 64x32 or 128x32 words in VRAM. Each word is `[palette:4 | tile_index:12]`.

**Approach**:
- Capture a screenshot in Geargrafx during a title screen / gameplay
- Use `mcp_geargrafx_get_disassembly` to trace the VDC setup at reset
- Look for `ST0 #$02` (write to R2 = MAWR, Memory Address Write Register) followed by bulk `ST1`/`ST2` writes - these fill the BAT

### 7. Palette Data

PC Engine palettes are 16 colours x 16 palettes = 256 entries x 9-bit RGB stored in the HuC6260 colour RAM.

**Approach**:
- Set a breakpoint on writes to `$0402` (HuC6260 colour write register)
- The bytes written before/after a palette load are the colour data
- Scan ROM for `ST0 #$00 / ST1 lo / ST2 hi` (set colour RAM address) followed by bulk colour writes

### 8. Bank Cross-Reference

The TAM summary showed heavy TAM usage in banks `$03`, `$06`, `$08`-`$0D`. These likely contain the main game engine and level managers.

**Approach**:
- Dump all TAMs in a specific bank (e.g. `$0D` with 54 TAMs) and decode the `LDA #bank / TAM` pairs to build a bank-swap call graph
- This reveals which code banks depend on which data banks and gives the full runtime layout

---

### 9. Sound Test — Bank `$08` Full Disassembly

The sound test program is now substantially traced. Known executed ranges:

| Range | Description |
|-------|-------------|
| `$4000` | Per-frame handler (called by IRQ1 handler every VBLANK) |
| `$4005–$4023` | Entry: init flags `$2374`, VDC cleanup, table init, CLI |
| `$4024–$4029` | Far-call `$49C2` mode `$00` (stop sound) via `JSR $EF22` + inline data |
| `$402A–$4043` | Intro animation setup (scroll pos, palette, text pointer) |
| `$4044` | `JSR $F922` — re-enable VBLANK IRQ (required for frame sync) |
| `$405F–$40BD` | Intro animation loop (scroll text, check P2 button to skip) |
| `$40B8` | `JMP $4162` — skip intro to menu (P2 button press) |
| `$40DB` | `JMP $E000` — exit/reset |
| `$4162` | **Menu entry**: far-call `$49C2` (stop sound) |
| `$4168` | `JSR $4217` — draw menu screen (calls `$F1B5` fade-out, needs VBLANK!) |
| `$416B–$4183` | Menu variable init (`$C7`, `$C8`, VRAM pointer, clear `$23A0`) |
| `$417D` | `JSR $F199` — fade-in (enables BG+sprites via `$F91A`, enables VBLANK via `$F922`) |
| `$418A` | Menu input loop (`JSR $41E6` / `JSR $4302` / `BEQ $418A`) |
| `$4217–$4255` | Screen init (draw menu text, setup VRAM) |
| `$4302–$4355` | Menu navigation (right/left scroll, SEC/CLC return) |
| `$4414–$4665` | Script interpreter (opcode dispatch at `$442E,Y`) |
| `$46B4–$46BF` | Sprite clear loop |
| `$471B–$477A` | Sprite setup |

**Key VBLANK dependency chain**: `$4168: JSR $4217` → `$4219: JSR $F1B5` (fade-out) → `$F1F0` → `$F299: STZ $10; LDA $10; CMP #$01; BCC` (VBLANK wait loop). If VBLANK IRQ is not firing, this spins forever.

**Untraced ranges in bank `$08`**: `$4666–$46B3`, `$4780–$5FFF`. These likely contain level-specific data or additional menu screens.

---

### 10. Voice SFX Sample Data Analysis — Result: 13% Headroom → v6 Applied

v5 exhausted all PSG register-level volume increases. The sample data was then analysed to check whether **nibble-level amplitude boosting** could further increase DDA voice volume.

**Sample encoding**: samples are nibble-packed 4-bit DDA PCM, two nibbles per byte:
- Lower nibble first: `byte & 0x0F` → written to R6
- Upper nibble second: `(byte >> 4) & 0x0F` → written to R6
- `$00` byte = phrase-end marker (silence floor, both nibbles = 0 → PCM = 0)
- Sample rate: **6,991 Hz** (inferred from ZP rate counter `$53,X` = 0 → direct)

Maximum nibble value = 15. If samples peak below 15, headroom exists.

**Analysis results** — correct descriptors (desc[16]–[23]), extraction using `$00` phrase-end detection:

| Sound | Desc | Bank | ROM start | Nibbles | Peak | Headroom |
|-------|------|------|----------|---------|------|----------|
| `$33` | [16] | `$09` | `$12000` | 6,016 | **13/15** | 13.3% |
| `$34` | [17] | `$12` | `$25462` | 5,600 | **12/15** | 20.0% |
| `$35` | [18] | `$09` | `$12BC1` | 4,704 | **13/15** | 13.3% |
| `$36` | [19] | `$17` | `$2E000` | 5,024 | **12/15** | 20.0% |
| `$37` | [20] | `$17` | `$2E9D1` | 5,120 | **13/15** | 13.3% |
| `$38` | [21] | `$09` | `$134F2` | 5,376 | **12/15** | 20.0% |
| `$39` | [22] | `$17` | `$2F3D2` | 2,624 | **11/15** | 26.7% |
| `$3A` | [23] | `$17` | `$2F8F3` | 3,392 | **12/15** | 20.0% |

Global peak = 13/15 → boost factor ×1.154 normalises loudest peak to 15.

Algorithmic nibble boost variants were tested (v6 through v7d) but **all produced no audible improvement or increasingly muffled/distorted results** because hard-clamping at nibble 15 crushes the waveform's dynamic range — the effect is compression/limiting at 4-bit resolution with no makeup gain possible. **This approach has been superseded by the custom WAV injection workflow** (see §12 below), which allows full Audacity processing (normalize, compress, EQ) before 4-bit quantization with TPDF dithering.

| Variant | Boost | Clipped nibbles | Clip % | CRC32 | Result |
|---------|-------|-----------------|--------|-------|--------|
| v6 | ×1.154 | 6 | 0.0% | `CB4B2670` | **Abandoned** — no audible improvement in-game |
| v7 | ×1.364 | 629 | 1.7% | `5AC164FE` | Slightly louder, minor artifacts |
| v7b | ×1.500 | 2,428 | 6.4% | `E78177B0` | Noticeably compressed |
| v7c | ×1.750 | 7,678 | 20.3% | `8A6ACC3A` | Muffled, lost dynamics |
| v7d | ×2.000 | 31,510 | 83.2% | `32035334` | Extremely distorted — nearly square wave |

> **Lesson learned**: algorithmic nibble boosting with clamping is inherently limited at 4-bit depth. With only 16 amplitude levels, any clipping immediately eats into the already-tiny dynamic range. Professional audio tools (compression, normalization, EQ) applied in Audacity before quantization produce far better results.

> **Root cause of earlier 15/15 false reading**: the `$80`-detection approach overshot bank boundaries and landed in adjacent ROM data (waveform tables, code), which happened to have high nibble values. The correct `$00` phrase-end detection stays within each bank's speech region and reveals the true peaks (11–13).

> **Investigation pitfall**: An earlier extraction attempt used `DDA_CONFIRMED = {$01, $10, $12}` as a bank filter and found wrong descriptors (desc[4]–[26] from banks `$0F`/`$10`/`$11`), and also set `VOICE_SFX_FIRST_DESC = 17` (off by one). The correct filter is `flags=$88` in the descriptor table, selecting exactly desc[16]–[23], and the correct banks are `$09`, `$12`, `$17`.

---

### 11. Voice SFX Bank Layout

Each voice SFX bank packs consecutive speech phrases back-to-back, separated by `$00` bytes (silence floor). Each descriptor points to the **start** of its own unique phrase — not into a shared stream.

| Bank | ROM Range | Sound | ROM start → end | Duration |
|------|-----------|-------|----------------|----------|
| `$09` | `$12000–$13FFF` | `$33` | `$12000 → $12BC0` | 861 ms |
| `$09` | | `$35` | `$12BC1 → $134F1` | 673 ms |
| `$09` | | `$38` | `$134F2 → $13F72` | 769 ms |
| `$12` | `$24000–$25FFF` | `$34` | `$25462 → $25F52` | 801 ms |
| `$17` | `$2E000–$2FFFF` | `$36` | `$2E000 → $2E9D0` | 719 ms |
| `$17` | | `$37` | `$2E9D1 → $2F3D1` | 732 ms |
| `$17` | | `$39` | `$2F3D2 → $2F8F2` | 375 ms |
| `$17` | | `$3A` | `$2F8F3 → $2FF93` | 485 ms |

Banks `$09` and `$17` are nearly filled by their speech data (8,048 and 8,080 of 8,192 bytes respectively). Bank `$12` holds only s$34 plus driver support tables at the bank start.

**End-of-phrase marker**: `$00` byte — both nibbles = 0 → PCM output 0 = silence floor. The DDA playback loop's `BMI` instruction fires on the `$80` terminator byte that follows, but the audible break in the waveform begins at the `$00` byte.

**Extraction algorithm** (`extract_voice_sfx.py`):
1. Parse descriptor table at ROM `$278D0`, 8 bytes/entry, pick entries [16]–[23]
2. For each descriptor, scan from `rom_sample` for the first `$00` byte (= `end_rom`)
3. Decode bytes `[rom_sample, end_rom)` as lo/hi nibble pairs → 8-bit unsigned PCM (nibble × 17)
4. Write as 8-bit mono WAV at 6,991 Hz

This produces one clean WAV per sound ID. See `extract_voice_sfx.py` for the fully-documented standalone implementation.

---

## Tools Reference

| Tool | Use |
|------|-----|
| `Gunhed-RE.ipynb` | All static analysis - edit `DRIVER_BANK`, `WAVEFORM_BANK` parameters and re-run |
| `mcp_geargrafx_load_media` | Load `Gunhed (Japan).pce` into Geargrafx |
| `mcp_geargrafx_set_breakpoint_range` | Break on PSG writes, TAM instructions, specific subroutines |
| `mcp_geargrafx_get_disassembly` | Disassemble any logical address range post-execution |
| `mcp_geargrafx_get_call_stack` | Trace JSR chain at a breakpoint |
| `mcp_geargrafx_memory_search` | Find specific values in RAM (ZP variables, channel state) |
| `mcp_geargrafx_memory_search_capture` | Snapshot RAM for before/after comparison |
| [Etripator](https://github.com/pce-devel/Etripator) | HuC6280-aware static disassembler - outputs annotated HuCC ASM from JSON config |


> For Etripator disassembler setup, starter JSON configs and progressive analysis plan, see [etripator.md](etripator.md).

---

## PSG Volume Control Mechanism

### Volume Chain

The PC Engine PSG has a three-level volume chain. The audible amplitude is the product of all three:

| Register | Address | Bits | Role | Gunhed value |
|----------|---------|------|------|--------------|
| R1 (global amp) | `$0801` | 7:0 | Master level: L=bits 7-4, R=bits 3-0 | `$FF` (fixed - max) |
| R4 (channel ctrl) | `$0804` | 7: chON, 6: DDA, 4-0: vol | Per-channel volume + mode | dynamic (see below) |
| R5 (stereo pan) | `$0805` | 7-4: L, 3-0: R | Per-channel L/R pan | dynamic from `$23D5,X` |

R1 is written once at startup (ROM `$269AD`) to `$FF` - it is never touched again. All effective volume changes happen through R4 (bits 4-0 = 0-31) and R5 (nibble-per-side = 0-15).

### PSG Output Loop (Bank `$13`, ROM `$26000`)

The sound driver tick runs every timer IRQ. The **PSG output subroutine** at logical `$484F` (ROM `$2615C`-`$261AA`, bank `$13` mapped to page 1) iterates over 6 channels (X = 0-5) writing all PSG registers per tick:

```
$261A5: BD CF 23    LDA $23CF,X     ; channel active flag / instrument index
                                    ; if zero -> channel muted, skip
$261A8: 09 80       ORA #$80        ; OR in chON bit (bit 7)
                                    ; *** vol bits 4-0 come from $23CF,X ***
$261AA: 8D 04 08    STA $0804       ; write R4

$2615C: BD D5 23    LDA $23D5,X     ; stereo pan from RAM table
$26161: 8D 05 08    STA $0805       ; write R5
```

The `ORA #$80` instruction is the **sole volume gate**. Because `$80` only sets bit 7 (chON) and leaves bits 4-0 unchanged, the actual channel volume is whatever bits 4-0 are in `$23CF,X` at runtime. If the music driver writes low values there, the volume is low. Pan (R5) comes from the RAM table at `$23D5,X`, initialised by the note-on sequence.

### RAM Tables (populated at runtime by music sequencer)

| RAM Address | Contents |
|-------------|----------|
| `$23CF,X` | Channel active flag + instrument index (bits 4-0 = vol for R4) |
| `$23D5,X` | Stereo pan byte for R5 (L nibble = bits 7-4, R nibble = bits 3-0) |
| `$23E7`-`$23EC` | Initial per-channel volume (written `$FF` by init at `$49A3`) |
| `$23DB,X` | Frequency-related byte |
| `$23E1,X` | Frequency high byte |

These are **RAM addresses** - they cannot be patched in ROM. Static ROM patching of values at ROM `$241CF` / `$243D5` (bank `$12`) changes unrelated data and is ineffective.

### Correct Patch Points — Music Channels (ROM, bank `$13`)

| ROM Offset | Original | Meaning |
|-----------|---------|---------|
| `$261A9` | `$80` | Operand of `ORA #$80` - controls chON + forced vol bits |
| `$2615C`-`$2615E` | `BD D5 23` | `LDA $23D5,X` - loads dynamic pan from RAM |

To force volume, change the operand at `$261A9`. To force pan, replace the 3-byte `LDA $23D5,X` with `LDA #$xx / NOP`.

**ORA operand quick reference**:

| Byte | Vol (bits 4-0) | % of max | Notes |
|------|---------------|----------|-------|
| `$80` | 0  | 0% | Original - volume from RAM only |
| `$87` | 7  | 23% | Gentle boost floor |
| `$8C` | 12 | 39% | Moderate |
| `$8F` | 15 | 48% | Half volume - good starting point for v4 |
| `$94` | 20 | 65% | Noticeably louder |
| `$97` | 23 | 74% | Loud but still dynamic |
| `$9C` | 28 | 90% | Near-max |
| `$9F` | 31 | 100% | Max - used in v3, too loud |

### Correct Patch Points — DDA Voice Channels (ROM, bank `$13`)

DDA channels use `ORA #$C0` (chON=1, DDA=1, vol=0/31) before writing R4. Bits 4–0 are a volume attenuator, and the original driver leaves them at 0/31.

| ROM Offset | Original | Location | Meaning |
|-----------|---------|----------|--------|
| `$26571` | `$C0` | Operand of `ORA #$C0` at `$26570` | DDA per-channel vol loop — `LDA $23FD,X / ORA #$C0 / STA $0804` |
| `$2687A` | `$C0` | Operand of `ORA #$C0` at `$26879` | DDA channel-amplitude routine — `LDA $23E4 / ORA #$C0 / STA $0804 / RTS` |

Pan note: immediately after `$26570` the driver writes `LDA #$FF / STA $0805` — DDA pan is already forced to `$FF` (L=15, R=15) by the driver itself.

**DDA ORA operand quick reference** (bit 7 = chON, bit 6 = DDA, bits 4–0 = vol floor):

| Byte | Vol floor | % of max | Notes |
|------|----------|----------|-------|
| `$C0` | 0  | 0%  | Original — DDA active, vol from RAM only |
| `$C7` | 7  | 23% | Gentle floor |
| `$CF` | 15 | 48% | Half — used in v5 |
| `$D7` | 23 | 74% | Loud |
| `$DF` | 31 | 100% | Max DDA volume |

---

### Patch Version History

| Version | File | Bytes changed | Patch description | Result |
|---------|------|--------------|-------------------|--------|
| v1 | `Gunhed_louder.pce` | 235x32 waveform bytes | Waveform amplitudes +20% | **Ineffective** - volume is register-controlled |
| v2 | `Gunhed_louder_v2.pce` | 34 bytes at ROM `$241CF`/`$243D5` | Patched ROM at "wrong bank" (bank `$12`) | **Ineffective** - `$23CF`/`$23D5` are RAM, not ROM |
| v3 | `Gunhed_louder_v3.pce` | **4 bytes** | `$261A9`: `$80`->`$9F`; `$2615C`-`$2615E`: `BD D5 23`->`A9 FF EA` | **Works but too loud** - vol=31, pan=$FF forced every tick |
| v4 | `Gunhed_louder_v4.pce` | **1 byte** | `$261A9`: `$80`→`$8F` (vol floor=15/31, pan dynamic) | Intermediate music boost, DDA unchanged |
| v5 | `Gunhed_louder_v5.pce` | **3 bytes** | v4 music patch + `$26571`: `$C0`→`$CF`; `$2687A`: `$C0`→`$CF` (DDA vol floor=15/31) | Music + DDA both boosted |
| v6 | `Gunhed_louder_v6.pce` | **18,810 bytes** | v5 PSG patches + voice sample data boost ×1.154 across 8 regions (peak nibble 13→15) | **Abandoned** — no audible improvement in-game |
| v7–v7d | `Gunhed_louder_v7*.pce` | ~18,900 bytes | Higher algorithmic boost factors (×1.36 to ×2.0) with increasing nibble clamping | **Abandoned** — muffled/distorted at high clipping |
| custom | `Gunhed_custom.pce` | varies | v5 base + custom WAV injection with TPDF dithering | **Current approach** — full Audacity control |

### CRC32 Checksums

| ROM | CRC32 | Status |
|-----|-------|--------|
| `Gunhed (Japan).pce` (original) | `A17D4D7E` | source |
| `Gunhed_louder_v3.pce` | `F14B692B` | superseded |
| `Gunhed_louder_v4.pce` | `1C442248` | superseded |
| `Gunhed_louder_v5.pce` | `11D4936D` | **BEST** — base for custom injection |
| `Gunhed_louder_v6.pce` | `CB4B2670` | abandoned — no audible improvement |
| `Gunhed_louder_v7.pce` | `5AC164FE` | experimental — abandoned |
| `Gunhed_louder_v7b.pce` | `E78177B0` | experimental — abandoned |
| `Gunhed_louder_v7c.pce` | `8A6ACC3A` | experimental — abandoned |
| `Gunhed_louder_v7d.pce` | `32035334` | experimental — abandoned |
| `Gunhed_custom.pce` | varies | **CURRENT** — custom WAV injection |
| `Gunhed_soundtest_boot.pce` (v3) | `6E5847B9` | **FAILED** — black screen, VBLANK never enabled (see §13) |
| `Gunhed_soundtest_boot_v4.pce` | `6D6FBC29` | **FAILED** — same root cause as v3 (see §13) |
| `Gunhed_soundtest_boot_v5.pce` | `EAE01103` | Partial — boots to menu but garbled display (missing VRAM init) |
| `Gunhed_soundtest_boot_v6.pce` | `5EBCA528` | ✅ **WORKING** — direct boot to sound test with full display |

---

### v5/v6 — Maximum Volume Achieved (All Mechanisms)

v5 is the **maximum achievable via PSG register patching**. Live verification in Geargrafx during sound `$33` playback:

```
PSG channel 2: dda=1, enabled=1, amplitude=$FF
  vol_left=$0F (15/15), vol_right=$0F (15/15)  ← absolute hardware maximum
```

Summary by sound category:

| Category | Patch site | v5 state | Can go higher? |
|----------|-----------|----------|---------------|
| Music channels (waveform) | ROM `$261A9` (`ORA #$8F`) | vol floor = 15/31, pan dynamic | No — R4 vol bits already at floor 15; R1 global amp `$FF` |
| DDA voice SFX ($33–$3A) | ROM `$26571` (`ORA #$CF`) | vol = 15/31, pan L15/R15 | PSG ceiling reached — v6 boosts sample data ×1.154 instead |
| DDA music amplitude (`$2879`) | ROM `$2687A` (`ORA #$CF`) | same ceiling | No — tested: `$2879` never fires during voice SFX |

**Sample data analysis (see Further Analysis §10)**: correct extraction (`$00` phrase-end detection, desc[16]–[23]) reveals DDA voice samples peak at nibble 13/15. There is 13% headroom. v6 applied a ×1.154 algorithmic boost, but this was superseded by the **custom WAV injection workflow** (§12) which gives full Audacity control over the audio before 4-bit quantization.

---

### 12. Custom WAV Injection Workflow

Algorithmic nibble boosting (v6–v7d) has diminishing returns at 4-bit depth. The custom injection approach gives full control via professional audio tools.

**Workflow:**
1. Extract originals: `python extract_voice_sfx.py` → `bin/voice_sfx/sound_33.wav` – `sound_3A.wav`
2. Copy to edit folder: `bin/voice_sfx_custom/`
3. Edit in Audacity (normalize, compress, EQ, amplify — any processing)
4. Export as WAV — **Signed 16-bit PCM** recommended (any sample rate works, auto-resampled to 6991 Hz)
5. Preview: `python preview_voice_sfx.py bin/voice_sfx_custom/sound_38.wav` → listen to `_preview.wav`
6. Inject: `python inject_voice_sfx.py` → `bin/Gunhed_custom.pce`

**Only edited files need to be present** — missing files keep original ROM data unchanged.

**Size constraint:** each sound has a fixed ROM region. The injected sample cannot exceed the original byte count (shown as "Max bytes" by the injection script). Shorter samples are padded with silence. Longer samples are truncated with a warning.

**TPDF Dithering:** the injection and preview scripts apply Triangular Probability Density Function dithering before 4-bit quantization. This replaces harsh quantization distortion with gentle uncorrelated noise — the standard technique for low-bit-depth audio. Without dithering, the hard rounding to 16 levels creates audible correlated artifacts that sound "crunchy".

**Sound regions (max injectable bytes):**

| Sound | Bank | ROM start | Orig bytes | Max bytes | Orig ms |
|-------|------|-----------|------------|-----------|--------|
| `$33` | `$09` | `$12000` | 3,008 | 3,008 | 861 |
| `$34` | `$12` | `$25462` | 2,800 | 2,973 | 801 |
| `$35` | `$09` | `$12BC1` | 2,352 | 2,352 | 673 |
| `$36` | `$17` | `$2E000` | 2,512 | 2,512 | 719 |
| `$37` | `$17` | `$2E9D1` | 2,560 | 2,560 | 732 |
| `$38` | `$09` | `$134F2` | 2,688 | 2,829 | 769 |
| `$39` | `$17` | `$2F3D2` | 1,312 | 1,312 | 375 |
| `$3A` | `$17` | `$2F8F3` | 1,696 | 1,804 | 485 |

**Audacity tips for 4-bit audio:**
- Set project rate to **6991 Hz** to avoid resampling artifacts
- **Effect → Compressor** reduces dynamic range so more signal uses the 16 available levels
- **Effect → Loudness Normalization** (target -1 dB) uses the full range
- Avoid subtle effects (reverb, gentle EQ) — they get lost in 4-bit quantization
- Bold moves work better — hard compression, aggressive normalization
- Always preview with `preview_voice_sfx.py` before injecting — it shows exactly what the PCE DAC will output

---

### 13. Sound Test Direct-Boot Patch — ✅ SOLVED (v6)

**Goal**: Create a ROM patch that boots directly to the "SOUND 01" menu screen, bypassing the title screen, intro animation, and gameplay — useful for rapid audio testing.

**Status**: ✅ **Working.** Patch v6 (two-site, 9 bytes total) boots directly to the sound test menu with all VRAM assets correctly loaded. CRC `5EBCA528`.

#### Boot Flow to Sound Test (normal game)

In the original ROM, the player navigates: Title → Options → Sound Test. The boot sequence at `$E000` is **linear** — it falls through to `$E092: JSR $4005` which enters the sound test program in bank `$08`. The code between `$E077` and `$E092` is always executed:

```
$E077: JSR $F922    ; VDC CR |= $0A → enable VBLANK+overflow IRQ, then CLI
                    ; IRQ1 handler starts firing; does per-frame updates via $4000/$C000
$E07A–$E083:        ; clear score/state variables (4 stores)
$E086: SEI          ; mask all interrupts
$E08A: JSR $F926    ; VDC CR &= $F0 → disable ALL VDC IRQ sources (VBLANK off!)
$E08D: MODE $32     ; map sound test banks: MPR2=$08, MPR3=$09, MPR4=$05, MPR5=$01, MPR6=$02
$E092: JSR $4005    ; enter bank $08 (sound test program)
```

> **Corrected understanding**: The IRQ1 handler at `$EB03` is a **normal ISR** (returns via RTI). It does NOT hijack the main thread. During the few frames between `$E077` (CLI) and `$E086` (SEI), the handler fires and calls `$4000`/`$C000` in the current mode's banks, but it returns to the main thread each time. The main thread falls through linearly to `$E092`.

#### Bank `$08` Sound Test Program Flow

```
$4005–$4023: Init (set flag $2374, VDC cleanup, table init, CLI)
$4024:       JSR $EF22 → far-call $49C2 mode $00 (stop sound)
$402A–$4043: Intro animation setup (scroll pos, palette, text)
$4044:       JSR $F922 → ★ re-enable VBLANK IRQ (VDC CR |= $0A + CLI)
$405F–$40BD: Intro animation loop
$40B8:       JMP $4162 (P2 button → skip intro to menu)
$40DB:       JMP $E000 (exit/reset)
─── Menu Entry ───
$4162:       JSR $EF22 → far-call $49C2 (stop sound)
$4168:       JSR $4217 → draw menu (calls $F1B5 fade-out → $F29B VBLANK wait)
$416B–$4183: Menu variable init
$417D:       JSR $F199 → fade-in (enables VBLANK + BG + sprites)
$418A:       Menu input loop (JSR $41E6 / JSR $4302 / BEQ $418A)
```

**The VBLANK dependency**: `$4217` (draw menu) calls `$F1B5` (fade-out), which calls `$F29B` (VBLANK sync: `STZ $10; loop: LDA $10; CMP #$01; BCC loop`). The IRQ1 handler at `$EB03` increments ZP `$10` on every VBLANK. **If VBLANK IRQ is not enabled in the VDC CR, `$10` stays 0 and the loop spins forever.**

#### The Core Problem

By the time `$4005` is entered, VBLANK is **disabled at TWO levels**:

1. **CPU level**: `$E086: SEI` masks all interrupts (fixed by `$4023: CLI` inside bank $08 init)
2. **VDC level**: `$E08A: JSR $F926` clears VDC CR bits 0–3 → VBLANK IRQ source is OFF

The VDC-level disable is the killer. Even after `CLI` at `$4023`, no VBLANK fires because the VDC isn't generating them. In the normal flow, `$4044: JSR $F922` re-enables VBLANK in the VDC CR during the intro animation. Any patch that skips the intro also skips this critical `$F922` call.

#### Patch Attempts

**v3** (CRC `6E5847B9`) — TWO patches:
1. ROM `$00077`: `20 22 F9` → `EA EA EA` — NOP boot's `JSR $F922`
2. ROM `$10024`: `20 22 EF` → `4C 62 41` — `JMP $4162` (skip intro to menu)

**Result**: ❌ Black screen. Patch 1 was based on the incorrect belief that `$F922` "hijacks" the main thread. It doesn't — it just enables VBLANK IRQ. With both patches applied, VBLANK is never enabled anywhere: boot's `$F922` is NOPed, and the intro's `$4044: JSR $F922` is skipped by the JMP. The fade-out routine at `$F1B5` (called from `$4217` draw menu) spins forever at `$F29B` waiting for ZP `$10` ≥ 1.

**v4** (CRC `6D6FBC29`) — ONE patch only:
- ROM `$10024`: `20 22 EF` → `4C 62 41` — `JMP $4162` (skip intro to menu)
- Boot's `JSR $F922` left intact

**Result**: ❌ Black screen. Same call stack: stuck in `$F29B`. The issue is that boot's `$F922` at `$E077` enables VBLANK, but then `$E08A: JSR $F926` immediately **disables** it again (VDC CR &= $F0). By the time we enter `$4005`, VBLANK is off at VDC level. The `JMP $4162` at `$4024` skips the only place that re-enables it (`$4044`).

#### v5 — Single-site (VBLANK fix only) — Partial Success

The `JSR $EF22` at `$4024` is followed by 3 inline data bytes (read by the far-call dispatcher). This gives us **6 consecutive bytes** to work with (`$4024–$4029`):

```
Original (6 bytes):
  $4024: 20 22 EF    JSR $EF22    ; far-call dispatcher
  $4027: 00 C2 49    ; inline: mode=$00, addr=$49C2

v5 patch (6 bytes):
  $4024: 20 22 F9    JSR $F922    ; re-enable VBLANK IRQ (VDC CR |= $0A + CLI)
  $4027: 4C 62 41    JMP $4162    ; skip intro → menu entry
```

**ROM offset**: `$10024` — 6 bytes: `20 22 EF 00 C2 49` → `20 22 F9 4C 62 41`

**Result**: ⚠️ **Partially working** (CRC `EAE01103`). Boots to the sound test menu — VBLANK works, fade-in/out completes, menu loop runs. **BUT the display shows garbled/invisible text** because the jump from `$4024` to `$4162` skips all initialisation between `$402A–$4046` — including `JSR $F2FE` and `JSR $F38E` which load palette and font data that the menu draw routine (`$4217`) depends on.

#### v6 — Two-site (VRAM init preserved) — ✅ WORKING

The fix: instead of jumping from `$4024`, let the init code at `$402A–$4046` execute normally (palette, font, RAM clear, VBLANK enable), then jump over the intro animation at `$4047`:

```
Site 1 — ROM $10024 (logical $4024), 6 bytes:
  Original: 20 22 EF 00 C2 49    JSR $EF22 → far-call $49C2 (stop sound)
  Patched:  EA EA EA EA EA EA    6× NOP (harmless — sound stop is redundant)

Site 2 — ROM $10047 (logical $4047), 3 bytes:
  Original: A9 00 93             LDA #$00; TST... (first bytes of intro animation)
  Patched:  4C 62 41             JMP $4162 (skip intro → jump to menu)
```

**Result**: ✅ **Fully working** (CRC `5EBCA528`). Boots directly to the sound test menu with all text, tiles, and palette correctly displayed. The preserved init at `$402A–$4046` runs: sets flag `$90`, clears RAM, calls `$F2FE` (palette/font init), calls `$F38E` (palette/font init), calls `$F922` (enable VBLANK). Then `JMP $4162` enters the menu.

**Patched flow**:
```
$4005: JSR $F91E          — disable BG + sprites
$4008: JSR $F173          — init tables
$400B: TII $58F1→$2220    — copy 239 bytes to RAM
$4024: NOP ×6             — skip sound stop far-call (harmless)
$402A: LDA #$01; STA $90  — set flag
$402E: STZ $3000; TII     — clear 2303 bytes of RAM
$4038: JSR $F2FE          — palette/font init ★
$403F: JSR $F38E          — palette/font init ★
$4044: JSR $F922          — enable VBLANK IRQ ★
$4047: JMP $4162          — skip intro → menu entry
  ↓
$4162: JSR $EF22 → $49C2  — stop sound
$4168: JSR $4217           — draw menu (fade-out, VRAM setup, tile rendering)
$417D: JSR $F199           — fade-in
$418A: input loop           — SOUND XX menu running
```

#### Key Subroutines Reference

| Address | ROM Offset | Function | Notes |
|---------|-----------|----------|-------|
| `$F922` | `$01922` | VDC CR \|= `$0A` + CLI | Enable VBLANK+overflow → IRQ1 |
| `$F926` | `$01926` | VDC CR &= `$F0` | Disable all VDC IRQ sources |
| `$F91A` | `$0191A` | VDC CR \|= `$C0` | Enable BG + sprites |
| `$F91E` | `$0191E` | VDC CR &= `$3F` | Disable BG + sprites |
| `$F199` | `$01199` | Fade-in | Calls `$F922` + `$F91A` (enable VBLANK, BG, sprites) |
| `$F1B5` | `$011B5` | Fade-out | Needs VBLANK running; ends with `JMP $F91E` |
| `$F29B` | `$012A3` | VBLANK sync | `STZ $10; LDA $10; CMP #$01; BCC` spin loop |
| `$EB03` | `$00B03` | IRQ1 handler | Normal ISR: `INC $10`, scroll, `$4000`/`$C000` calls, RTI |
| `$EF22` | `$00F22` | Far-call | Reads 3 inline bytes: mode, addr_lo, addr_hi |
| `$EEFF` | `$00EFF` | set_mode(A) | Maps banks to MPR2–6 from table at `$FF80+Y` |

#### Notebook

The boot sequence disassembly and patch development are in `Gunhed-Disasm.ipynb`. Key cells:
- Boot sequence `$E000–$E095` with full annotations
- Mode mapper `$EEFF` and bank table dump
- VDC CR helpers `$F91A–$F955`
- IRQ1 handler `$EB03` full disassembly
- Bank `$08` entry `$4005` disassembly
- VBLANK wait analysis (`$F29B`, `$F199`, `$F1B5`)
