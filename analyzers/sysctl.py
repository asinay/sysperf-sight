"""
Analyzer for the 'sysctl -a' section in Linux pButtons files.

Produces a compliance table (current vs. recommended) for parameters
that directly affect IRIS/Caché performance, plus insight flags for
critical misconfigurations.
"""
import re


def _parse_sysctl(text: str) -> dict[str, str]:
    kv = {}
    for line in text.splitlines():
        m = re.match(r'^([\w./\-]+)\s*=\s*(.+)', line)
        if m:
            kv[m.group(1).strip()] = m.group(2).strip()
    return kv


def _int(kv: dict, key: str) -> int | None:
    v = kv.get(key)
    if v is None:
        return None
    try:
        return int(v.split()[0])
    except (ValueError, IndexError):
        return None


def _insight(level: str, text: str) -> str:
    cfg = {
        'red':   ('#fef2f2', '#dc2626', '✖'),
        'amber': ('#fffbeb', '#d97706', '⚠'),
        'info':  ('#eff6ff', '#2563eb', 'ℹ'),
        'green': ('#f0fdf4', '#16a34a', '✔'),
    }
    bg, fg, icon = cfg.get(level, cfg['info'])
    return (
        f'<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;'
        f'background:{bg};border-left:3px solid {fg};border-radius:4px;margin-bottom:6px">'
        f'<span style="color:{fg};font-size:1rem;flex-shrink:0">{icon}</span>'
        f'<span style="font-size:0.8rem;color:#1a1a2e;line-height:1.5">{text}</span></div>'
    )


def _row(param: str, current: str, recommended: str, status: str, note: str) -> str:
    color = {'ok': '#16a34a', 'warn': '#d97706', 'bad': '#dc2626', 'info': '#2563eb'}.get(status, '#555')
    icon  = {'ok': '✔', 'warn': '⚠', 'bad': '✖', 'info': 'ℹ'}.get(status, '·')
    bg    = {'ok': '#f0fdf4', 'warn': '#fffbeb', 'bad': '#fef2f2', 'info': '#eff6ff'}.get(status, '#fff')
    return (
        f'<tr style="background:{bg};border-bottom:1px solid #f0f2f5">'
        f'<td style="padding:7px 12px;font-size:0.78rem;font-family:monospace;white-space:nowrap;color:#334">{param}</td>'
        f'<td style="padding:7px 12px;font-size:0.78rem;font-family:monospace;color:#1a1a2e">{current}</td>'
        f'<td style="padding:7px 12px;font-size:0.78rem;font-family:monospace;color:#556">{recommended}</td>'
        f'<td style="padding:7px 12px;font-size:0.8rem;color:{color};text-align:center;white-space:nowrap">'
        f'<span style="font-size:0.9rem">{icon}</span></td>'
        f'<td style="padding:7px 12px;font-size:0.75rem;color:#667">{note}</td>'
        f'</tr>'
    )


async def analyze(section_text: str) -> str:
    kv = _parse_sysctl(section_text)
    if not kv:
        return ''

    insights = []
    table_rows = []

    # ── vm.swappiness ─────────────────────────────────────────────────────────
    swappiness = _int(kv, 'vm.swappiness')
    if swappiness is not None:
        if swappiness <= 1:
            s, note = 'ok', 'Optimal for database workloads — OS will not evict file cache to free RAM for anonymous pages.'
        elif swappiness <= 10:
            s, note = 'warn', 'Slightly elevated — OS may swap under memory pressure. Recommended: 1.'
        else:
            s, note = 'bad', 'High swappiness — OS will aggressively swap IRIS buffers out to disk under load.'
        table_rows.append(_row('vm.swappiness', str(swappiness), '1', s, note))
        if swappiness > 10:
            insights.append(_insight('red',
                f'<b>vm.swappiness = {swappiness}</b> — the OS will swap IRIS global buffer pages to disk under memory pressure. '
                f'Set to 1: <code>echo 1 > /proc/sys/vm/swappiness</code> and persist in <code>/etc/sysctl.conf</code>.'))

    # ── vm.dirty_ratio / vm.dirty_background_ratio ────────────────────────────
    dirty_ratio = _int(kv, 'vm.dirty_ratio')
    dirty_bg    = _int(kv, 'vm.dirty_background_ratio')

    if dirty_ratio is not None:
        if dirty_ratio <= 15:
            s, note = 'ok', 'Writeback triggered before large dirty page accumulation — limits latency spikes.'
        elif dirty_ratio <= 25:
            s, note = 'warn', 'Moderate. Occasional write bursts when threshold is hit. Recommended: ≤15.'
        else:
            s, note = 'bad', 'High — large dirty page batches cause periodic I/O stalls visible as mgstat PhyWrs spikes.'
        table_rows.append(_row('vm.dirty_ratio', str(dirty_ratio), '≤15', s, note))
        if dirty_ratio > 25:
            insights.append(_insight('amber',
                f'<b>vm.dirty_ratio = {dirty_ratio}</b> — large dirty page batches will be flushed in bursts, '
                f'causing periodic write latency spikes. Correlate with sar -d await spikes. Recommended: 10–15.'))

    if dirty_bg is not None:
        if dirty_bg <= 5:
            s, note = 'ok', 'Background writeback starts early — keeps dirty page pressure low.'
        elif dirty_bg <= 10:
            s, note = 'warn', 'Slightly high. Recommended: 3–5.'
        else:
            s, note = 'bad', 'High — background flusher waits too long before starting writes.'
        table_rows.append(_row('vm.dirty_background_ratio', str(dirty_bg), '3–5', s, note))

    # ── vm.overcommit_memory ──────────────────────────────────────────────────
    overcommit = _int(kv, 'vm.overcommit_memory')
    if overcommit is not None:
        if overcommit == 2:
            s, note = 'bad', 'Strict overcommit — IRIS processes can be OOM-killed if committed memory exceeds limit.'
            insights.append(_insight('red',
                f'<b>vm.overcommit_memory = 2</b> — strict overcommit mode. If committed virtual memory exceeds '
                f'(RAM × overcommit_ratio / 100 + swap), new allocations fail and IRIS processes may be OOM-killed. '
                f'Recommended: 0 (heuristic) for IRIS.'))
        elif overcommit == 0:
            s, note = 'ok', 'Heuristic overcommit — standard default, safe for IRIS.'
        else:
            s, note = 'info', 'Always overcommit — fine for IRIS but means OOM killer is the only guard.'
        table_rows.append(_row('vm.overcommit_memory', str(overcommit), '0', s, note))

    # ── kernel.numa_balancing ─────────────────────────────────────────────────
    numa_bal = _int(kv, 'kernel.numa_balancing')
    if numa_bal is not None:
        if numa_bal == 0:
            s, note = 'ok', 'NUMA auto-balancing disabled — prevents OS from migrating IRIS buffer pages across NUMA nodes.'
        else:
            s, note = 'bad', 'NUMA auto-balancing enabled — OS will migrate pages across NUMA nodes, causing random latency spikes.'
        table_rows.append(_row('kernel.numa_balancing', str(numa_bal), '0', s, note))
        if numa_bal != 0:
            insights.append(_insight('red',
                f'<b>kernel.numa_balancing = {numa_bal}</b> — the OS will automatically migrate memory pages between NUMA nodes. '
                f'For IRIS, this causes unpredictable latency as buffer pages are moved away from the accessing CPU node. '
                f'Set to 0: <code>echo 0 > /proc/sys/kernel/numa_balancing</code>.'))

    # ── vm.nr_hugepages ───────────────────────────────────────────────────────
    hugepages = _int(kv, 'vm.nr_hugepages')
    if hugepages is not None:
        if hugepages == 0:
            s, note = 'warn', 'Huge pages not configured — IRIS uses standard 4 kB pages, increasing TLB pressure on large buffer pools.'
            insights.append(_insight('amber',
                '<b>vm.nr_hugepages = 0</b> — huge pages (2 MB) are not configured. '
                'For large IRIS global buffer pools, huge pages reduce TLB misses and can improve throughput. '
                'InterSystems recommends allocating nr_hugepages = (global buffer pool size in MB) / 2. '
                'Requires IRIS restart after configuration.'))
        else:
            s, note = 'ok', f'{hugepages} × 2 MB = {hugepages * 2:,} MB reserved for huge pages.'
        table_rows.append(_row('vm.nr_hugepages', str(hugepages), '≥ bufpool_mb/2', s, note))

    # ── kernel.shmmax ─────────────────────────────────────────────────────────
    shmmax = _int(kv, 'kernel.shmmax')
    if shmmax is not None:
        shmmax_gb = shmmax / 1024**3
        if shmmax_gb >= 1:
            s, note = 'ok', f'{shmmax_gb:.1f} GB — large enough for most IRIS shared memory segments.'
        else:
            s, note = 'bad', f'Only {shmmax / 1024**2:.0f} MB — too small; IRIS shared memory allocation will fail.'
            insights.append(_insight('red',
                f'<b>kernel.shmmax = {shmmax:,} ({shmmax/1024**2:.0f} MB)</b> — the maximum shared memory segment size is too small. '
                f'IRIS requires shmmax ≥ global buffer pool size. Instance startup will fail if the buffer pool exceeds this value.'))
        table_rows.append(_row('kernel.shmmax', f'{shmmax_gb:.2f} GB', '≥ bufpool size', s, note))

    # ── kernel.sem ────────────────────────────────────────────────────────────
    sem = kv.get('kernel.sem')
    if sem:
        parts = sem.split()
        try:
            semmsl, semmns, semopm, semmni = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
            ok = semmsl >= 250 and semmns >= 32000 and semopm >= 100 and semmni >= 128
            if ok:
                s, note = 'ok', 'Meets IRIS minimum semaphore requirements (250 32000 100 128).'
            else:
                s, note = 'bad', 'Below IRIS minimum — instance startup or process creation may fail under load.'
                insights.append(_insight('red',
                    f'<b>kernel.sem = {sem}</b> — semaphore limits are below InterSystems minimums (250 32000 100 128). '
                    f'This can cause IRIS process creation failures. '
                    f'Set: <code>kernel.sem = 250 32000 100 128</code> in /etc/sysctl.conf.'))
            table_rows.append(_row('kernel.sem', sem, '250 32000 100 128', s, note))
        except (ValueError, IndexError):
            table_rows.append(_row('kernel.sem', sem, '250 32000 100 128', 'info', 'Could not parse — verify manually.'))

    # ── fs.file-max ───────────────────────────────────────────────────────────
    file_max = _int(kv, 'fs.file-max')
    if file_max is not None:
        if file_max >= 1_000_000:
            s, note = 'ok', f'{file_max:,} — adequate for high-concurrency IRIS workloads.'
        elif file_max >= 100_000:
            s, note = 'warn', f'{file_max:,} — may be insufficient under high load. Recommended: ≥ 1,000,000.'
        else:
            s, note = 'bad', f'{file_max:,} — very low; risk of "too many open files" errors under load.'
            insights.append(_insight('red',
                f'<b>fs.file-max = {file_max:,}</b> — the system-wide open file limit is very low. '
                f'Under concurrent IRIS load this causes "too many open files" errors. '
                f'Recommended: ≥ 1,000,000.'))
        table_rows.append(_row('fs.file-max', f'{file_max:,}', '≥ 1,000,000', s, note))

    # ── net.core.somaxconn ────────────────────────────────────────────────────
    somaxconn = _int(kv, 'net.core.somaxconn')
    if somaxconn is not None:
        if somaxconn >= 1024:
            s, note = 'ok', 'Adequate TCP accept backlog for high-concurrency workloads.'
        elif somaxconn >= 512:
            s, note = 'warn', 'Moderate. Under burst connection load, clients may see connection resets. Recommended: ≥ 1024.'
        else:
            s, note = 'bad', 'Low TCP accept backlog — connection resets likely under concurrent load spikes.'
            insights.append(_insight('amber',
                f'<b>net.core.somaxconn = {somaxconn}</b> — the TCP listen backlog is small. '
                f'During connection bursts, the kernel will drop incoming connections before IRIS accepts them. '
                f'Recommended: ≥ 1024.'))
        table_rows.append(_row('net.core.somaxconn', str(somaxconn), '≥ 1024', s, note))

    # ── net.ipv4.tcp_max_syn_backlog ──────────────────────────────────────────
    syn_backlog = _int(kv, 'net.ipv4.tcp_max_syn_backlog')
    if syn_backlog is not None:
        if syn_backlog >= 1024:
            s, note = 'ok', 'Sufficient SYN backlog.'
        else:
            s, note = 'warn', 'Low SYN backlog — connection failures under high concurrency. Recommended: ≥ 1024.'
        table_rows.append(_row('net.ipv4.tcp_max_syn_backlog', str(syn_backlog), '≥ 1024', s, note))

    # ── kernel.pid_max ────────────────────────────────────────────────────────
    pid_max = _int(kv, 'kernel.pid_max')
    if pid_max is not None:
        if pid_max >= 65536:
            s, note = 'ok', 'Sufficient PID space for IRIS processes and OS daemons.'
        else:
            s, note = 'warn', 'Low PID limit — may be exhausted on busy systems with many short-lived processes.'
        table_rows.append(_row('kernel.pid_max', f'{pid_max:,}', '≥ 65,536', s, note))

    if not table_rows:
        return ''

    # ── Assemble ──────────────────────────────────────────────────────────────
    if not insights:
        insights.append(_insight('green', 'No critical kernel parameter misconfigurations detected for IRIS workloads.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:16px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:8px">Insights</div>'
        + ''.join(insights) + '</div>'
        + '<!--/INS-->'
    )

    header_row = (
        '<tr style="background:#f0f2f5;border-bottom:2px solid #dde3ee">'
        '<th style="padding:8px 12px;font-size:0.72rem;color:#555;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Parameter</th>'
        '<th style="padding:8px 12px;font-size:0.72rem;color:#555;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Current</th>'
        '<th style="padding:8px 12px;font-size:0.72rem;color:#555;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Recommended</th>'
        '<th style="padding:8px 12px;font-size:0.72rem;color:#555;text-align:center;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Status</th>'
        '<th style="padding:8px 12px;font-size:0.72rem;color:#555;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Notes</th>'
        '</tr>'
    )
    table_html = (
        '<div style="overflow-x:auto;margin-bottom:16px">'
        '<table style="border-collapse:collapse;width:100%;background:#fff;border:1px solid #dde3ee;border-radius:8px;overflow:hidden">'
        f'{header_row}{"".join(table_rows)}'
        '</table></div>'
    )

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:12px;'
        'text-transform:uppercase;letter-spacing:.06em">sysctl -a Analysis</div>'
        + insights_html
        + table_html
        + '</div>'
    )
