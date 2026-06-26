"""
Analyzer for the 'CPF file' section in pButtons files.

Parses the INI-style iris.cpf and produces:
  - Summary cards for the most critical performance/durability settings
  - Annotated tables per relevant section (Parameter | Value | Status | Notes)
  - Insight flags for anything concerning

No charts — CPF is static config, not time-series data.
"""
import re


# ── INI parser ────────────────────────────────────────────────────────────────

def _parse_cpf(text: str) -> dict[str, dict[str, str]]:
    """Parse INI-style CPF into {section: {key: value}}."""
    result: dict[str, dict[str, str]] = {}
    current = '__top__'
    result[current] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        m = re.match(r'^\[(.+?)\]$', line)
        if m:
            current = m.group(1)
            result.setdefault(current, {})
            continue
        if '=' in line:
            key, _, val = line.partition('=')
            result[current][key.strip()] = val.strip()
    return result


# ── Shared HTML helpers ───────────────────────────────────────────────────────

def _flag(level: str, text: str) -> str:
    style = {
        'red':   ('#fef2f2', '#fca5a5', '#7f1d1d', '#ef4444'),
        'amber': ('#fffbeb', '#fcd34d', '#78350f', '#f59e0b'),
        'info':  ('#eff6ff', '#93c5fd', '#1e3a5f', '#3b82f6'),
        'green': ('#f0fdf4', '#bbf7d0', '#14532d', '#22c55e'),
    }[level]
    bg, border, fg, dot = style
    return (f'<div style="display:flex;align-items:flex-start;gap:8px;padding:7px 11px;'
            f'background:{bg};border:1px solid {border};border-radius:6px;'
            f'font-size:0.78rem;color:{fg};line-height:1.4;margin-bottom:5px">'
            f'<span style="color:{dot};flex-shrink:0;margin-top:1px">&#9679;</span>'
            f'<span>{text}</span></div>')


def _card(label: str, value: str, sub: str = '', color: str = '#1a1a2e') -> str:
    return (f'<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;'
            f'padding:12px 16px;min-width:130px;flex:1">'
            f'<div style="font-size:0.68rem;color:#888;text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:4px">{label}</div>'
            f'<div style="font-size:1.05rem;font-weight:700;color:{color};line-height:1.2">{value}</div>'
            + (f'<div style="font-size:0.7rem;color:#888;margin-top:3px">{sub}</div>' if sub else '')
            + '</div>')


def _badge(text: str, color: str, bg: str) -> str:
    return (f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;'
            f'font-size:0.68rem;font-weight:600;background:{bg};color:{color}">{text}</span>')


# Status badges
_OK    = _badge('OK',      '#14532d', '#dcfce7')
_WARN  = _badge('WARN',    '#78350f', '#fef9c3')
_RISK  = _badge('RISK',    '#7f1d1d', '#fee2e2')
_INFO  = _badge('INFO',    '#1e3a5f', '#dbeafe')
_DEF   = _badge('DEFAULT', '#374151', '#f3f4f6')


def _section_table(table_id: str, title: str, subtitle: str, rows: list[tuple]) -> str:
    """
    rows: list of (param, value, status_badge_html, notes)
    """
    if not rows:
        return ''
    body = ''
    for param, value, badge, notes in rows:
        body += (
            f'<tr style="border-bottom:1px solid #f0f2f5">'
            f'<td style="padding:6px 10px;font-size:0.77rem;font-family:monospace;'
            f'white-space:nowrap;color:#334">{param}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;font-family:monospace;'
            f'white-space:nowrap">{value}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;white-space:nowrap">{badge}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;color:#556;line-height:1.4">{notes}</td>'
            f'</tr>'
        )
    return (
        f'<div style="margin-bottom:18px;overflow-x:auto">'
        f'<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        f'letter-spacing:.06em;margin-bottom:4px">{title}'
        + (f'<span style="font-weight:400;text-transform:none;color:#999;margin-left:8px">'
           f'{subtitle}</span>' if subtitle else '')
        + f'</div>'
        f'<table id="{table_id}" style="border-collapse:collapse;width:100%;background:#f8f9fc;'
        f'border:1px solid #dde3ee;border-radius:8px;overflow:hidden">'
        f'<thead><tr style="background:#eef2f7;font-size:0.7rem;color:#667;text-transform:uppercase">'
        f'<th onclick="sortTable(\'{table_id}\',0,this)" '
        f'style="padding:7px 10px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap">Parameter ↕</th>'
        f'<th onclick="sortTable(\'{table_id}\',1,this)" '
        f'style="padding:7px 10px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap">Value ↕</th>'
        f'<th style="padding:7px 10px;text-align:left;white-space:nowrap">Status</th>'
        f'<th style="padding:7px 10px;text-align:left">Notes</th>'
        f'</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'</table></div>'
    )


# ── Per-section analysis ──────────────────────────────────────────────────────

def _analyze_config(cfg: dict) -> tuple[list, list]:
    """Returns (rows, flags) for [config] section."""
    rows = []
    flags = []
    g = cfg.get

    # globals: 0,0,c,d,e,f where each value is MB for that block size
    # a,b are always 0 (unused); c=8kB blocks; d=16kB; e=32kB; f=64kB
    globals_val = g('globals', '0,0,0,0,0,0')
    parts = [v.strip() for v in globals_val.split(',')]
    all_zero = all(v in ('0', '') for v in parts)
    if all_zero:
        rows.append(('globals', globals_val, _DEF,
                     'Global buffer pool (MB per block size) -- all zeros means IRIS '
                     'auto-allocates 25% of physical RAM at startup. '
                     'Verify actual allocation in mgstat <b>GblSz</b> column.'))
        flags.append(_flag('info',
            '<b>Global buffers at default (auto-sized)</b> -- IRIS allocates 25% of physical RAM. '
            'Confirm actual size in mgstat GblSz. For production workloads, '
            'explicit sizing is recommended.'))
    else:
        # Each value is already in MB
        total_mb = sum(int(v) for v in parts if v.strip().lstrip('-').isdigit() and int(v) > 0)
        block_labels = ['a(unused)', 'b(unused)', '8kB', '16kB', '32kB', '64kB']
        configured = ', '.join(
            f'{block_labels[i]}: {v} MB' for i, v in enumerate(parts[:6])
            if v.strip().isdigit() and int(v) > 0
        )
        rows.append(('globals', globals_val, _OK,
                     f'Global buffer pool -- {total_mb:,} MB total. '
                     f'Format: 0,0,8kB-MB,16kB-MB,32kB-MB,64kB-MB.'
                     + (f' Configured: {configured}.' if configured else '')))

    # routines: single value = total MB; 6 values = MB per pool
    # 0 = auto (10% of 8kB global buffers, min 80 MB, max 1 GB)
    routines_val = g('routines', '0')
    try:
        if ',' in routines_val:
            total_r = sum(int(v.strip()) for v in routines_val.split(',') if v.strip().isdigit())
            rows.append(('routines', routines_val, _OK,
                         f'Routine buffer cache -- {total_r} MB total, manually split across buffer pools.'))
        elif int(routines_val) == 0:
            rows.append(('routines', routines_val, _DEF,
                         'Routine buffer cache -- 0 = auto-sized (10% of 8kB global buffers, min 80 MB, max 1 GB).'))
        else:
            rows.append(('routines', routines_val, _OK,
                         f'Routine buffer cache -- {int(routines_val)} MB explicitly set.'))
    except ValueError:
        rows.append(('routines', routines_val, _DEF, 'Routine buffer cache.'))

    # locksiz
    locksiz_val = g('locksiz', '0')
    try:
        lsz = int(locksiz_val)
        if lsz == 0:
            rows.append(('locksiz', locksiz_val, _WARN,
                         'Lock table size — 0 uses IRIS default (~1 MB). '
                         'For systems with heavy concurrent lock usage, increase this. '
                         'A full lock table causes <b>LOCKTABLEFULL</b> errors.'))
            flags.append(_flag('amber',
                '<b>Lock table at default (0)</b> — IRIS default is ~1 MB. '
                'If you see LOCKTABLEFULL errors or high lock contention in irisstat -D, '
                'increase locksiz in [config]. Typical values: 4,000,000–16,000,000 bytes.'))
        else:
            rows.append(('locksiz', locksiz_val, _OK,
                         f'Lock table — {lsz / 1048576:.1f} MB ({lsz:,} bytes) explicitly allocated.'))
    except ValueError:
        rows.append(('locksiz', locksiz_val, _DEF, 'Lock table size.'))

    # gmheap: value is in KB (range 16384-1,073,741,760 KB); 0 = auto (3% of global buffers, min 300 MB)
    gmheap_val = g('gmheap', '0')
    try:
        gm = int(gmheap_val)
        if gm == 0:
            rows.append(('gmheap', gmheap_val, _DEF,
                         'Shared memory heap -- 0 = auto-sized (3% of global buffers, min 300 MB, max 2 GB). '
                         'May need manual increase for large ECP deployments or parallel SQL.'))
        else:
            rows.append(('gmheap', gmheap_val, _OK,
                         f'Shared memory heap -- {gm:,} KB ({gm/1024:.0f} MB) explicitly set.'))
    except ValueError:
        rows.append(('gmheap', gmheap_val, _DEF, 'Shared memory heap (KB).'))

    # jrnbufs: value is directly in MB (range 8-1024 MB, default 64 MB)
    jrnbufs_val = g('jrnbufs', '64')
    try:
        jb = int(jrnbufs_val)
        if jb <= 64:
            rows.append(('jrnbufs', jrnbufs_val, _DEF,
                         f'Journal write buffers -- {jb} MB. Default is 64 MB. '
                         f'For write-heavy workloads, consider increasing. '
                         f'Note: jrnbufs + FileSizeLimit must not exceed 4096 MB combined.'))
        else:
            rows.append(('jrnbufs', jrnbufs_val, _OK,
                         f'Journal write buffers -- {jb} MB (above default of 64 MB). '
                         f'Configured for write-heavy workload.'))
    except ValueError:
        rows.append(('jrnbufs', jrnbufs_val, _DEF, 'Journal write buffers (MB).'))

    # bbsiz: value is in KB (range 256-2,147,483,647 KB); -1 = max (~2 TB, effectively unlimited)
    bbsiz_val = g('bbsiz', '-1')
    rows.append(('bbsiz', bbsiz_val, _DEF if bbsiz_val in ('-1', '0') else _OK,
                 'Max per-process memory in KB (-1 = unlimited, ~2 TB). '
                 'Limits symbol table and I/O buffer allocation per process.'))

    # targwijsz
    wij_val = g('targwijsz', '0')
    rows.append(('targwijsz', wij_val, _DEF if wij_val == '0' else _OK,
                 'Target WIJ (Write Image Journal) size in MB. '
                 '0 = IRIS default. Increase if WIJ is a bottleneck on fast storage.'))

    # ijcbuff: value is in bytes (range 512-8192 bytes); ijcnum: number of IJC devices (0-256)
    ijcbuff = g('ijcbuff', '512')
    ijcnum  = g('ijcnum', '16')
    rows.append(('ijcbuff / ijcnum', f'{ijcbuff} / {ijcnum}', _DEF,
                 f'Inter-job communication: {ijcbuff} bytes per buffer, {ijcnum} devices. '
                 f'Defaults are fine unless ^$Job messaging is heavily used.'))

    return rows, flags


def _analyze_journal(cfg: dict, misc_cfg: dict) -> tuple[list, list]:
    rows = []
    flags = []
    g = cfg.get

    cur_dir  = g('CurrentDirectory', '')
    alt_dir  = g('AlternateDirectory', '')
    if cur_dir and alt_dir:
        same = cur_dir.rstrip('/\\').lower() == alt_dir.rstrip('/\\').lower()
        if same or not alt_dir:
            rows.append(('CurrentDirectory / AlternateDirectory',
                         f'{cur_dir} / {alt_dir or "(none)"}', _RISK,
                         '<b>Both journal directories point to the same path.</b> '
                         'If this disk fails, journals are lost. Set AlternateDirectory '
                         'to a separate physical disk.'))
            flags.append(_flag('red',
                '<b>No journal redundancy</b> — CurrentDirectory and AlternateDirectory '
                'are the same. A single disk failure loses journal data. '
                'Set AlternateDirectory to a separate physical volume.'))
        else:
            rows.append(('CurrentDirectory / AlternateDirectory',
                         f'{cur_dir} / {alt_dir}', _OK,
                         'Journal written to two separate directories — redundancy is configured.'))

    days = g('DaysBeforePurge', '2')
    try:
        d = int(days)
        badge = _WARN if d < 3 else _OK
        note = (f'Journal files purged after {d} day(s). '
                + ('Low retention — if a backup job fails silently you have little recovery window.'
                   if d < 3 else 'Adequate retention for most environments.'))
        rows.append(('DaysBeforePurge', days, badge, note))
        if d < 3:
            flags.append(_flag('amber',
                f'<b>Journal retention is {d} day(s)</b> — low margin if a backup fails. '
                f'Consider increasing DaysBeforePurge to at least 3–5.'))
    except ValueError:
        rows.append(('DaysBeforePurge', days, _DEF, 'Days before journal files are purged.'))

    fsize = g('FileSizeLimit', '1024')
    try:
        fs = int(fsize)
        rows.append(('FileSizeLimit', fsize, _OK if fs >= 512 else _WARN,
                     f'Max journal file size: {fs} MB. Smaller files = more frequent switches, '
                     f'which can generate more I/O overhead. Typical: 1024–4096 MB.'))
    except ValueError:
        rows.append(('FileSizeLimit', fsize, _DEF, 'Maximum journal file size in MB.'))

    freeze = g('FreezeOnError', '0')
    if freeze == '0':
        rows.append(('FreezeOnError', '0', _WARN,
                     'IRIS will <b>not</b> freeze if journal I/O fails. '
                     'This protects uptime but risks data inconsistency if '
                     'the journal disk silently fails or fills up.'))
        flags.append(_flag('amber',
            '<b>FreezeOnError=0</b> — IRIS will continue running if journal I/O fails. '
            'Data written after a journal error may not be recoverable. '
            'Consider enabling FreezeOnError=1 for critical systems.'))
    else:
        rows.append(('FreezeOnError', freeze, _OK,
                     'IRIS will freeze on journal I/O error — protects data integrity.'))

    compress = g('CompressFiles', '1')
    rows.append(('CompressFiles', compress, _INFO if compress == '1' else _DEF,
                 'Journal file compression enabled. ' if compress == '1' else
                 'Journal file compression disabled — journals will consume more disk space.'))

    backups = g('BackupsBeforePurge', '2')
    rows.append(('BackupsBeforePurge', backups, _DEF,
                 f'Number of backups required before a journal file can be purged.'))

    # SynchCommit lives in [Miscellaneous] but is journal-related
    sync = misc_cfg.get('SynchCommit', '0')
    if sync == '0':
        rows.append(('SynchCommit (Misc)', '0', _INFO,
                     'Async commit — transactions commit without waiting for journal to flush to disk. '
                     '<b>Better performance</b>, but a system crash (not IRIS crash) could lose the '
                     'last few committed transactions. OS-level write caching applies.'))
        flags.append(_flag('info',
            '<b>SynchCommit=0</b> (async commit) — transaction performance is maximized, '
            'but an OS crash or power loss could lose the last few commits. '
            'Acceptable for most workloads; set SynchCommit=1 only if strict durability is required.'))
    else:
        rows.append(('SynchCommit (Misc)', sync, _OK,
                     'Sync commit — every transaction waits for journal flush. '
                     'Maximum durability, but adds I/O latency to each commit.'))

    return rows, flags


def _analyze_startup(cfg: dict) -> list:
    rows = []
    g = cfg.get

    port = g('DefaultPort', '1972')
    rows.append(('DefaultPort', port, _DEF if port in ('1972', '51773', '51775') else _INFO,
                 f'SuperServer port. Standard IRIS ports are 1972 (classic) or 51773/51775.'))

    ens = g('EnsembleAutoStart', '0')
    rows.append(('EnsembleAutoStart', ens, _INFO if ens == '1' else _DEF,
                 'Interoperability (Ensemble) productions auto-start on IRIS startup. '
                 if ens == '1' else
                 'Interoperability productions do not auto-start.'))

    job_servers = g('JobServers', '0')
    try:
        js = int(job_servers)
        rows.append(('JobServers', job_servers,
                     _DEF if js == 0 else _OK,
                     f'Pre-spawned job servers: {js}. '
                     + ('0 = jobs spawned on demand (default).'
                        if js == 0 else
                        f'{js} job slots pre-allocated — reduces connection latency under burst load.')))
    except ValueError:
        rows.append(('JobServers', job_servers, _DEF, 'Pre-spawned job server slots.'))

    shutdown = g('ShutdownTimeout', '300')
    rows.append(('ShutdownTimeout', shutdown, _DEF,
                 f'Graceful shutdown timeout: {shutdown}s. '
                 f'IRIS waits this long for processes to exit before forcing shutdown.'))

    fips = g('FIPSMode', '0')
    rows.append(('FIPSMode', fips, _INFO if fips == '1' else _DEF,
                 'FIPS 140-2 cryptographic mode enabled.' if fips == '1'
                 else 'FIPS mode disabled.'))

    ipv6 = g('IPv6', '0')
    rows.append(('IPv6', ipv6, _INFO if ipv6 == '1' else _DEF,
                 'IPv6 networking enabled.' if ipv6 == '1' else 'IPv6 disabled (IPv4 only).'))

    errpurge = g('ErrorPurge', '30')
    rows.append(('ErrorPurge', errpurge, _DEF,
                 f'Application error log entries purged after {errpurge} days.'))

    return rows


def _analyze_sql(cfg: dict) -> list:
    rows = []
    g = cfg.get

    ap = g('AutoParallel', '1')
    rows.append(('AutoParallel', ap, _OK if ap == '1' else _WARN,
                 'Parallel query execution enabled — IRIS splits large queries across multiple CPUs.'
                 if ap == '1' else
                 'Parallel query disabled — large queries run single-threaded.'))

    apt = g('AutoParallelThreshold', '3200')
    rows.append(('AutoParallelThreshold', apt, _DEF,
                 f'Queries scanning >{apt} rows become candidates for parallel execution.'))

    lt = g('LockTimeout', '10')
    rows.append(('LockTimeout', lt, _DEF if lt == '10' else _INFO,
                 f'SQL row/table lock timeout: {lt}s. '
                 f'Default 10s — short enough to surface contention quickly.'))

    lth = g('LockThreshold', '1000')
    rows.append(('LockThreshold', lth, _DEF,
                 f'Row lock escalation threshold: {lth} rows. '
                 f'Above this, IRIS escalates to a table lock.'))

    idle = g('ClientMaxIdleTime', '0')
    rows.append(('ClientMaxIdleTime', idle, _WARN if idle == '0' else _OK,
                 'Max idle time for SQL client connections — 0 means no timeout. '
                 'Idle connections hold locks and consume resources. '
                 'Consider setting a reasonable value (e.g. 300–600s).'
                 if idle == '0' else
                 f'SQL client idle timeout: {idle}s.'))

    adaptive = g('AdaptiveMode', '1')
    rows.append(('AdaptiveMode', adaptive, _OK if adaptive == '1' else _DEF,
                 'Adaptive SQL optimization enabled — query plans auto-tune based on data distributions.'
                 if adaptive == '1' else 'Adaptive mode disabled.'))

    odbc_max = g('ODBCVarcharMaxlen', '4096')
    rows.append(('ODBCVarcharMaxlen', odbc_max, _DEF,
                 f'Max VARCHAR length reported to ODBC clients: {odbc_max} chars.'))

    return rows


def _analyze_ecp(cfg: dict) -> tuple[list, bool]:
    """Returns (rows, is_ecp_active)."""
    rows = []
    g = cfg.get

    reconn_dur = g('ClientReconnectDuration', '1200')
    reconn_int = g('ClientReconnectInterval', '5')
    trouble    = g('ServerTroubleDuration', '60')

    # ECP is active if any values are non-default or if we have ECP-specific config
    is_ecp = any(v != '' for v in [g('ClientReconnectDuration', ''), g('ServerTroubleDuration', '')])

    rows.append(('ClientReconnectDuration', reconn_dur, _DEF,
                 f'ECP client reconnect window: {reconn_dur}s ({int(reconn_dur)//60}m). '
                 f'How long a client tries to reconnect to a failed ECP server.'))
    rows.append(('ClientReconnectInterval', reconn_int, _DEF,
                 f'ECP reconnect retry interval: {reconn_int}s.'))
    rows.append(('ServerTroubleDuration', trouble, _DEF,
                 f'ECP server trouble timeout: {trouble}s. '
                 f'After this, clients consider the server unavailable.'))

    return rows, True


def _analyze_workqueues(cfg: dict) -> list:
    rows = []
    for key, val in cfg.items():
        if not val:
            rows.append((key, '(default)', _DEF,
                         f'{key} work queue — IRIS default sizing.'))
        else:
            parts = val.split(',')
            workers = parts[0] if parts else val
            rows.append((key, val, _OK,
                         f'{key} work queue — {workers} worker(s) configured.'))
    return rows


def _analyze_mirror(cfg: dict) -> tuple[str, list]:
    """Returns (summary_text, flags)."""
    flags = []
    join = cfg.get('JoinMirror', '0')
    if join == '1':
        sysname   = cfg.get('SystemName', '')
        async_type = cfg.get('AsyncMemberType', '0')
        guid      = cfg.get('AsyncMemberGUID', '')
        member_label = 'Async DR Member' if async_type != '0' else 'Sync Mirror Member'
        flags.append(_flag('info',
            f'<b>Mirror member</b>: this instance is a {member_label}. '
            f'System name: <code>{sysname or "(not set)"}</code>. '
            f'Mirror configuration affects journal behavior and failover.'))
        return member_label, flags
    return 'Standalone', flags


# ── Summary cards ─────────────────────────────────────────────────────────────

_SYS_DBS = {'IRISSYS', 'IRISLIB', 'IRISTEMP', 'IRISLOCALDATA', 'IRISAUDIT',
            'IRISMETRICS', 'IRISSECURITY', 'ENSLIB'}
_SYS_NS  = {'%SYS'}


def _build_db_ns_table(db_cfg: dict, ns_cfg: dict) -> str:
    if not db_cfg and not ns_cfg:
        return ''

    # Build namespace → db mapping for cross-reference
    # ns_cfg values: "DBNAME" or "DBNAME,DBNAME2" (globals db, routines db)
    ns_to_dbs: dict[str, list[str]] = {}
    for ns, val in ns_cfg.items():
        ns_to_dbs[ns] = [v.strip() for v in val.split(',') if v.strip()]

    # Which databases are actually referenced by a namespace?
    referenced_dbs = {db for dbs in ns_to_dbs.values() for db in dbs}

    # ── Databases table ────────────────────────────────────────────────────────
    db_rows = ''
    for db_name in sorted(db_cfg.keys()):
        path = db_cfg[db_name]
        is_sys  = db_name.upper() in _SYS_DBS
        in_use  = db_name in referenced_dbs
        badge   = _badge('SYSTEM', '#374151', '#e5e7eb') if is_sys else \
                  (_OK if in_use else _badge('UNUSED?', '#78350f', '#fef9c3'))
        note    = 'InterSystems system database' if is_sys else \
                  ('Referenced by a namespace' if in_use else
                   'Not referenced by any namespace — may be unmapped or orphaned')
        db_rows += (
            f'<tr style="border-bottom:1px solid #f0f2f5">'
            f'<td style="padding:6px 10px;font-size:0.77rem;font-family:monospace;white-space:nowrap">{db_name}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;color:#556;word-break:break-all">{path}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;white-space:nowrap">{badge}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;color:#556">{note}</td>'
            f'</tr>'
        )

    db_table = (
        f'<div style="margin-bottom:18px;overflow-x:auto">'
        f'<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        f'letter-spacing:.06em;margin-bottom:4px">Databases'
        f'<span style="font-weight:400;text-transform:none;color:#999;margin-left:8px">'
        f'[Databases] — {len(db_cfg)} total</span></div>'
        f'<table id="cpf-dbs" style="border-collapse:collapse;width:100%;background:#f8f9fc;'
        f'border:1px solid #dde3ee;border-radius:8px;overflow:hidden">'
        f'<thead><tr style="background:#eef2f7;font-size:0.7rem;color:#667;text-transform:uppercase">'
        f'<th onclick="sortTable(\'cpf-dbs\',0,this)" style="padding:7px 10px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap">Name ↕</th>'
        f'<th style="padding:7px 10px;text-align:left">Path</th>'
        f'<th style="padding:7px 10px;text-align:left;white-space:nowrap">Type</th>'
        f'<th style="padding:7px 10px;text-align:left">Notes</th>'
        f'</tr></thead>'
        f'<tbody>{db_rows}</tbody>'
        f'</table></div>'
    ) if db_rows else ''

    # ── Namespaces table ───────────────────────────────────────────────────────
    ns_rows = ''
    for ns_name in sorted(ns_cfg.keys()):
        dbs = ns_to_dbs.get(ns_name, [])
        is_sys = ns_name.upper() in _SYS_NS
        badge  = _badge('SYSTEM', '#374151', '#e5e7eb') if is_sys else _OK
        globals_db  = dbs[0] if len(dbs) > 0 else '—'
        routines_db = dbs[1] if len(dbs) > 1 else globals_db
        same_db = globals_db == routines_db
        db_display = globals_db if same_db else f'{globals_db} / {routines_db}'
        note = ('System namespace' if is_sys else
                ('Globals and routines in same database' if same_db else
                 f'Globals: {globals_db} · Routines: {routines_db}'))
        ns_rows += (
            f'<tr style="border-bottom:1px solid #f0f2f5">'
            f'<td style="padding:6px 10px;font-size:0.77rem;font-family:monospace;white-space:nowrap">{ns_name}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;font-family:monospace;white-space:nowrap">{db_display}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;white-space:nowrap">{badge}</td>'
            f'<td style="padding:6px 10px;font-size:0.77rem;color:#556">{note}</td>'
            f'</tr>'
        )

    ns_table = (
        f'<div style="margin-bottom:18px;overflow-x:auto">'
        f'<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        f'letter-spacing:.06em;margin-bottom:4px">Namespaces'
        f'<span style="font-weight:400;text-transform:none;color:#999;margin-left:8px">'
        f'[Namespaces] — {len(ns_cfg)} total</span></div>'
        f'<table id="cpf-ns" style="border-collapse:collapse;width:100%;background:#f8f9fc;'
        f'border:1px solid #dde3ee;border-radius:8px;overflow:hidden">'
        f'<thead><tr style="background:#eef2f7;font-size:0.7rem;color:#667;text-transform:uppercase">'
        f'<th onclick="sortTable(\'cpf-ns\',0,this)" style="padding:7px 10px;text-align:left;cursor:pointer;user-select:none;white-space:nowrap">Namespace ↕</th>'
        f'<th style="padding:7px 10px;text-align:left;white-space:nowrap">Database(s)</th>'
        f'<th style="padding:7px 10px;text-align:left;white-space:nowrap">Type</th>'
        f'<th style="padding:7px 10px;text-align:left">Notes</th>'
        f'</tr></thead>'
        f'<tbody>{ns_rows}</tbody>'
        f'</table></div>'
    ) if ns_rows else ''

    return db_table + ns_table


def _build_cards(sections: dict) -> str:
    config_cfg = sections.get('config', {})
    journal_cfg = sections.get('Journal', {})
    misc_cfg    = sections.get('Miscellaneous', {})
    mirror_cfg  = sections.get('MirrorMember', {})

    cards = []

    # Global buffers
    globals_val = config_cfg.get('globals', '0,0,0,0,0,0')
    parts = [v.strip() for v in globals_val.split(',')]
    all_zero = all(v in ('0', '') for v in parts)
    if all_zero:
        cards.append(_card('Global Buffers', 'Auto-sized', 'Confirm in mgstat GblSz', '#d97706'))
    else:
        total_mb = sum(int(v) for v in parts if v.isdigit() and int(v) > 0)
        cards.append(_card('Global Buffers', f'{total_mb:,} MB', 'Explicitly configured', '#0055aa'))

    # Journal redundancy
    cur = journal_cfg.get('CurrentDirectory', '')
    alt = journal_cfg.get('AlternateDirectory', '')
    same = not alt or cur.rstrip('/\\').lower() == alt.rstrip('/\\').lower()
    cards.append(_card('Journal Redundancy',
                        'At Risk' if same else 'Redundant',
                        'Same dir' if same else 'Separate dirs',
                        '#dc2626' if same else '#16a085'))

    # SynchCommit
    sync = misc_cfg.get('SynchCommit', '0')
    cards.append(_card('Sync Commit',
                        'Async' if sync == '0' else 'Sync',
                        'Faster, slight durability risk' if sync == '0' else 'Max durability',
                        '#d97706' if sync == '0' else '#16a085'))

    # FreezeOnError
    freeze = journal_cfg.get('FreezeOnError', '0')
    cards.append(_card('Freeze on Journal Error',
                        'Disabled' if freeze == '0' else 'Enabled',
                        'Uptime priority' if freeze == '0' else 'Data integrity priority',
                        '#d97706' if freeze == '0' else '#16a085'))

    # Lock table
    locksiz = config_cfg.get('locksiz', '0')
    try:
        ls = int(locksiz)
        lsz_label = 'Default' if ls == 0 else f'{ls / 1048576:.1f} MB'
        lsz_sub   = '~1 MB (IRIS default)' if ls == 0 else 'Explicitly configured'
        cards.append(_card('Lock Table', lsz_label, lsz_sub,
                            '#d97706' if ls == 0 else '#0055aa'))
    except ValueError:
        cards.append(_card('Lock Table', locksiz, '', '#888'))

    # Mirror
    join = mirror_cfg.get('JoinMirror', '0')
    async_type = mirror_cfg.get('AsyncMemberType', '0')
    mirror_label = 'Async DR' if join == '1' and async_type != '0' else \
                   'Sync Member' if join == '1' else 'Standalone'
    cards.append(_card('Mirror Mode', mirror_label, '', '#0055aa' if join == '1' else '#64748b'))

    # Databases
    db_cfg = sections.get('Databases', {})
    total_dbs = len(db_cfg)
    user_dbs  = sum(1 for k in db_cfg if k.upper() not in _SYS_DBS)
    cards.append(_card('Databases', str(total_dbs),
                        f'{user_dbs} user, {total_dbs - user_dbs} system', '#0055aa'))

    # Namespaces
    ns_cfg = sections.get('Namespaces', {})
    _SYS_NS = {'%SYS'}
    total_ns = len(ns_cfg)
    user_ns  = sum(1 for k in ns_cfg if k.upper() not in _SYS_NS)
    cards.append(_card('Namespaces', str(total_ns),
                        f'{user_ns} user, {total_ns - user_ns} system', '#0055aa'))

    inner = ''.join(cards)
    return (f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px">'
            f'{inner}</div>')


# ── Main ──────────────────────────────────────────────────────────────────────

async def analyze(section_text: str) -> str:
    sections = _parse_cpf(section_text)

    # Need at least [config] or [Journal] to be meaningful
    if not sections.get('config') and not sections.get('Journal'):
        return ''

    config_cfg  = sections.get('config', {})
    journal_cfg = sections.get('Journal', {})
    misc_cfg    = sections.get('Miscellaneous', {})
    startup_cfg = sections.get('Startup', {})
    sql_cfg     = sections.get('SQL', {})
    ecp_cfg     = sections.get('ECP', {})
    wq_cfg      = sections.get('WorkQueues', {})
    mirror_cfg  = sections.get('MirrorMember', {})
    db_cfg      = sections.get('Databases', {})
    ns_cfg      = sections.get('Namespaces', {})

    all_flags = []

    # Cards
    cards_html = _build_cards(sections)

    # [config] memory table
    config_rows, config_flags = _analyze_config(config_cfg)
    all_flags.extend(config_flags)
    config_table = _section_table(
        'cpf-config', 'Memory & Buffers',
        '[config]', config_rows,
    )

    # [Journal] + SynchCommit table
    jrn_rows, jrn_flags = _analyze_journal(journal_cfg, misc_cfg)
    all_flags.extend(jrn_flags)
    jrn_table = _section_table(
        'cpf-journal', 'Journal & Durability',
        '[Journal] + [Miscellaneous]', jrn_rows,
    )

    # [Startup] table
    startup_rows = _analyze_startup(startup_cfg)
    startup_table = _section_table(
        'cpf-startup', 'Startup & Runtime',
        '[Startup]', startup_rows,
    )

    # [SQL] table
    sql_rows = _analyze_sql(sql_cfg)
    sql_table = _section_table(
        'cpf-sql', 'SQL Engine',
        '[SQL]', sql_rows,
    )

    # [WorkQueues] table
    wq_rows = _analyze_workqueues(wq_cfg)
    wq_table = _section_table(
        'cpf-wq', 'Work Queues',
        '[WorkQueues]', wq_rows,
    ) if wq_rows else ''

    # [ECP] table
    ecp_rows, _ = _analyze_ecp(ecp_cfg)
    ecp_table = _section_table(
        'cpf-ecp', 'ECP Configuration',
        '[ECP]', ecp_rows,
    ) if ecp_cfg else ''

    # [Databases] + [Namespaces] table
    db_ns_table = _build_db_ns_table(db_cfg, ns_cfg)

    # Mirror flags
    _, mirror_flags = _analyze_mirror(mirror_cfg)
    all_flags.extend(mirror_flags)

    if not all_flags:
        all_flags.append(_flag('green', 'No significant configuration concerns detected.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:18px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(all_flags) + '</div>'
        + '<!--/INS-->'
    )

    version = sections.get('ConfigFile', {}).get('Version', '')
    product = sections.get('ConfigFile', {}).get('Product', 'IRIS')
    subtitle = f'{product} {version}' if version else product

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">CPF Configuration Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:14px">{subtitle}</div>'
        + cards_html
        + insights_html
        + config_table
        + jrn_table
        + startup_table
        + sql_table
        + (wq_table if wq_table else '')
        + (ecp_table if ecp_table else '')
        + (db_ns_table if db_ns_table else '')
        + '</div>'
    )
