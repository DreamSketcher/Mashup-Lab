# Determinism and Reproducibility Specification — draft v0.1

Status: proposed contract, not a tested guarantee. See the
[project format](project-format-specification.md) and
[audio processing](audio-processing-specification.md) specifications.

## Contract levels

1. **Project semantics:** the same valid project and verified sources describe
   the same clip selection, placement, parameters and operation order.
2. **Fixed-environment audio:** identical decoded PCM output is a target only
   for a documented, pinned environment after tests establish it. Compare PCM
   samples and their format, not just container bytes.
3. **Cross-platform:** identical musical decisions are intended; numerical and
   audible differences may occur. No quantitative equivalence or bit identity
   is promised without measurements and a defined tolerance.

A deterministic algorithm does not by itself guarantee identical output across
CPUs, compiler options, floating-point libraries or thread schedules. Fixed
seeds alone would not solve those differences. Any random processing or dither
is excluded from MVP.

## Render environment profile

Before an audio renderer can claim fixed-environment reproducibility, it must
publish a versioned, immutable profile identifying engine version and build ID
separately from each audio algorithm/backend and version. It also fixes stretch
and pitch options, resampler algorithm/version/filter, binary64 mixing and its
execution mode, sum order, OS, CPU architecture, runtime and library versions,
and thread count and scheduling policy. The profile identifies the actual build
artifacts (e.g. hashes), not just informal version labels. A CLI-only engine
change need not change the audio algorithm version, but the engine build remains
recorded. There is no approved profile yet; a claimed profile must be tested.

## Render manifest

A render produces a separate machine-readable manifest, without changing the
project. The implementation must choose and document a schema before release.
It contains at least:

- project file SHA-256 and schema version; source file hashes and validated
  decoded sample rates, channels and frame counts;
- engine version/build identifier, backend and dependency versions, backend
  options, resampler and settings, processing order, numeric precision;
- OS, architecture, relevant runtime/build information and thread settings;
- output sample rate, channels, bit depth, frame count, export settings, peak
  and master scale; SHA-256 of a canonical PCM byte stream.

The canonical hash input is interleaved signed PCM frames, left then right,
16- or 24-bit little-endian two's complement, without WAV headers. The manifest
also records format and frame count because bytes alone do not identify them.
Output WAV file SHA-256 may additionally be reported, but is not a substitute
for the PCM hash. A manifest documents provenance; it cannot guarantee that an
environment can be reconstructed unless the exact artifacts remain available.

## Verification and diagnostics

In a pinned environment, render a test project twice and compare format, frame
count and PCM hash. On mismatch, report differing source hashes, project hash,
versions/settings and output metadata, plus the first differing frame/channel
when both PCM streams are available. Such comparisons can identify potential
causes but cannot always prove why samples differ. Tests must include at least
silence, a mono clip, stereo overlap, resampling, nontrivial stretch/pitch,
fades, peak protection and a fractional timeline-frame boundary. Include
missing or mismatched source and invalid-project failures. Add independently
specified reference vectors for timing and quantization so repeating the same
bug twice is not considered correctness.

When supported, cross-platform comparison should report maximum absolute sample
difference and RMS difference in normalized units; choose and publish a
justified tolerance before claiming a measured level of equivalence. Codec
versions, metadata, output path and machine-specific details may affect file
hashes; those are distinct from PCM equality.

## Cache and security

Caching is optional and not required for MVP. If added, cache keys must include
source identity, source range, all effective operation parameters, algorithm and
backend versions, all profile settings and artifact identities that may affect
the cached computation, including numeric mode, resampler, architecture and
thread policy. Until that dependency set is proven, include the entire immutable
render environment profile and invalidate on any profile change. A cache hit must never
bypass source verification. Paths in a project are untrusted input and follow
the restrictions in the project format. Resource limits and safe WAV parsing
must be considered before accepting untrusted projects in a service.
