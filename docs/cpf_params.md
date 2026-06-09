# CPF Parameter Reference

Parameters handled by `analyzers/cpf.py`, extracted from the InterSystems IRIS
Configuration Parameter File Reference (RACS.pdf, version 2026.1).

Each entry lists: unit, default, valid range, and performance/operational notes.

---

## [config] — Memory & Buffers

### globals
**Unit:** MB per block size  
**Default:** `0,0,0,0,0,0`  
**Format:** `0,0,c,d,e,f`
- `a`, `b` — always 0, unused
- `c` — MB allocated for 8 kB blocks
- `d` — MB allocated for 16 kB blocks
- `e` — MB allocated for 32 kB blocks
- `f` — MB allocated for 64 kB blocks

When all values are 0, IRIS auto-allocates **25% of total physical RAM** at startup.  
To use block sizes other than 8 kB, `DBSizesAllowed` in `[Startup]` must be configured.  
Limit: 16 TB on 64-bit systems.

> **Analyzer note:** Each value is already in MB — do not multiply by block size.

---

### routines
**Unit:** MB (single value) or MB per pool (6-value form)  
**Default:** `0`  
**Single-value format:** `routines=n` — total MB, auto-split across pool sizes  
**Multi-value format:** `routines=n1,n2,n3,n4,n5,n6` — MB for 2kB/4kB/8kB/16kB/32kB/64kB pools

When `0`: auto-sizes to **10% of 8 kB global buffers**, minimum 80 MB, maximum 1020 MB.  
Minimum for any non-zero value: 80 MB (IRIS adjusts up if smaller).

---

### locksiz
**Unit:** bytes  
**Default:** `0`  
**Minimum (non-zero):** 65,536 bytes

When `0`: lock table can grow up to the available space in `gmheap` — effectively
unlimited within shared memory. Setting a non-zero value places a fixed upper bound.  
If `locksiz=0` and lock table is exhausted, increase `gmheap` instead, or lower `LockThreshold` in `[SQL]`.

Changes take effect **immediately** (no restart required).

---

### gmheap
**Unit:** KB  
**Default:** `0`  
**Range:** 16,384 – 1,073,741,760 KB

When `0`: auto-sized to **3% of global buffers**, minimum 307,200 KB (300 MB), maximum 2,097,000 KB (2 GB).  
Used for: global mapping, database name/directory info, security system, lock table (when `locksiz=0`), parallel SQL.  
Requires **restart** to apply changes.

---

### jrnbufs
**Unit:** MB  
**Default:** `64`  
**Range:** 8 – 1024 MB (8 for 8-bit instances, 16 for Unicode)

Amount of memory for journal write buffers. More memory = more journal data buffered in RAM = better write performance, but more potential data loss on hard crash.  
**Combined limit:** `jrnbufs + FileSizeLimit` must not exceed **4096 MB**.  
Requires **restart** to apply changes.

---

### bbsiz
**Unit:** KB  
**Default:** `-1`  
**Range:** 256 – 2,147,483,647 KB; `-1` = maximum (~2 TB, effectively unlimited)

Maximum per-process memory allocation. Used for symbol table, I/O buffers, and other process-private memory. Memory is allocated as needed up to this cap and generally not released until the process exits.  
Changes apply to **new processes only**.

---

### targwijsz
**Unit:** MB  
**Default:** `0`

Pre-allocates disk space for the Write Image Journal (WIJ) file. When `0`, WIJ grows dynamically as needed.  
Useful on fast storage to avoid WIJ growth pauses during high activity.  
Setting too high wastes disk; no benefit beyond the maximum database cache size.

---

### ijcbuff
**Unit:** bytes  
**Default:** `512`  
**Range:** 512 – 8192 bytes

Size of each Inter-Job Communication (IJC) buffer. InterSystems recommends the default.  
Requires **restart** to apply changes.

---

### ijcnum
**Unit:** count (devices)  
**Default:** `16`  
**Range:** 0 – 256

Number of IJC devices. Each device uses one buffer of size `ijcbuff`.  
Requires **restart** to apply changes.

---

### errlog
**Unit:** count (entries)  
**Default:** `500`  
**Range:** 10 – 10,000

Maximum entries in the IRIS system error log. Old entries expire as the limit is reached.

---

### memlock
**Unit:** bit flags  
**Default:** `0`

Controls shared memory allocation strategy. Bit values:
- `1` — Lock shared memory into physical RAM (non-Windows/macOS)
- `8` — Lock text segment into physical RAM (some UNIX platforms)
- `32` — Disable large/huge pages
- `128` — Disable backoff on allocation failure (abort instead of retrying with less memory)

Default (0): IRIS attempts large pages first, falls back to standard pages, reduces by 1/8 and retries on failure.  
Requires **restart** to apply changes.

---

### wijdir
**Unit:** path  
**Default:** `<install-dir>/mgr`

Directory for the Write Image Journal (WIJ) file. InterSystems recommends placing the WIJ on a **different partition from your databases** for I/O isolation.

---

### netjob
**Unit:** boolean (0/1)  
**Default:** `1`

When enabled, this instance accepts incoming remote JOB requests via ECP.

---

### nlstab
**Unit:** count (tables)  
**Default:** `50`  
**Range:** 0 – 64

Number of NLS (National Language Support) collation tables pre-allocated at startup. Does not include built-in collations.

---

### zfheap
**Unit:** `ZFString` (characters), `ZFSize` (bytes)  
**Default:** `0,0`  
**Format:** `zfheap=ZFString,ZFSize`

Configures the `$ZF` heap for callout libraries. When `0,0`, IRIS uses system defaults (ZFString=32,767 chars, ZFSize=135,168 bytes). InterSystems recommends leaving at `0,0`.  
Changes apply to **new processes only**.

---

## [Journal] — Journaling & Durability

### CurrentDirectory / AlternateDirectory
**Unit:** path  
**Default:** `<install-dir>/mgr/journal/`

Two separate journal directories for redundancy. If both point to the same path, a single disk failure loses all journal data. **Always configure AlternateDirectory on a separate physical disk.**

---

### DaysBeforePurge
**Unit:** days  
**Default:** `2`  
**Range:** 0 – 100

Days before finished journal files are purged. Works with `BackupsBeforePurge`: if both > 0, files are purged after whichever comes first. If both are 0, automatic purging is disabled.  
Ignored if `PurgeArchive=1`.

---

### BackupsBeforePurge
**Unit:** count (backups)  
**Default:** `2`  
**Range:** 0 – 10

Number of successful IRIS backups required before journal files can be purged.  
Works with `DaysBeforePurge` (see above).  
Ignored if `PurgeArchive=1`.

---

### FileSizeLimit
**Unit:** MB  
**Default:** `1024`  
**Range:** 0 – 4079 MB

Maximum size of a journal file. When reached, the current file closes and a new one starts.  
**Combined limit:** `FileSizeLimit + jrnbufs` must not exceed **4096 MB**.

---

### FreezeOnError
**Unit:** boolean (0/1)  
**Default:** `0`

- `0` — IRIS continues running on journal I/O error; journal daemon retries periodically (up to ~150 seconds). If retries fail, journaling is disabled. Risk: data written after the error may not be recoverable. Journaling must be manually restarted afterward.
- `1` — IRIS immediately freezes all journaled global updates on journal I/O error (or after 30 seconds of failed writes). System appears down until the problem is resolved. Protects data integrity.

---

### CompressFiles
**Unit:** boolean (0/1)  
**Default:** `1`

When enabled, completed journal files are compressed using Zstd. Compressed files get a `z` suffix (e.g., `20210818.001z`). The active journal file is not compressed until it closes.

---

### PurgeArchive
**Unit:** boolean (0/1)  
**Default:** `0`

When `1`, journal files are purged as soon as they are copied to the archive target. Overrides both `DaysBeforePurge` and `BackupsBeforePurge`.

---

## [Miscellaneous]

### SynchCommit
**Unit:** boolean (0/1)  
**Default:** `0`

> **Note:** Retained for compatibility — not recommended for new applications.

- `0` — `TCOMMIT` completes without waiting for journal flush. Better performance; small risk of losing the last few commits on OS crash or power loss.
- `1` — `TCOMMIT` waits for journal write to complete. Maximum durability; adds I/O latency per commit.

Per-process override available via `%SYSTEM.Process.SynchCommit()`.

---

## [Startup] — Instance Startup

### DefaultPort
**Unit:** port number  
**Default:** `1972` (classic) or `51773`/`51775` (standard IRIS)

SuperServer TCP port. Clients connect here for all protocol connections (JDBC, ODBC, ObjectScript, etc.).

### EnsembleAutoStart
**Unit:** boolean (0/1)  
**Default:** `1`

When enabled, productions configured for auto-start in each interoperability-enabled namespace start automatically when IRIS starts. Disable to prevent troubled productions from starting during debugging.

### JobServers
**Unit:** count  
**Default:** `0`  
**Range:** 0 – 2000

Target number of pre-spawned job server processes to maintain. `0` = on-demand (default). Pre-spawned servers reduce connection latency under burst load by skipping OS-level process creation and initialization.  
The effective target is `min(configured, dynamic_target)` where the dynamic target scales with total job server count (5 up to 20 total, 10 up to 100, 20 for 100+).

### ShutdownTimeout
**Unit:** seconds  
**Default:** `300` (5 minutes)  
**Range:** 120 – 100,000

How long IRIS waits for graceful shutdown before forcing termination.

### ErrorPurge
**Unit:** days  
**Default:** `30`

Application error log entries are purged after this many days.

### FIPSMode
**Unit:** boolean (0/1)  
**Default:** `0`

Enables FIPS 140-2 compliant cryptography.

---

## [SQL] — SQL Engine

### AutoParallel
**Unit:** boolean (0/1)  
**Default:** `1`

Enables parallel query execution. In non-sharded environments, IRIS decides per-query based on `AutoParallelThreshold`. If `AdaptiveMode=1` and `AutoParallel=0`, AdaptiveMode overrides and re-enables parallelism.

### AutoParallelThreshold
**Unit:** row count (approximate)  
**Default:** `3200`

Minimum number of tuples in the visited map before a query is considered for parallel execution. Higher = less parallelism. No effect when `AutoParallel=0`.

### LockTimeout
**Unit:** seconds  
**Default:** `10`  
**Range:** 0 – 32,767 (max ~9 hours)

Lock timeout for SQL statement execution. Short values surface contention quickly; increase if legitimate long-running transactions are timing out.

### LockThreshold
**Unit:** row count  
**Default:** `1000`

Row lock escalation threshold per table per transaction. When exceeded, IRIS attempts a table-level lock to prevent lock table overflow. See also `locksiz` and `gmheap`.

### ClientMaxIdleTime
**Unit:** seconds  
**Default:** `0` (no timeout)

Maximum idle time before an SQL client connection (JDBC/ODBC/ADO.NET) is forcibly disconnected. `0` = no timeout. Setting a value prevents idle connections from holding resources and locks indefinitely.

### AdaptiveMode
**Unit:** boolean (0/1)  
**Default:** `1`

Enables runtime query plan choice and automatic tuning. Can override `AutoParallel=0`.

### ODBCVarcharMaxlen
**Unit:** characters  
**Default:** `4096`

Maximum VARCHAR length reported to ODBC clients.

---

## [ECP] — Enterprise Cache Protocol

### ClientReconnectDuration
**Unit:** seconds  
**Default:** `1200` (20 minutes)  
**Range:** 10 – 65,636

How long an ECP Application Server (client) keeps trying to reconnect to a failed Data Server before giving up. Reconnection attempts occur at `ClientReconnectInterval` intervals.

### ClientReconnectInterval
**Unit:** seconds  
**Default:** `5`  
**Range:** 1 – 60

Interval between ECP reconnection attempts.

### ServerTroubleDuration
**Unit:** seconds  
**Default:** `60`  
**Range:** 20 – 65,636

How long an ECP connection stays in "troubled" state before the Data Server declares it dead and stops recovery attempts.

---

## [WorkQueues]

Each key is a queue name (e.g., `Default`, `SQL`, `Utility`). Value format: `workers[,maxworkers[,...]]`.  
Empty value = IRIS default sizing.

---

## Key relationships

| If you see...                        | Check these parameters                          |
|--------------------------------------|-------------------------------------------------|
| High PhyRds in mgstat                | `globals` — buffer pool may be undersized       |
| LOCKTABLEFULL errors                 | `locksiz`, `gmheap`, `LockThreshold`            |
| Journal I/O bottleneck               | `jrnbufs`, `FileSizeLimit`, `wijdir`            |
| Slow commits                         | `SynchCommit`, `FreezeOnError`, journal dirs    |
| High SQL lock waits                  | `LockTimeout`, `LockThreshold`, `locksiz`       |
| Slow job startup under burst load    | `JobServers`                                    |
| ECP reconnect storms                 | `ClientReconnectDuration`, `ClientReconnectInterval` |
| Parallel SQL not working             | `AutoParallel`, `AutoParallelThreshold`, `gmheap` |
