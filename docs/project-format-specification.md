# Project Format Specification — draft v0.1

Status: design proposal, not an implemented or stable format. This document, the
[processing specification](audio-processing-specification.md), and the
[reproducibility specification](determinism-reproducibility-specification.md)
define the proposed MVP together. Conflicts must be resolved before release.

## Scope and conventions

A project is a UTF-8 YAML document describing a composition, not a sequence of
imperative commands. No embedded code, remote URLs, plugins, or implicit source
search are supported. The MVP accepts local uncompressed signed integer PCM WAV sources (16, 24 or
32 bits per sample; standard PCM WAV, not extensible WAV) and
renders stereo PCM WAV. Unknown fields, duplicate YAML keys, unsupported schema
versions and invalid types are errors. YAML aliases and custom tags are forbidden.
Values are finite. Numeric tokens use ordinary decimal notation: integers or
decimals with a decimal point; no octal, sexagesimal, underscores, NaN or
infinity. Decimal tokens are constructed directly as Decimal from the original
scalar text, never via binary floating point, then converted to exact rationals
for timing. Scientific notation, if used, must include a decimal point and a
signed exponent (for example `1.0e+2`). Quoted strings are not numbers.

Paths are relative to the project file's directory. Absolute paths, URLs and
paths resolving outside that directory (including through symlinks) are rejected.
A renderer must not overwrite the project or any source file. The project file
is the authority for edit decisions; analysis results do not silently modify it.

## Example

```yaml
schema_version: "0.1"
timeline:
  bpm: 125
  time_signature: [4, 4]
  ppq: 960
  sample_rate: 48000
sources:
  - id: vocal
    path: sources/vocal.wav
    sha256: "<64 lowercase hexadecimal characters>"
    sample_rate: 48000
    channels: 1
    frames: 960000
clips:
  - id: verse
    source_id: vocal
    source_range: {start_frame: 48000, end_frame: 576000}
    position: {bar: 16, beat: 1, tick: 0}
    processing:
      duration_ratio: 0.96
      pitch_semitones: 2
      gain_db: -6
      pan: 0
      fade_in_frames: 240
      fade_out_frames: 240
render:
  bit_depth: 24
```

The hash above is a placeholder; a real project must contain the actual SHA-256
of the complete source file. One frame contains one sample per channel. Source
ranges use the source file's native sample rate, **not** the timeline rate.

## Fields and validation

All fields shown are required. IDs are unique within their respective lists,
nonempty ASCII strings matching `[A-Za-z0-9_-]+`. Lists preserve their order;
clip order also defines mixing order. Sources may be reused by multiple clips.
The source SHA-256 is 64 lowercase hexadecimal characters. The listed rate,
channels and frame count must match the decoded WAV metadata: a mismatch or
missing file is an error. MVP sources are mono or stereo, with positive frame
count and sample rate. Every source reference must resolve to one source.

- `timeline.bpm`: positive finite decimal; constant throughout the project.
  BPM counts quarter notes per minute, regardless of time signature.
- `time_signature`: `[numerator, denominator]`, positive integers; denominator
  must be one of 1, 2, 4, 8, 16. One beat in a position is one denominator
  note. `ppq` is fixed at 960 ticks per quarter note in v0.1.
- `sample_rate`: integer 48000 for MVP. Output is stereo.
- `source_range`: zero-based half-open frame interval `[start_frame, end_frame)`;
  integers satisfying `0 <= start_frame < end_frame <= source.frames`.
- `position`: one-based bar and beat; `1 <= beat <= numerator`, bar >= 1,
  `0 <= tick < 960 * 4 / denominator`. Ticks are zero-based within the beat.
- `duration_ratio`: positive decimal, output duration divided by input duration,
  independent of pitch: 0.96 is 4% shorter and 1.04 is 4% longer, not a
  speed multiplier. Thus aligning a constant 120 BPM source to 125 BPM
  uses 0.96. It is explicit; no tempo or beat grid is inferred. Range 0.5–2
  inclusive in MVP.
- `pitch_semitones`: integer in [-12, 12]; independent of duration.
- `gain_db`: finite decimal in [-120, 24]. `pan`: decimal in [-1, 1], with
  -1 left, 0 center and 1 right. See processing specification for semantics.
- Fades are nonnegative integer output frames, each no longer than the processed
  clip. Their overlap is allowed and their gain envelopes multiply.
- `bit_depth`: 16 or 24 integer PCM. The export sample rate is the timeline rate.

Empty clip lists are invalid. Clips may overlap; silence between clips is valid.
The render begins at frame 0 and ends at the greatest clip end; no implicit
trailing silence or effect tail is added.

## Timing

For position `(bar, beat, tick)`, calculate integer quarter-note ticks:

```
ticks = ((bar - 1) * numerator + (beat - 1)) * (960 * 4 / denominator) + tick
frame = round_half_up(ticks * 60 * sample_rate / (960 * bpm))
```

All arithmetic in this calculation is exact rational arithmetic until rounding.
The rule is nearest integer, with exact halves rounded upward. Processed clip
length is specified in the processing document. Source trimming occurs before
resampling and stretching. The source frame at the beginning of the range is
aligned to the specified timeline frame; no onset or downbeat is inferred.

## Compatibility and evolution

Validation checks syntax, semantics, source identity and required processing
backend before rendering. Hash mismatches are errors by default, even when
metadata matches. To use another version, explicitly create a revised project
with updated metadata/hash and review affected clip boundaries and alignment;
there is no silent override in MVP. A matching hash establishes file identity,
not ownership or permission. Source paths and hashes may reveal information;
project sharing does not itself grant rights to the recordings.

A future schema must have an explicit version and migrations. A migration must
not silently change the semantics of an existing project. A processing backend
change can change audio even if the declarative intent is unchanged; it must be
recorded and is not interchangeable for exact reproduction.
