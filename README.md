# Mashup Lab

**A community-driven space for musical experiments and creative collaborations.**

Mashup Lab is an open playground for experimenting with music by combining different tracks, genres, vocals, instrumentals, and musical ideas.

The project aims to bring together people who enjoy exploring unexpected musical combinations, sharing experiments, suggesting mashup ideas, and collaborating on creative projects.

## What is this about?

- **Mashup Experiments** — combine different songs into something new.
- **Track Pairing Ideas** — suggest tracks that could work surprisingly well together.
- **Community Requests** — propose mashups you'd like to hear.
- **Collaborations** — find people interested in working on the same musical idea.
- **Creative Exploration** — experiment with genres, tempos, vocals, instrumentals, and arrangements.

## How to Participate

You don't need to be a professional music producer to participate.

You can:
- Share your own mashup experiments.
- Suggest two or more tracks for a potential mashup.
- Create a request describing a musical idea.
- Collaborate with other participants.
- Discuss techniques, arrangements, and creative approaches.

## Community Requests

Have an idea for an interesting combination?

Open a GitHub Issue and describe:
- The tracks you'd like to combine.
- Your idea of how they could work together.
- Any particular sections, vocals, or instrumental elements you'd like to hear.

Requests are suggestions for creative experiments, not guaranteed commissions.

## Community Guidelines

- Respect other creators and contributors.
- Credit original artists and sources.
- Keep discussions constructive and welcoming.
- Don't upload copyrighted audio without appropriate authorization.
- Clearly distinguish original material from third-party material.

## Disclaimer

Mashup Lab is a non-commercial community experiment focused on musical creativity and collaboration.

All original recordings, compositions, and other third-party materials remain the property of their respective rights holders.

This project does not claim ownership of third-party material or imply endorsement by its original creators.

---

**Experiment. Combine. Create.**

## Mashup engine MVP

The focus is a local, deterministic and reproducible audio workflow: validate a
project and its sources, calculate a timeline, render the audio, and record the
parameters and output identity. See the [MVP scope and roadmap](docs/mvp-scope.md).
An experimental limited renderer and in-process plan binding are implemented;
the full renderer and render manifest are **not implemented**.

Core drafts:

- [Project format](docs/project-format-specification.md)
- [Timeline plan](docs/timeline-plan-specification.md)
- [Audio processing](docs/audio-processing-specification.md)
- [Determinism and reproducibility](docs/determinism-reproducibility-specification.md)

The earlier Linux trust, OCI admission, policy loading and anti-rollback designs
are retained as **optional research outside the MVP**. They are not a prerequisite
for rendering; their previous requirements apply only to that proposed research,
not to the local music engine. The current [project–plan binding proposal](docs/project-plan-binding-specification.md)
also contains this older trust-oriented design; for MVP use the simpler binding
direction in the scope document. None of those documents imply that trusted
execution is implemented or that hashes authenticate the source of a file.

## Reference timeline model (experimental)

The Python implementation parses the draft YAML format, validates project
structure and local PCM WAV identity/metadata, and computes exact timeline
frames, pairwise half-open overlap intervals, and total duration. An experimental
in-memory renderer supports 48 kHz PCM WAV sources, identity duration/pitch,
clip gain, balance, fades, ordered mixing, peak protection and 16/24-bit PCM
export. It rejects resampling and non-identity time/pitch transforms. `soundfile`
(libsndfile) decodes; NumPy mixes; Python's `wave` writes the explicitly
quantized PCM. The output path must not exist. Memory usage scales with the
entire sources and output, so this is for small projects. It is not a hardened
hostile-input boundary and cross-environment bit identity is not established.
Python 3.11+ is required.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m mashup validate project.yaml
.venv/bin/python -m mashup plan project.yaml > plan.json
.venv/bin/python -m mashup validate-plan plan.json
.venv/bin/python -m mashup render project.yaml -o output.wav
.venv/bin/python -m unittest discover -s tests -v
```

`plan` prints versioned JSON with named clip and overlap boundaries and
durations in timeline frames; see [the plan contract](docs/timeline-plan-specification.md). Project paths are relative to the project file;
the hash in the specification example must be replaced with the actual source
file hash and metadata. `render` prints the output PCM SHA-256, peak and scale;
this diagnostic is not a render manifest. Pin the full environment when comparing
results; the dependency ranges alone do not pin versions.

Optional research commands `inspect-manifest` and `compare-policy` are separate
from the music MVP. `inspect-manifest` validates UTF-8 JSON structure and computes the SHA-256 and
planner ID from the exact file bytes. It does not read an image, authorize a
planner, verify a build, check isolation, or run any code. Its `trust` and
`execution` fields are explicitly `not_checked`; the sample manifest contains
fabricated artifact digests.

`compare-policy` checks a caller-supplied policy's schema and compares it to a
manifest's claimed identity, image digest and platform. It returns `MATCH`,
`NOT_LISTED`, `REVOKED`, `MISMATCH` or `UNAVAILABLE` (exit 0, 1 or 2). A
`MATCH` is **not admission or proof of trust**: policy ownership/protection,
actual image contents, runtime and isolation are not checked. The policy parser
shares the manifest JSON limits and permits at most 1,024 entries.

The Linux trusted policy snapshot adapter is a fail-closed scaffold only: it
never reads a policy or returns a trusted snapshot. No Linux configuration is
currently supported for trusted policy loading or execution admission.

## Continuous integration

The CI workflow runs the unit tests and script syntax checks on Python 3.11,
3.12 and 3.13 for pushes and pull requests. It does not run the privileged Linux
policy experiments; those remain in the separate manual research workflow.

## Windows launcher

On Windows 10/11, run `Mashup-Lab.bat` to check or prepare the local Python
virtual environment and use the CLI without manual activation. See the
[Windows guide](docs/windows-launcher.md) for setup, render limitations and
troubleshooting. Windows and Russian-locale testing status is documented there
and in the Windows test workflow; it is not implied by Linux test results.

## Audio architecture research

The [audio-engine audit](docs/audio-engine-research-audit.md) and [architecture
recommendations](docs/audio-engine-architecture-recommendations.md) are proposals
for review, not implemented features or finalized backend choices.

## License status

**License: undecided.** No open-source license has been granted for the project
in this repository. See the [licensing and distribution research](docs/licensing-distribution-research.md);
third-party dependencies retain their own licenses.
