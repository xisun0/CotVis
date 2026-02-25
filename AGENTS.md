# AGENTS.md

## Purpose
Guidelines for human/agent contributors working in this repository.

## Commit Convention
Use Conventional Commits:

- `feat`: new user-facing capability
- `fix`: bug fix
- `docs`: documentation-only changes
- `refactor`: internal code restructuring without behavior change
- `chore`: maintenance tasks
- `test`: tests added/updated

Recommended scopes for this project:

- `build`: packaging/dependencies/tooling setup
- `cli`: command entrypoint, flags, terminal output behavior
- `asr`: speech backend integration (macOS Speech Framework)
- `context`: buffering, tokenization, top-terms computation
- `docs`: README/spec/troubleshooting docs
- `infra`: local workflow files (e.g., Makefile)
- `scaffold`: initial project structure/bootstrap

Commit format:

`<type>(<scope>): <short summary>`

Examples:

- `feat(asr): stream partial and final transcripts from macOS Speech`
- `feat(cli): add --no-jsonl switch for terminal output`
- `fix(context): prevent duplicate counting when final arrives`
- `docs(docs): add microphone permission troubleshooting`

## Repo Boundaries
- Keep `README.md` user-facing (setup/run/usage).
- Keep implementation details and contributor policy here in `AGENTS.md`.
- Do not introduce cloud ASR dependencies in MVP.
