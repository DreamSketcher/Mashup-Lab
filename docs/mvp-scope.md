# Mashup Lab MVP: scope and delivery

This document is the current project direction. It takes precedence over older
drafts wherever they make trusted infrastructure a prerequisite for rendering.
It is a product/implementation roadmap; the initial renderer is experimental.

## Goal

Build a local, AI-free musical mashup engine that turns a declarative project and
user-provided audio into a composition whose timing, processing parameters and
provenance can be inspected and reproduced. The project provides no AI-based
analysis or separation; it accepts source audio without asserting how it was
prepared. No audio files should be published without appropriate rights.

## Core pipeline

1. **Project and validation:** parse and validate the project, check source file
   identity and metadata, reject invalid or changed inputs. Do not modify source
   files. Source hashes identify bytes, not legal rights or authenticity.
2. **Planner:** calculate clip placement and processed duration in output frames
   using the existing rational timing model and validate the derived plan.
3. **Binding:** the simplest first implementation is to regenerate the plan
   from the validated project for each render, in the same invocation, and pass
   that plan directly to the renderer. This avoids accepting an unrelated stale
   plan; no saved sidecar or trusted build verifier is required. If saved plans
   are supported later, verify project/source identities and recompute or compare
   their complete geometry before use. Current `plan` JSON has no project hash;
   its independent validator does not prove correspondence to a project.
4. **Renderer:** use the verified source data and planned frame boundaries;
   do not recompute bars/beats independently. Apply explicitly specified,
   versioned processing and export PCM WAV. Select and test an audio backend
   rather than inventing one; capture its versions and options. Respect the
   [audio processing draft](audio-processing-specification.md), revising it
   explicitly if the selected backend cannot honor its semantics.
5. **Render manifest:** record project/source hashes, plan version, engine and
   dependency versions, processing/export parameters and output PCM identity.
   This provides provenance and comparison, not proof of authorship or a secure
   execution environment.

Validation and rendering should operate on the same project bytes and verified
source data where practical; report errors rather than silently accepting a
mismatch. Ordinary file/hash checks do not guarantee safety against a malicious
privileged actor or concurrent changes to mutable inputs. Decide and document
snapshot/locking behavior before claiming stronger guarantees; this MVP is not a
sandbox for hostile projects or a trusted-execution service.

## Reproducibility contract

The desired fixed-environment outcome is identical PCM on repeated renders of
identical verified inputs with identical settings, **only after demonstrated by
tests**. Record the environment and compare canonical PCM independently of WAV
metadata. Do not promise byte-identical output across CPUs, operating systems,
library versions or codecs without evidence. Test stable timing, audio length,
placement and repeat renders; add diagnostics for differing hashes/settings.
A successful plan or source-hash check alone does not prove identical audio or
musical quality. See the [reproducibility draft](determinism-reproducibility-specification.md).

## Delivery order

1. **Agree on the minimal end-to-end render contract.** Decide the initial audio
   formats, the exact backend and pinned build/settings, and which processing
   operations it can honor. Review dependencies and licenses.
2. **Implement a first vertical slice:** verified small WAV sources, existing
   plan positions, clipping/fades/mixing and WAV output. If stretch/pitch are not
   yet available, explicitly reject non-identity parameters instead of silently
   ignoring them. A narrow first slice is not yet the full MVP.
3. Add the specified independent time and pitch processing, resampling, error
   handling and output manifest. Ensure exact clip lengths and mixing semantics
   match the documented contract.
4. Test with generated legal fixtures: two short tracks, overlap, leading or
   intermediate silence, expected frame positions/lengths and invalid source
   hashes. Render twice in the same pinned environment and compare PCM hashes.
   Verify that project changes generate the appropriate new plan and that stale
   plans are not accepted if any persisted plan interface is introduced.
5. Iterate on usability and sound quality. GUI, automatic structure analysis,
   source separation, DAW import and arbitrary plug-ins remain outside MVP.

The first slice uses libsndfile/soundfile for decoding, NumPy for mixing and
Python wave for PCM output. It rejects non-48 kHz sources and non-identity
time/pitch transforms. These dependency ranges do not pin an environment.
A time/pitch backend and resampler remain to be selected.

## Explicitly outside MVP: trusted execution research

Do not make a local trust allowlist, OCI image attestation, trusted launcher,
Linux policy loader, update-lock protocol, crash consistency, anti-rollback
service or VM admission gate a condition for implementing or using this local
renderer. The earlier documents, experimental workflows and fail-closed
`capture_policy_snapshot()` scaffold remain in the repository as **optional,
non-MVP research**, not as security features or requirements for the engine.
They may be reconsidered separately if a concrete deployment and threat model
justify them. No claim of verified trust or production-grade isolation follows
from hashes, passing unit tests or these research artifacts.

## Current state

The YAML project validator, timeline planner and independent plan validator are
implemented. Separate manifest/policy parsers and Linux experiments also exist,
but are not prerequisites for the music MVP. A limited in-process renderer generates its own plan and verifies source bytes;
the full renderer and render manifest are not implemented. Review actual test/CI results
for the revision being used rather than treating a previous run as permanent.
