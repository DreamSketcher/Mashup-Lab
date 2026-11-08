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

## Proposed engine specifications

The following drafts explore a deterministic, AI-free audio processing engine.
They are design proposals, not features currently implemented in this repository:

- [Project format](docs/project-format-specification.md)
- [Audio processing](docs/audio-processing-specification.md)
- [Determinism and reproducibility](docs/determinism-reproducibility-specification.md)
- [Project–plan binding (proposal; not implemented)](docs/project-plan-binding-specification.md)
- [Planner build manifest (proposal; not implemented)](docs/planner-build-manifest-specification.md)
- [Planner build manifest test contract](docs/planner-build-manifest-test-contract.md)
- [Planner trust and execution (proposal; not implemented)](docs/planner-trust-and-execution-specification.md)

## Reference timeline model (experimental)

The Python implementation parses the draft YAML format, validates project
structure and local PCM WAV identity/metadata, and computes exact timeline
frames, pairwise half-open overlap intervals, and total duration. It does not
process or render audio, check a render backend, or prove audio determinism.
Python 3.11+ is required.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m mashup validate project.yaml
.venv/bin/python -m mashup plan project.yaml > plan.json
.venv/bin/python -m mashup validate-plan plan.json
.venv/bin/python -m unittest discover -s tests -v
```

`plan` prints versioned JSON with named clip and overlap boundaries and
durations in timeline frames; see [the plan contract](docs/timeline-plan-specification.md). Project paths are relative to the project file;
the hash in the specification example must be replaced with the actual source
file hash and metadata. Render-environment checks will be added with a renderer.
