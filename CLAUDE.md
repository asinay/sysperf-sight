# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A web tool for extracting specific sections from InterSystems IRIS pButtons HTML performance reports. Users upload a pButtons file, select which sections to include, and download a filtered HTML file. Sensitive sections are pre-deselected with explanations. Selected sections get inline analysis (charts, insights) injected above their raw data.

## Environment

Always use the `venv` virtual environment — never global pip or python.

```bash
# First-time setup
python -m venv venv
./venv/Scripts/pip install -r requirements.txt

# Run the dev server
./venv/Scripts/uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

The app is then available at http://127.0.0.1:8000.

## Architecture

The app has three layers that must stay in sync:

**[pbuttons_parser.py](pbuttons_parser.py)** — Pure parsing logic, no web framework dependency.
- `parse_sections(html)` → `(header_html, [Section])`: splits the file into a header block (nav table + debug comment) and a list of `Section` dataclasses. Uses two regex patterns: one for `Configuration`/`Profile` which use `<div id="...">` (quoted), and one for all other sections which use `<div id=...>` (unquoted).
- `build_output(header_html, sections, selected_ids, analysis)` → `str`: iterates **all** sections — selected ones keep their full content, excluded ones show a placeholder. Injects `analysis[section_id]` HTML above each section's raw data block when present.
- `_make_excluded_html(content_html)`: strips all `<pre>…</pre>` blocks then inserts `_EXCLUDED_PLACEHOLDER` at the position of the first `<pre>`. The strip-then-insert order is important — do not replace-then-strip or the placeholder itself gets removed.
- `SENSITIVE_SECTIONS` dict maps section **titles** to human-readable reasons — drives UI warnings and default deselection.
- `SECTION_DESCRIPTIONS` dict maps section **titles** to one-line descriptions shown in the output sidebar.
- `SECTION_GROUPS` list defines sidebar nav groups using section **IDs** (not titles).
- `COLLAPSED_BY_DEFAULT` set of section **IDs** whose raw data panel starts collapsed.

**[app.py](app.py)** — FastAPI backend with two endpoints:
- `POST /upload` — accepts a multipart `.html` file, calls `parse_sections`, stores result in the in-memory `sessions` dict keyed by UUID, returns section metadata (id, title, sensitive flag, reason, time_filterable).
- `POST /export` — accepts `{session_id, selected_ids, output_filename, time_from, time_to}`, applies time filters, runs analyzers in parallel, calls `build_output`, returns the result as a file download.

Sessions are in-memory only — lost on server restart. The `uploads/` directory exists but files are not written there; only `outputs/` gets written.

**[static/index.html](static/index.html)** — Single-file vanilla JS frontend (no build step). Communicates with the backend via `fetch`. Key flow: drag-drop/select file → `POST /upload` → render section checklist → user toggles sections + optionally sets time range → `POST /export` → trigger browser download via blob URL. The file is never opened automatically after download.

## pButtons HTML format

The file uses `iso-8859-1` encoding. Section boundaries are `<hr size="4" noshade>` followed by a bold font tag containing a `<div id=SECTIONID>` anchor. The first two sections (Configuration, Profile) use quoted IDs (`<div id="Configuration">`) while all subsequent sections use unquoted IDs (`<div id=mgstat>`). Each section ends with a "Back to top" link before the next `<hr>`.

**Important key distinction across dicts:**
- `SENSITIVE_SECTIONS`, `SECTION_DESCRIPTIONS`, `TITLE_TIME_FILTERS` — keyed by section **title** (the heading text, e.g. `"sar -d"`)
- `SECTION_ANALYZERS`, `SECTION_GROUPS`, `COLLAPSED_BY_DEFAULT` — keyed by section **ID** (the div id value, e.g. `"sar-d"`)

When adding a new section, update both the title-keyed and ID-keyed dicts as appropriate.

## Sections reference

### Common to Windows and Linux

| Title | Section ID | Sensitive | Analyzer | Time-filterable | Notes |
|---|---|---|---|---|---|
| Configuration | Configuration | ✓ | — | — | quoted div id |
| Profile | Profile | ✓ | — | — | quoted div id |
| IRIS ALL | IRISALL | ✓ | — | — | |
| License | License | ✓ | — | — | |
| CPF file | CPFfile | ✓ | — | — | collapsed by default |
| mgstat | mgstat | — | ✓ | ✓ | 24-hour CSV timestamps |
| %SS | %SS | — | ✓ | — | per-process snapshots |
| irisstat -c1 | irisstat-c1 | — | — | — | collapsed by default |
| irisstat -D | irisstat-D | — | — | — | collapsed by default |
| irisstat -R | irisstat-R | — | — | — | collapsed by default |

### Linux-only

| Title | Section ID | Sensitive | Analyzer | Time-filterable | Notes |
|---|---|---|---|---|---|
| Linux info | Linuxinfo | — | — | — | |
| cpu | cpu | — | ✓ | — | |
| ipcs | ipcs | — | — | — | |
| lsblk | lsblk | — | — | — | |
| mount | mount | — | — | — | |
| df -m | df-m | — | — | — | |
| ifconfig | ifconfig | — | — | — | |
| sysctl -a | sysctl-a | — | — | — | |
| ps | ps | — | — | — | |
| vmstat | vmstat | — | — | — | |
| sar -u | sar-u | — | — | ✓ | AM/PM timestamps on some locales |
| free | free | — | — | — | |
| iostat | iostat | — | ✓ | ✓ | AM/PM timestamps on some locales |
| sar -d | sar-d | — | ✓ | ✓ | AM/PM timestamps on some locales |

### Windows-only

| Title | Section ID | Sensitive | Analyzer | Time-filterable | Notes |
|---|---|---|---|---|---|
| Windows info | Windowsinfo | ✓ | ✓ | — | |
| tasklist | tasklist | ✓ | ✓ | — | collapsed by default |
| perfmon | perfmon | — | — | — | collapsed by default |

## Time filter system

**[analyzers/time_filter.py](analyzers/time_filter.py)** — filter functions keyed by section **title** in `TITLE_TIME_FILTERS`.

- UI sends `time_from` / `time_to` as `HH:MM` 24-hour strings from plain `<input type="text">` fields with auto-formatting (`timeInput` / `timeBlur` JS helpers). Values are persisted to `localStorage` and restored on page load. Clear button wipes both fields and storage.
- `_parse_hhmm(s)` accepts `HH:MM` only — never AM/PM.
- `_in_range(t, lo, hi)` supports open-ended ranges (one bound is `None`) and midnight-crossing ranges (when `lo > hi`).
- `filter_mgstat` — matches CSV rows by `MM/DD/YYYY, HH:MM:SS` at the start of each line. mgstat always uses 24-hour timestamps.
- `filter_iostat` — groups lines into timestamp blocks; each block starts with a standalone `MM/DD/YYYY HH:MM:SS [AM|PM]` line. Parses with `strptime` trying `%I:%M:%S %p` then `%H:%M:%S`.
- `filter_sar` — filters line-by-line using `_SAR_DATA_RE` (verbose regex with named group `(?P<ts>...)` that handles optional date prefix and optional AM/PM suffix). **Must use `m.group('ts')` not `m.group(1)`** — the named group is not group 1 in the verbose regex. `_parse_sar_ts()` detects AM/PM presence with `re.search(r'\b[AP]M\b')` and uses `strptime('%I:%M:%S %p')` for 12-hour or `strptime('%H:%M:%S')` for 24-hour. Real Linux sar -d output uses `HH:MM:SS AM/PM` format (e.g. `03:45:09 PM`) — always parse with strptime, never manual arithmetic.

**Critical AM/PM rule**: never convert AM/PM timestamps by hand (e.g. `h + 12`). Always use `strptime` with `%I:%M:%S %p`. Manual arithmetic silently fails on edge cases like `12:00 AM` (midnight) and was the root cause of the filter bug where `03:45 PM` was incorrectly matched by a `03:45` filter.

When adding a new time-filterable section, add a `filter_*` function and register it in `TITLE_TIME_FILTERS` using the section **title**. Do not use the section ID here — titles are more stable for sar/vmstat sections whose div ids vary across pButtons versions.

## Analyzer system

**[analyzers/__init__.py](analyzers/__init__.py)** — `SECTION_ANALYZERS` maps section **ID** → `async analyze(section_text) -> str`.

Each analyzer module (`analyzers/*.py`) exposes an `async analyze(section_text: str) -> str` that:
1. Parses the plain text extracted from the section's `<pre>` block(s).
2. Returns an HTML fragment (charts + insight flags) to inject above the raw data, or `''` if the section can't be parsed.

Current analyzers:

| Section ID | Module | What it produces |
|---|---|---|
| Windowsinfo | windows_info.py | OS/hardware summary cards |
| tasklist | tasklist.py | Top processes by memory |
| mgstat | mgstat.py | 4-row × 2-col chart grid: Glorefs, PhyRds/Wrs, Jrnwrts+WDQ, Rourefs, GblSz, BytSnt/Rcd, Gloupds, Jrnwrts (dedicated); stat cards; insights |
| iostat | iostat.py | %util, CPU iowait, IOPS, throughput, latency charts; insights |
| cpu | cpu.py | CPU topology summary |
| %SS | ss.py | Process type breakdown, TCP trend, top-CPU/Glob tables, processes-per-namespace table, top-5-routines-by-concurrent-count table; insights |
| sar-d | sar_d.py | %util, tps, throughput, r/w latency, queue depth charts; per-device summary table with latency baselines; insights |

### Shared UI patterns

`_flag(level, text)` — renders a coloured insight pill. Levels: `'red'`, `'amber'`, `'info'`, `'green'`.

`_stat(label, value, unit)` — renders a summary stat card.

Charts use Plotly (loaded from CDN in the output HTML). Call `fig.to_html(full_html=False, include_plotlyjs=False, ...)` — the CDN script tag is already in the output template.

### mgstat column names (normalised after CSV parse)

Key columns: `Glorefs`, `Gloupds`, `PhyRds`, `PhyWrs`, `Jrnwrts`, `WDQsz`, `Rourefs`, `RemGrefs`, `RemRrefs`, `GblSz`, `BDBSz`, `BytSnt`, `BytRcd`, `Rdratio`.

### %SS snapshot format

Each snapshot starts with `InterSystems IRIS System Status: <time>`. Fixed column positions (0-based): pid=0–9, device=10–21, ns=22–36, routine=37–end (until cpu,glob numbers). CPU and Glob values are **cumulative since process start** — the analyzer computes deltas between consecutive snapshots for rates. Routine field: read from col 37 to the start of the cpu,glob pair on the same line (not hard-capped at col 53) to avoid truncating long class method names like `EnsLib.TCP.InboundAdapter`.

### sar -d column variations

Old sysstat: `tps rd_sec/s wr_sec/s avgrq-sz avgqu-sz await svctm %util` — `rd_sec/s`/`wr_sec/s` are 512-byte sectors, divided by 2 to get kB/s.
New sysstat: `tps rkB/s wkB/s areq-sz aqu-sz await r_await w_await svctm %util`.
The analyzer handles both formats transparently via `col_map`.

## .gitignore

`/*.html` (root-level only) excludes pButtons data files while keeping `static/index.html` tracked. Never broaden this to `**/*.html`.

## Reusable skill

A global Claude Code slash command `/iris-report-parser` at `~/.claude/commands/iris-report-parser.md` captures the full recipe for building similar tools for other InterSystems IRIS HTML reports.
