"""
Analyzer for the 'ps' section (ps -elfy) in Linux pButtons files.

Each sample is a full snapshot separated by "sample N of M" markers.
Columns (fixed-width, space-delimited):
  S UID PID PPID C PRI NI RSS SZ WCHAN STIME TTY TIME CMD
RSS is in KB. Kernel threads have CMD wrapped in [...] and RSS=0.
IRIS processes run as the IRIS service user (irisusr or similar) and
their CMD is the irisdb binary, with job type in trailing args.
"""
import re
import plotly.graph_objects as go

_HEADER_RE = re.compile(r'^\s*S\s+UID\s+PID\s+PPID\s+C\s+PRI', re.MULTILINE)
_SAMPLE_SEP = re.compile(r'sample\s+\d+\s+of\s+\d+')

# Extract job type from irisdb CMD like: -cj -p26 domulti^SystemPerformance
_IRIS_JOB_RE = re.compile(r'-cj\s+-p\d+\s+(\S+)')


def _parse_ps(text: str) -> list[dict]:
    """Return list of process dicts parsed from one ps -elfy snapshot."""
    lines = text.splitlines()
    hdr_line = None
    data_start = 0
    for i, ln in enumerate(lines):
        if _HEADER_RE.match(ln):
            hdr_line = ln
            data_start = i + 1
            break
    if hdr_line is None:
        return []

    procs = []
    for ln in lines[data_start:]:
        # Stop at section separators or empty/HTML lines
        if not ln or ln.startswith('<') or _SAMPLE_SEP.search(ln):
            break
        parts = ln.split()
        if len(parts) < 13:
            continue
        try:
            rss = int(parts[7])
            pid = int(parts[2])
        except ValueError:
            continue
        cmd = ' '.join(parts[13:]) if len(parts) > 13 else parts[12] if len(parts) == 13 else ''
        procs.append({
            'state': parts[0],
            'uid':   parts[1],
            'pid':   pid,
            'rss':   rss,
            'time':  parts[12],
            'cmd':   cmd,
        })
    return procs


def _split_samples(text: str) -> list[str]:
    """Split the section text into per-sample blocks."""
    parts = _SAMPLE_SEP.split(text)
    return [p for p in parts if _HEADER_RE.search(p)]


def _is_kernel_thread(cmd: str) -> bool:
    return cmd.startswith('[') and cmd.endswith(']')


def _is_iris(uid: str, cmd: str) -> bool:
    return 'irisdb' in cmd or 'iris' in uid.lower()


def _iris_job_type(cmd: str) -> str:
    m = _IRIS_JOB_RE.search(cmd)
    if m:
        return m.group(1)
    if 'irisdb' in cmd:
        return 'irisdb (other)'
    return 'other'


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


def _stat(label: str, value: str, unit: str = '') -> str:
    return (f'<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;'
            f'padding:10px 14px;min-width:100px">'
            f'<div style="font-size:0.68rem;color:#888;text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:3px">{label}</div>'
            f'<div style="font-size:1.1rem;font-weight:700;color:#1a1a2e">'
            f'{value}<span style="font-size:0.75rem;font-weight:400;color:#888;'
            f'margin-left:3px">{unit}</span></div></div>')


def _fmt_rss(kb: int) -> str:
    if kb >= 1024:
        return f'{kb / 1024:.0f} MB'
    return f'{kb} KB'


def _truncate_cmd(cmd: str, max_len: int = 72) -> str:
    if len(cmd) <= max_len:
        return cmd
    return cmd[:max_len - 1] + '…'


def _table(headers: list[str], rows: list[list[str]], col_align: list[str] | None = None) -> str:
    if not rows:
        return ''
    col_align = col_align or ['left'] * len(headers)
    th_style = ('padding:5px 10px;text-align:left;font-size:0.72rem;font-weight:700;'
                'color:#555;text-transform:uppercase;letter-spacing:.05em;'
                'border-bottom:2px solid #dde3ee;white-space:nowrap')
    ths = ''.join(f'<th style="{th_style}">{h}</th>' for h in headers)
    tbody = ''
    for i, row in enumerate(rows):
        bg = '#f8f9fc' if i % 2 == 0 else 'white'
        tds = ''
        for j, cell in enumerate(row):
            align = col_align[j] if j < len(col_align) else 'left'
            td_style = (f'padding:4px 10px;font-size:0.78rem;color:#222;'
                        f'text-align:{align};white-space:nowrap')
            if j == len(row) - 1:
                td_style = td_style.replace('white-space:nowrap', 'white-space:normal;word-break:break-all')
            tds += f'<td style="{td_style}">{cell}</td>'
        tbody += f'<tr style="background:{bg}">{tds}</tr>'
    return (f'<table style="border-collapse:collapse;width:100%;margin-bottom:16px">'
            f'<thead><tr>{ths}</tr></thead><tbody>{tbody}</tbody></table>')


async def analyze(section_text: str) -> str:
    samples = _split_samples(section_text)
    if not samples:
        return ''

    # Use first snapshot as primary; last for comparison
    first_procs = _parse_ps(samples[0])
    last_procs  = _parse_ps(samples[-1]) if len(samples) > 1 else first_procs

    if not first_procs:
        return ''

    n_samples  = len(samples)
    n_total    = len(first_procs)
    n_dstate   = sum(1 for p in first_procs if p['state'] == 'D')
    iris_procs = [p for p in first_procs if _is_iris(p['uid'], p['cmd'])]
    n_iris     = len(iris_procs)
    iris_rss_mb = sum(p['rss'] for p in iris_procs) // 1024

    # ── Insights ────────────────────────────────────────────────────────────────
    flags = []

    if n_dstate > 0:
        flags.append(_flag('amber',
            f'<b>{n_dstate} process{"es" if n_dstate > 1 else ""} in uninterruptible I/O wait (D state)</b> '
            f'at snapshot time — indicates disk or NFS pressure. Cross-reference with iostat %util and await.'))

    if n_samples > 1:
        n_iris_last = sum(1 for p in last_procs if _is_iris(p['uid'], p['cmd']))
        if n_iris_last != n_iris:
            flags.append(_flag('info',
                f'IRIS process count changed between first and last snapshot: '
                f'{n_iris} → {n_iris_last}. A process may have started or crashed during the run.'))

    if not flags:
        flags.append(_flag('green', f'No D-state processes detected at snapshot time.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:14px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(flags) + '</div>'
        + '<!--/INS-->'
    )

    # ── Stat cards ───────────────────────────────────────────────────────────────
    user_procs = [p for p in first_procs if not _is_kernel_thread(p['cmd'])]
    total_user_rss_mb = sum(p['rss'] for p in user_procs) // 1024

    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + _stat('Total processes', str(n_total))
        + _stat('User-space processes', str(len(user_procs)))
        + _stat('IRIS processes', str(n_iris))
        + _stat('IRIS RSS', str(iris_rss_mb), 'MB')
        + _stat('D-state', str(n_dstate))
        + _stat('Snapshots', str(n_samples))
        + '</div>'
    )

    # ── RSS by user bar chart ────────────────────────────────────────────────────
    rss_by_user: dict[str, int] = {}
    for p in user_procs:
        rss_by_user[p['uid']] = rss_by_user.get(p['uid'], 0) + p['rss']

    sorted_users = sorted(rss_by_user.items(), key=lambda x: x[1], reverse=True)[:12]
    users  = [u for u, _ in sorted_users]
    rss_mb = [kb // 1024 for _, kb in sorted_users]

    fig = go.Figure(go.Bar(
        x=rss_mb, y=users, orientation='h',
        marker_color='#0055aa',
        hovertemplate='<b>%{y}</b>: %{x:,} MB<extra></extra>',
    ))
    fig.update_layout(
        title_text='RSS by User (MB)',
        title_font_size=11,
        height=max(200, 32 * len(users) + 80),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='white',
        plot_bgcolor='#f8f9fc',
        font=dict(family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size=10),
        xaxis=dict(title='MB', showgrid=True, gridcolor='#e8edf5'),
        yaxis=dict(autorange='reversed'),
    )
    chart_html = fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={'displayModeBar': False},
    )

    # ── Top 15 processes by RSS ──────────────────────────────────────────────────
    top_procs = sorted(
        [p for p in user_procs],
        key=lambda p: p['rss'], reverse=True
    )[:15]

    top_rows = [
        [p['state'], p['uid'], str(p['pid']), _fmt_rss(p['rss']),
         p['time'], _truncate_cmd(p['cmd'])]
        for p in top_procs
    ]
    top_table = _table(
        ['S', 'User', 'PID', 'RSS', 'CPU Time', 'Command'],
        top_rows,
        ['left', 'left', 'right', 'right', 'right', 'left'],
    )

    # ── IRIS job breakdown ───────────────────────────────────────────────────────
    if iris_procs:
        job_counts: dict[str, dict] = {}
        for p in iris_procs:
            jt = _iris_job_type(p['cmd'])
            if jt not in job_counts:
                job_counts[jt] = {'count': 0, 'rss': 0}
            job_counts[jt]['count'] += 1
            job_counts[jt]['rss'] += p['rss']

        iris_rows = sorted(job_counts.items(), key=lambda x: x[1]['count'], reverse=True)
        iris_table_rows = [
            [jt, str(d['count']), _fmt_rss(d['rss'])]
            for jt, d in iris_rows
        ]
        iris_table_html = (
            '<div style="font-size:0.78rem;font-weight:600;color:#333;margin-bottom:6px">'
            'IRIS Job Types</div>'
            + _table(
                ['Job Type / Routine', 'Count', 'Total RSS'],
                iris_table_rows,
                ['left', 'right', 'right'],
            )
        )
    else:
        iris_table_html = ''

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">ps Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">'
        f'{n_total} processes · {n_samples} snapshot{"s" if n_samples != 1 else ""}</div>'
        + insights_html
        + stats_html
        + chart_html
        + '<div style="margin:14px 0 6px 0">'
        '<span style="font-size:0.78rem;font-weight:600;color:#333">Top Processes by RSS</span>'
        '<span style="font-size:0.72rem;color:#888;margin-left:8px">'
        'Resident Set Size — physical RAM currently held by the process (excludes swap)</span>'
        '</div>'
        + top_table
        + iris_table_html
        + '</div>'
    )
