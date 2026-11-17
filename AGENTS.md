# Working on this repository

These are instructions for an engineer or an LLM coding agent who continues this work. Read them before you touch the TV.

## Start here

1. [README.md](README.md): the result, the direction, and where everything lives.
2. [docs/ROADMAP.md](docs/ROADMAP.md): what to do next.
3. [docs/FINDINGS.md](docs/FINDINGS.md): facts about the platform and every engine. Search it before you investigate anything. Most traps on this TV are already described there, with the fix or the reason it is a dead end.
4. [docs/BENCHMARKS.md](docs/BENCHMARKS.md): how to measure, and the raw file behind every number.
5. [docs/SOURCES.md](docs/SOURCES.md): the test device and pinned versions.

## The TV

- **Access.** Every tool reaches the TV over telnet as root: `bench/tvtelnet.py $TV_HOST '<command>'`.
  - Set `TV_HOST`. Scripts fail without it.
  - A telnet session that launches an app may never return. Use short timeouts and a separate session for launching.
- **Free space.** `/media/developer` is about 2.7 GB in total. Check `df -h /media/developer` before an install. A full disk once left an empty binary in place of the old one.
- **Debug ports.**
  - Open DevTools and inspector ports only for the duration of a run.
  - Bind them to the TV's LAN IP or to 127.0.0.1, never 0.0.0.0. They have no authentication.
  - Close them afterwards and confirm with `nc -z $TV_HOST <port>`.
- **One user at a time.** Two benchmark runs, or a person with the remote, close each other's browsers. Benchmark records carry timestamps, so exclude overlap windows and rerun.
- **Destructive actions.** Deleting files, uninstalling apps and replacing installed libraries need a confirmation from the TV's owner. Keep the installed state described in [docs/ARTIFACTS.md](docs/ARTIFACTS.md) up to date.
- **LG proprietary libraries** (`libNDL*`, CDMs, `libumedia*`) may be read from the TV for linking and analysis. They must never be committed.

## Measuring

- Use `bench/harness_run.py` for anything compared across browsers, and `bench/bench.py` for WPE A/B runs.
- Close preloaded apps first. The harness does this itself.
- Keep the TV screensaver from starting. Drop runs that overlapped it.
- Do not trust per-frame layout or paint costs from an attached inspector or DevTools Timeline. Confirm them without it, with `perf/perfsym.py` or with beacons.
- Every number that goes into a document needs a raw file in the repository, or an explicit note that the raw output was not kept.

## Repository conventions

- **Commit messages** follow Conventional Commits: `type(area): description`.
- **Paths and addresses.** Scripts resolve paths from their own location and read the TV address from `TV_HOST`. Never commit a home path, a private IP or personal data.
- **Not versioned:** binaries, upstream clones, LG libraries and build logs. See `.gitignore`. Record versions and commits in [docs/SOURCES.md](docs/SOURCES.md) instead.
- **Third-party material.** When you add some, add its license to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- **Frozen directories** (`buildroot/`, `buildroot64/`, `bridge64/`, `cr120/`) each have a `STATUS.md`. Update it if you revive one.
- **Facts.** Record a finding in FINDINGS.md when you make it, dead ends included, with the date and the reason.
