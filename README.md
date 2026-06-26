# pButtons Parser

A web tool for extracting specific sections from InterSystems IRIS pButtons HTML performance reports. Upload a pButtons file, choose which sections to keep, and download a clean filtered copy — without sharing data you didn't intend to.

## Features

- **100% local processing — your file never leaves your machine.** The tool runs entirely on your own computer. All parsing is done in-process using Python's standard library (`re`). The three dependencies (FastAPI, Uvicorn, python-multipart) are server/parsing primitives that make no outbound network calls. The server binds to `127.0.0.1` (loopback only), so even the traffic between your browser and the tool stays within your machine's network stack. No data is sent to any cloud service or AI.
- Drag-and-drop upload of pButtons `.html` files
- All sections detected and listed automatically
- Sensitive sections (license keys, usernames, file paths, machine details) are flagged and **pre-deselected** with explanations
- One-click "Select non-sensitive only" filter
- Excluded sections keep their header and nav anchor — replaced with a clearly marked placeholder so the file remains well-formed and shareable
- Optional time range filter to slice time-series sections (mgstat, vmstat, sar, iostat)
- **Three export modes** for different sharing needs:
  - **Full report** — charts, insights, raw data, cross-section synthesis, and sensitive-data banners
  - **Charts + Raw** — charts plus raw data (collapsed); no insights or synthesis
  - **Charts only** — charts only; no raw data, no insights; excluded sections hidden entirely
- Output filename auto-populated from the source file name + upload timestamp

## Running with Docker (recommended)

Requires [Docker](https://docs.docker.com/get-docker/).

```bash
docker run -p 8765:8765 --name pbuttons-parser ghcr.io/asinay/pbuttons-parser
```

If port 8765 is already in use, pick any free port (e.g. 8080):

```bash
docker run -p 8080:8765 --name pbuttons-parser ghcr.io/asinay/pbuttons-parser
```

Or build and run locally:

```bash
docker build -t pbuttons-parser .
docker run -p 8765:8765 --name pbuttons-parser pbuttons-parser
```

Using Docker Compose:

```bash
docker compose up
```

Open http://localhost:8765 in your browser.

## Setup (without Docker)

Requires Python 3.9+.

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

```bash
./venv/Scripts/uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 in your browser.

## Sensitive sections

The following sections are flagged and deselected by default:

| Section | Why it's sensitive |
|---|---|
| Configuration | Instance name, machine name, GUID, license number |
| Profile | Username/email of report author, directory paths |
| License | License type, user counts, feature codes |
| CPF file | Full filesystem paths for all databases and namespaces |
| IRIS ALL | All IRIS instances on the machine with ports and directories |
| Windows info | OS, hardware, and network configuration details |
| tasklist | All running processes on the machine |

## Analyzers

Selected sections with an analyzer get inline charts and insights injected above their raw data:

| Section | What it produces |
|---|---|
| mgstat | Global refs, physical I/O, journal writes, WD phase, routine cache, network charts; stat cards; NSeize/ASeize contention and WD saturation insights |
| %SS | Process type breakdown, TCP trend, top-CPU/Glob tables, namespace and top-routine breakdowns; insights |
| vmstat | Run queue, swap I/O, CPU breakdown, block I/O charts; stat cards; insights |
| sar -u | Stacked CPU area chart (user/sys/iowait/steal + idle); stat cards; saturation/steal/iowait insights |
| sar -d | %util, tps, throughput, r/w latency, queue depth charts; per-device summary table; insights |
| iostat | %util, CPU iowait, IOPS, throughput, latency charts; insights |
| free | RAM usage, adjusted free RAM trend, swap used charts; stat cards; memory pressure insights |
| irisstat -D | Lock contention summary and per-second rates tables (sortable); block collision insights |
| irisstat -R | Routine buffer pool: in-use routines, top packages by buffer count, type breakdown; class LRU eviction insights |
| sysctl -a | Compliance table for IRIS-relevant kernel parameters (sortable); red/amber/green status; tuning insights |
| ps | Process snapshot: RSS by user chart, top-15 by RSS table, IRIS job-type breakdown; D-state insights |
| df -m | Disk usage stacked bar chart; full filesystem table with colour-coded Use% badge; capacity insights |
| mount | Local and network filesystem tables (sortable); soft-mount and NFS sync insights |
| cpu | CPU topology summary cards |
| Windows info | OS/hardware summary cards |
| tasklist | Top processes by memory |
| perfmon | CPU utilization, processor queue, available memory, paging, disk IOPS/throughput/latency, network throughput charts; insights |
| CPF file | Database configuration, namespace mappings, and key parameter summary |

## Project structure

```
app.py                  FastAPI backend (upload + export endpoints)
pbuttons_parser.py      HTML parsing and section reconstruction logic
static/index.html       Single-page frontend (no build step)
analyzers/              Per-section analysis modules
requirements.txt        Python dependencies
outputs/                Generated filtered files
```
