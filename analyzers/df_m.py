"""
Analyzer for the 'df -m' section in Linux pButtons files.

Format: single snapshot, space-separated, values in MiB.
  Filesystem  1M-blocks  Used  Available  Use%  Mounted on

The Filesystem column can contain spaces (long SMB/NFS share paths), so
columns are parsed from the right: the last 5 tokens are the numeric
fields + Use% + mount point, and everything before them is the filesystem.
"""
import re
import plotly.graph_objects as go

_USE_PCT_RE = re.compile(r'(\d+)%$')

# Filesystem prefixes that indicate virtual/pseudo filesystems to skip
_VIRTUAL_FS = ('devtmpfs', 'tmpfs', 'udev', 'none', 'sysfs', 'proc', 'cgroup')

# IRIS-relevant mount path fragments
_IRIS_PATHS = ('iris', 'cache', 'ensemble', 'healthshare', 'hs-', '/mgr', '/db', '/jrn', '/sys')


def _parse_df(text: str) -> list[dict]:
    lines = text.splitlines()
    # Find header line
    hdr_idx = None
    for i, ln in enumerate(lines):
        if re.search(r'1[mM]-blocks|1M-blocks', ln):
            hdr_idx = i
            break
    if hdr_idx is None:
        return []

    rows = []
    for ln in lines[hdr_idx + 1:]:
        if not ln.strip() or ln.startswith('<'):
            continue
        parts = ln.split()
        # Need at least: filesystem + 1M-blocks + used + available + use% + mountpoint
        if len(parts) < 6:
            continue
        # Parse from the right: mountpoint, use%, available, used, 1M-blocks
        try:
            mountpoint  = parts[-1]
            use_pct_str = parts[-2]
            available   = int(parts[-3])
            used        = int(parts[-4])
            total       = int(parts[-5])
            filesystem  = ' '.join(parts[:-5])
        except (ValueError, IndexError):
            continue

        m = _USE_PCT_RE.search(use_pct_str)
        if not m:
            continue
        use_pct = int(m.group(1))

        rows.append({
            'filesystem': filesystem,
            'total':      total,
            'used':       used,
            'available':  available,
            'use_pct':    use_pct,
            'mountpoint': mountpoint,
        })
    return rows


def _is_virtual(fs: str) -> bool:
    return any(fs.startswith(v) for v in _VIRTUAL_FS)


def _is_iris_path(mp: str) -> bool:
    mp_lower = mp.lower()
    return any(p in mp_lower for p in _IRIS_PATHS)


def _fmt_mb(mb: int) -> str:
    if mb >= 1024 * 1024:
        return f'{mb / (1024 * 1024):.1f} TB'
    if mb >= 1024:
        return f'{mb / 1024:.1f} GB'
    return f'{mb} MB'


def _use_pct_color(pct: int) -> str:
    if pct >= 90:
        return '#ef4444'
    if pct >= 75:
        return '#f59e0b'
    return '#22c55e'


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


async def analyze(section_text: str) -> str:
    rows = _parse_df(section_text)
    if not rows:
        return ''

    real = [r for r in rows if not _is_virtual(r['filesystem'])]
    if not real:
        return ''

    # Sort by total size descending for the chart (top 15)
    chart_rows = sorted(real, key=lambda r: r['total'], reverse=True)[:15]

    # ── Insights ─────────────────────────────────────────────────────────────────
    flags = []
    critical = [r for r in real if r['use_pct'] >= 90]
    warning  = [r for r in real if 75 <= r['use_pct'] < 90]

    for r in sorted(critical, key=lambda x: x['use_pct'], reverse=True):
        iris_note = ' (IRIS path)' if _is_iris_path(r['mountpoint']) else ''
        flags.append(_flag('red',
            f'<b>{r["mountpoint"]}{iris_note} is {r["use_pct"]}% full</b> — '
            f'{_fmt_mb(r["available"])} free of {_fmt_mb(r["total"])}.'))

    for r in sorted(warning, key=lambda x: x['use_pct'], reverse=True):
        iris_note = ' (IRIS path)' if _is_iris_path(r['mountpoint']) else ''
        flags.append(_flag('amber',
            f'<b>{r["mountpoint"]}{iris_note} is {r["use_pct"]}% full</b> — '
            f'{_fmt_mb(r["available"])} free of {_fmt_mb(r["total"])}.'))

    if not flags:
        flags.append(_flag('green', 'All filesystems are below 75% capacity.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:14px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(flags) + '</div>'
        + '<!--/INS-->'
    )

    # ── Stat cards ────────────────────────────────────────────────────────────────
    total_used_mb  = sum(r['used']  for r in real)
    total_total_mb = sum(r['total'] for r in real)
    n_critical = len(critical)
    n_warning  = len(warning)

    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + _stat('Filesystems', str(len(real)))
        + _stat('Total capacity', _fmt_mb(total_total_mb))
        + _stat('Total used', _fmt_mb(total_used_mb))
        + _stat('≥90% full', str(n_critical))
        + _stat('75–89% full', str(n_warning))
        + '</div>'
    )

    # ── Bar chart: used vs available for top N by size ────────────────────────────
    mounts    = [r['mountpoint'] for r in chart_rows]
    used_vals = [r['used']       for r in chart_rows]
    free_vals = [r['available']  for r in chart_rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='Used',
        y=mounts, x=used_vals, orientation='h',
        marker_color='#0055aa',
        hovertemplate='<b>%{y}</b><br>Used: %{x:,} MB<extra></extra>',
    ))
    fig.add_trace(go.Bar(
        name='Available',
        y=mounts, x=free_vals, orientation='h',
        marker_color='#bbdefb',
        hovertemplate='<b>%{y}</b><br>Available: %{x:,} MB<extra></extra>',
    ))
    fig.update_layout(
        barmode='stack',
        title_text='Disk Usage by Mount Point (MB)',
        title_font_size=11,
        height=max(220, 30 * len(chart_rows) + 100),
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='white',
        plot_bgcolor='#f8f9fc',
        font=dict(family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size=10),
        xaxis=dict(title='MB', showgrid=True, gridcolor='#e8edf5'),
        yaxis=dict(autorange='reversed'),
        legend=dict(orientation='h', x=0, y=-0.08, font_size=10),
    )
    chart_html = fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={'displayModeBar': False},
    )

    # ── Full table ────────────────────────────────────────────────────────────────
    table_rows = sorted(real, key=lambda r: r['use_pct'], reverse=True)
    th_style = ('padding:5px 10px;text-align:left;font-size:0.72rem;font-weight:700;'
                'color:#555;text-transform:uppercase;letter-spacing:.05em;'
                'border-bottom:2px solid #dde3ee;white-space:nowrap')
    headers = ['Mount Point', 'Size', 'Used', 'Available', 'Use%', 'Filesystem']
    ths = ''.join(f'<th style="{th_style}">{h}</th>' for h in headers)

    tbody = ''
    for i, r in enumerate(table_rows):
        bg = '#f8f9fc' if i % 2 == 0 else 'white'
        pct_color = _use_pct_color(r['use_pct'])
        pct_badge = (f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;'
                     f'background:{pct_color};color:white;font-weight:700;font-size:0.75rem">'
                     f'{r["use_pct"]}%</span>')
        fs_display = r['filesystem']
        if len(fs_display) > 48:
            fs_display = f'<span title="{fs_display}">{fs_display[:47]}…</span>'

        td = lambda val, align='left': (
            f'<td style="padding:4px 10px;font-size:0.78rem;color:#222;'
            f'text-align:{align};white-space:nowrap">{val}</td>'
        )
        tbody += (
            f'<tr style="background:{bg}">'
            + td(r['mountpoint'])
            + td(_fmt_mb(r['total']), 'right')
            + td(_fmt_mb(r['used']),  'right')
            + td(_fmt_mb(r['available']), 'right')
            + td(pct_badge, 'center')
            + f'<td style="padding:4px 10px;font-size:0.78rem;color:#222;white-space:normal;word-break:break-all">{fs_display}</td>'
            + '</tr>'
        )

    table_html = (
        f'<table style="border-collapse:collapse;width:100%;margin-bottom:16px">'
        f'<thead><tr>{ths}</tr></thead><tbody>{tbody}</tbody></table>'
    )

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">df -m Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">'
        f'{len(real)} real filesystems ({len(rows) - len(real)} virtual excluded)</div>'
        + insights_html
        + stats_html
        + chart_html
        + '<div style="font-size:0.78rem;font-weight:600;color:#333;margin:14px 0 6px 0">'
        'All Filesystems</div>'
        + table_html
        + '</div>'
    )
