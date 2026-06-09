# pButtons Parser

A web tool for extracting specific sections from InterSystems IRIS pButtons HTML performance reports. Upload a pButtons file, choose which sections to keep, and download a clean filtered copy — without sharing data you didn't intend to.

## Features

- **100% local processing — your file never leaves your machine.** The tool runs entirely on your own computer. All parsing is done in-process using Python's standard library (`re`). The three dependencies (FastAPI, Uvicorn, python-multipart) are server/parsing primitives that make no outbound network calls. The server binds to `127.0.0.1` (loopback only), so even the traffic between your browser and the tool stays within your machine's network stack. No data is sent to any cloud service or AI.
- Drag-and-drop upload of pButtons `.html` files
- All sections detected and listed automatically
- Sensitive sections (license keys, usernames, file paths, machine details) are flagged and **pre-deselected** with explanations
- One-click "Select non-sensitive only" filter
- Excluded sections keep their header and nav anchor — replaced with a clearly marked placeholder so the file remains well-formed and shareable
- Download the filtered file with only the sections you chose

## Setup

Requires Python 3.9+.

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

## Running

```bash
./venv/Scripts/uvicorn app:app --host 127.0.0.1 --port 8000 --reload
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
| Windows info | OS/hardware summary cards |
| tasklist | Top processes by memory |
| mgstat | Global refs, physical I/O, journal writes, cache, network charts; stat cards; insights |
| iostat | %util, CPU iowait, IOPS, throughput, latency charts; insights |
| cpu | CPU topology summary |
| %SS | Process type breakdown, TCP trend, top-CPU/Glob tables, namespace breakdown; insights |
| sar -d | %util, tps, throughput, r/w latency, queue depth charts; per-device summary; insights |
| sar -u | Stacked CPU chart (user/sys/iowait/steal); stat cards; insights |
| vmstat | Run queue, swap I/O, CPU breakdown, block I/O charts; stat cards; insights |
| irisstat -D | Lock contention summary and per-second rates tables; insights |
| perfmon | CPU utilization, processor queue, available memory, paging, disk IOPS/throughput/latency, network throughput charts; insights |

## Project structure

```
app.py                  FastAPI backend (upload + export endpoints)
pbuttons_parser.py      HTML parsing and section reconstruction logic
static/index.html       Single-page frontend (no build step)
requirements.txt        Python dependencies
uploads/                Temp directory (not currently used for storage)
outputs/                Generated filtered files
```
