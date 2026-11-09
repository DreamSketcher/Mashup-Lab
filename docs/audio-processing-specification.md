# Audio Processing Specification — draft v0.1

Status: draft contract. An experimental identity-transform, 48 kHz slice is
implemented; resampling, time stretch and pitch shift are not. See
[scope and implementation status](mvp-scope.md).
See [project format](project-format-specification.md) and
[reproducibility](determinism-reproducibility-specification.md). The project
specifies desired clip properties; this document fixes their evaluation order.

## Processing graph

For each clip, in project list order:

1. Verify and decode the selected source WAV; extract its native-frame half-open
   range. Original files are never modified.
2. Resample to 48 kHz using the pinned resampler and settings of the rendering
   environment. Convert mono to stereo by copying its signal to both channels;
   preserve stereo channel order. No automatic loudness normalization.
3. Apply duration scaling, then pitch shifting as two ordered operations using
   the pinned offline backend(s) and explicit options. A ratio of 1 bypasses
   duration scaling; a shift of 0 bypasses pitch shifting. Pitch shifting must
   preserve duration. Backend delay and padding must be compensated by the
   implementation, and the final output normalized to the exact length below
   (trim end or pad silence at end if needed). The profile must identify both
   operations separately; a combined operation is not equivalent to this order.
4. Apply gain and pan, then fades as defined below; place on the output timeline.
   Sum overlapping clips in list order in IEEE 754 binary64 precision. No random
   choice or automatic musical decisions are permitted.
5. Apply the master peak policy, quantize, and write WAV.

Non-finite samples (NaN or infinity) at any processing stage are a render
error, not silence or clipped values. Report the stage and clip where possible.

The exact output length of a processed clip in frames is
`round_half_up((end_frame - start_frame) * timeline_rate / source_rate * duration_ratio)`,
with exact rational arithmetic and ties upward. A zero-frame result is invalid.
This target length applies irrespective of intermediate resampler rounding.

## Gain, pan and fades

Gain is `10^(gain_db / 20)`. Pan is a **balance**, not constant-power pan:
left multiplier is `1 - max(pan, 0)` and right multiplier is `1 + min(pan, 0)`.
At center both are 1; for a mono source centered output has the same amplitude
in each channel as the source. A channel is attenuated, not cross-mixed.

A fade of N frames uses multiplier `(i + 1) / N` for output clip frame i in
`[0, N)`; N=0 means no fade. Fade-out is the same envelope reversed over the
last N frames. Where fades overlap, multiply both envelopes. Fades are applied
after duration processing, before placement. These definitions avoid ambiguity
at N=1; endpoints intentionally do not reach zero at the boundary.

## Master and export

After summing, calculate the absolute peak across both channels. If peak > 1,
scale the entire mix by `1 / peak`; otherwise leave it unchanged. Report the
original peak and applied scale. This is deterministic peak protection, **not**
a limiter or loudness mastering; a single transient can attenuate the entire
mix. Do not silently apply compression or normalization beyond this policy.

Export signed integer PCM WAV, 16 or 24 bits as specified in the project, with
no dithering. Quantization: scale by `2^(bit_depth - 1)`, round to nearest integer
with ties away from zero, then clamp to the signed integer range. WAV metadata
must not contain timestamps or other changing values. PCM comparison excludes
container metadata, as described in the reproducibility specification.

## Implementation and limitations

The full MVP still needs resampler and time/pitch backend selection, precise
settings, floating-point execution mode and pinned library versions.
The backend must support independent duration and pitch changes and must be
reviewed for licensing and offline use. Render is invalid if a required backend
is unavailable; no silent fallback. Time stretching and pitch shifting can create
artifacts. No source separation, beat detection, note correction or guarantee of
musical compatibility is part of MVP. Strictly AI-free describes the tools
provided by the project, not a verifiable claim about how user files were made.
