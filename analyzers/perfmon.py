"""
Analyzer for the 'perfmon' section in Windows pButtons files.

Expected format: PDH-CSV export from logman.
  Header: "(PDH-CSV 4.0) (timezone)(offset)","\\\\HOST\\Object(instance)\\counter",...
  Data:   "MM/DD/YYYY HH:MM:SS.mmm"," value",...

Returns '' when logman failed to collect data (access denied, etc.).
"""
import io
import re
import csv
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_PDH_RE = re.compile(r'\bPDH-CSV\b', re.IGNORECASE)

# (object_substring, counter_substring) → logical column name.
# Object match is against the object+instance part (e.g. "processor(_total)").
# First match wins; _Total instances are preferred over specific ones.
_COUNTER_MAP = [
    ('processor',        '% processor time',          'cpu_total'),
    ('processor',        '% privileged time',         'cpu_kernel'),
    ('processor',        '% user time',               'cpu_user'),
    ('processor',        '% interrupt time',          'cpu_interrupt'),
    ('memory',           'available mbytes',          'mem_avail'),
    ('memory',           'pages/sec',                 'mem_pages'),
    ('memory',           '% committed bytes in use',  'mem_commit_pct'),
    ('physicaldisk',     '% disk time',               'disk_busy'),
    ('physicaldisk',     'disk reads/sec',            'disk_rps'),
    ('physicaldisk',     'disk writes/sec',           'disk_wps'),
    ('physicaldisk',     'disk read bytes/sec',       'disk_rbytes'),
    ('physicaldisk',     'disk write bytes/sec',      'disk_wbytes'),
    ('physicaldisk',     'avg. disk queue length',    'disk_queue'),
    ('physicaldisk',     'avg. disk sec/read',        'disk_rlatency'),
    ('physicaldisk',     'avg. disk sec/write',       'disk_wlatency'),
    ('system',           'processor queue length',    'proc_queue'),
    ('network interface', 'bytes total/sec',          'net_bytes'),
    ('network interface', 'bytes sent/sec',           'net_sent'),
    ('network interface', 'bytes received/sec',       'net_recv'),
]


def _match_counter(path: str) -> str | None:
    """Map a PDH counter path to a logical column name."""
    # Path: \\HOSTNAME\Object(Instance)\Counter  or  \\HOSTNAME\Object\Counter
    parts = [p for p in path.split('\\') if p]
    if len(parts) < 2:
        return None
    obj_inst = parts[-2].lower()   # e.g. "processor(_total)"
    counter  = parts[-1].lower()   # e.g. "% processor time"
    for obj_sub, ctr_sub, logical in _COUNTER_MAP:
        if obj_sub in obj_inst and ctr_sub in counter:
            return logical
    return None


def _parse_perfmon(text: str) -> pd.DataFrame | None:
    lines = text.splitlines()
    header_idx = next((i for i, ln in enumerate(lines) if _PDH_RE.search(ln)), None)
    if header_idx is None:
        return None

    try:
        reader = csv.reader(io.StringIO('\n'.join(lines[header_idx:])))
        headers = next(reader)
    except Exception:
        return None

    if not headers:
        return None

    # Build idx_to_logical: prefer _Total over named instances
    assigned: dict[str, int] = {}   # logical → csv_col_index
    for i, h in enumerate(headers[1:], start=1):
        logical = _match_counter(h)
        if logical is None:
            continue
        is_total = '_total' in h.lower()
        if logical not in assigned or is_total:
            assigned[logical] = i

    idx_to_logical = {v: k for k, v in assigned.items()}  # csv_col_index → logical
    if not idx_to_logical:
        return None

    records = []
    for row in reader:
        if not row or not row[0].strip():
            continue
        ts_raw = row[0].strip()
        for fmt in ('%m/%d/%Y %H:%M:%S.%f', '%m/%d/%Y %H:%M:%S'):
            try:
                ts = pd.to_datetime(ts_raw, format=fmt)
                break
            except Exception:
                pass
        else:
            continue

        rec: dict = {'dt': ts}
        for col_idx, logical in idx_to_logical.items():
            if col_idx < len(row):
                try:
                    rec[logical] = float(row[col_idx].strip())
                except (ValueError, AttributeError):
                    pass
        records.append(rec)

    if len(records) < 2:
        return None

    df = pd.DataFrame(records).sort_values('dt').reset_index(drop=True)

    if len(df) > 1000:
        step = len(df) // 1000
        df = df.iloc[::step].reset_index(drop=True)

    return df


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
    df = _parse_perfmon(section_text)
    if df is None or df.empty:
        return ''

    n     = len(df)
    dcols = set(df.columns)
    has   = lambda c: c in dcols  # noqa: E731

    # ── Insights ─────────────────────────────────────────────────────────────
    flags = []

    if has('cpu_total'):
        avg = df['cpu_total'].mean()
        pk  = df['cpu_total'].max()
        if avg > 80:
            flags.append(_flag('red',
                f'<b>CPU saturation</b>: avg {avg:.1f}%, peak {pk:.1f}% — '
                f'processor is a bottleneck. Check Process\\% Processor Time for top consumers.'))
        elif avg > 60:
            flags.append(_flag('amber',
                f'<b>Elevated CPU utilization</b>: avg {avg:.1f}%, peak {pk:.1f}%.'))

    if has('proc_queue'):
        avg = df['proc_queue'].mean()
        pk  = df['proc_queue'].max()
        if avg > 4:
            flags.append(_flag('red',
                f'<b>Processor queue backed up</b>: avg {avg:.1f}, peak {pk:.0f} — '
                f'threads are waiting for CPU. Indicates CPU saturation.'))
        elif avg > 2:
            flags.append(_flag('amber',
                f'<b>Processor queue elevated</b>: avg {avg:.1f}, peak {pk:.0f}.'))

    if has('mem_avail'):
        min_avail = df['mem_avail'].min()
        avg_avail = df['mem_avail'].mean()
        if min_avail < 500:
            flags.append(_flag('red',
                f'<b>Low available memory</b>: min {min_avail:.0f} MB — '
                f'risk of excessive paging. Consider increasing RAM or IRIS global buffer settings.'))
        elif min_avail < 1024:
            flags.append(_flag('amber',
                f'<b>Available memory tight</b>: min {min_avail:.0f} MB, avg {avg_avail:.0f} MB.'))

    if has('mem_pages'):
        avg = df['mem_pages'].mean()
        pk  = df['mem_pages'].max()
        if avg > 100:
            flags.append(_flag('red',
                f'<b>High page fault rate</b>: avg {avg:.0f} pages/sec, peak {pk:.0f} — '
                f'system is paging heavily. Memory pressure confirmed.'))
        elif avg > 20:
            flags.append(_flag('amber',
                f'<b>Elevated paging</b>: avg {avg:.0f} pages/sec.'))

    if has('disk_queue'):
        avg = df['disk_queue'].mean()
        pk  = df['disk_queue'].max()
        if avg > 2:
            flags.append(_flag('red',
                f'<b>Disk queue saturation</b>: avg {avg:.1f}, peak {pk:.1f} — '
                f'I/O is queuing up. Storage cannot keep pace with demand.'))
        elif avg > 1:
            flags.append(_flag('amber',
                f'<b>Disk queue elevated</b>: avg {avg:.1f}, peak {pk:.1f}.'))

    if has('disk_rlatency'):
        avg_ms = df['disk_rlatency'].mean() * 1000
        pk_ms  = df['disk_rlatency'].max()  * 1000
        if avg_ms > 20:
            flags.append(_flag('red',
                f'<b>High disk read latency</b>: avg {avg_ms:.1f} ms, peak {pk_ms:.1f} ms — '
                f'storage response is very slow for random reads.'))
        elif avg_ms > 10:
            flags.append(_flag('amber',
                f'<b>Elevated disk read latency</b>: avg {avg_ms:.1f} ms, peak {pk_ms:.1f} ms.'))

    if has('disk_wlatency'):
        avg_ms = df['disk_wlatency'].mean() * 1000
        pk_ms  = df['disk_wlatency'].max()  * 1000
        if avg_ms > 20:
            flags.append(_flag('red',
                f'<b>High disk write latency</b>: avg {avg_ms:.1f} ms, peak {pk_ms:.1f} ms.'))
        elif avg_ms > 10:
            flags.append(_flag('amber',
                f'<b>Elevated disk write latency</b>: avg {avg_ms:.1f} ms, peak {pk_ms:.1f} ms.'))

    if not flags:
        flags.append(_flag('green', 'No significant CPU, memory, or disk pressure detected.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:14px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(flags) + '</div>'
        + '<!--/INS-->'
    )

    # ── Stat cards ────────────────────────────────────────────────────────────
    stat_items = []
    if has('cpu_total'):
        stat_items.append(_stat('CPU avg', f'{df["cpu_total"].mean():.1f}', '%'))
        stat_items.append(_stat('CPU peak', f'{df["cpu_total"].max():.1f}', '%'))
    if has('mem_avail'):
        stat_items.append(_stat('Avail RAM min', f'{df["mem_avail"].min():.0f}', 'MB'))
    if has('mem_commit_pct'):
        stat_items.append(_stat('Mem commit avg', f'{df["mem_commit_pct"].mean():.1f}', '%'))
    if has('disk_queue'):
        stat_items.append(_stat('Disk queue avg', f'{df["disk_queue"].mean():.2f}'))
    if has('disk_rlatency'):
        stat_items.append(_stat('Read latency avg', f'{df["disk_rlatency"].mean()*1000:.1f}', 'ms'))
    if has('disk_wlatency'):
        stat_items.append(_stat('Write latency avg', f'{df["disk_wlatency"].mean()*1000:.1f}', 'ms'))

    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + ''.join(stat_items) + '</div>'
    ) if stat_items else ''

    # ── Charts ────────────────────────────────────────────────────────────────
    # Each entry: (title, y_label, [(col, color, name, transform_fn)])
    row_defs = []

    # CPU: single % Processor Time or stacked user+kernel if available
    cpu_traces = []
    if has('cpu_total'):
        cpu_traces.append(('cpu_total',   '#0055aa', '% Processor Time', None))
    if has('cpu_user'):
        cpu_traces.append(('cpu_user',    '#27ae60', '% User Time', None))
    if has('cpu_kernel'):
        cpu_traces.append(('cpu_kernel',  '#e67e22', '% Privileged Time', None))
    if has('cpu_interrupt'):
        cpu_traces.append(('cpu_interrupt', '#e74c3c', '% Interrupt Time', None))
    if cpu_traces:
        row_defs.append(('CPU Utilization (%)', '%', cpu_traces))

    if has('proc_queue'):
        row_defs.append(('Processor Queue Length', 'threads', [
            ('proc_queue', '#e74c3c', 'Processor Queue Length', None),
        ]))

    # Memory
    mem_traces = []
    if has('mem_avail'):
        mem_traces.append(('mem_avail', '#27ae60', 'Available MBytes', None))
    if mem_traces:
        row_defs.append(('Memory — Available MBytes', 'MB', mem_traces))

    if has('mem_pages'):
        row_defs.append(('Paging Activity (pages/sec)', 'pages/sec', [
            ('mem_pages', '#e74c3c', 'Pages/sec', None),
        ]))

    # Disk % busy and queue
    disk_busy_traces = []
    if has('disk_busy'):
        disk_busy_traces.append(('disk_busy', '#e74c3c', '% Disk Time', None))
    if has('disk_queue'):
        disk_busy_traces.append(('disk_queue', '#8e44ad', 'Avg Queue Length', None))
    if disk_busy_traces:
        row_defs.append(('Disk — % Busy & Queue Length', '', disk_busy_traces))

    # Disk IOPS
    iops_traces = []
    if has('disk_rps'):
        iops_traces.append(('disk_rps', '#0055aa', 'Reads/sec', None))
    if has('disk_wps'):
        iops_traces.append(('disk_wps', '#e74c3c', 'Writes/sec', None))
    if iops_traces:
        row_defs.append(('Disk IOPS', 'ops/sec', iops_traces))

    # Disk throughput (bytes → MB/s)
    tput_traces = []
    if has('disk_rbytes'):
        tput_traces.append(('disk_rbytes', '#0055aa', 'Read MB/s', lambda v: v / 1048576))
    if has('disk_wbytes'):
        tput_traces.append(('disk_wbytes', '#e74c3c', 'Write MB/s', lambda v: v / 1048576))
    if tput_traces:
        row_defs.append(('Disk Throughput (MB/s)', 'MB/s', tput_traces))

    # Disk latency (seconds → ms)
    lat_traces = []
    if has('disk_rlatency'):
        lat_traces.append(('disk_rlatency', '#0055aa', 'Avg Read ms', lambda v: v * 1000))
    if has('disk_wlatency'):
        lat_traces.append(('disk_wlatency', '#e74c3c', 'Avg Write ms', lambda v: v * 1000))
    if lat_traces:
        row_defs.append(('Disk Latency (ms)', 'ms', lat_traces))

    # Network
    net_traces = []
    if has('net_bytes'):
        net_traces.append(('net_bytes', '#2980b9', 'Total Bytes/sec', None))
    elif has('net_sent') or has('net_recv'):
        if has('net_sent'):
            net_traces.append(('net_sent', '#27ae60', 'Sent Bytes/sec', None))
        if has('net_recv'):
            net_traces.append(('net_recv', '#e74c3c', 'Recv Bytes/sec', None))
    if net_traces:
        row_defs.append(('Network Throughput (bytes/sec)', 'bytes/sec', net_traces))

    if not row_defs:
        return ''

    nrows = len(row_defs)
    fig = make_subplots(
        rows=nrows, cols=1,
        subplot_titles=[rd[0] for rd in row_defs],
        vertical_spacing=0.06 if nrows > 3 else 0.10,
    )

    for row_idx, (title, ylabel, traces) in enumerate(row_defs, start=1):
        for col, color, name, transform in traces:
            y = df[col].apply(transform) if transform else df[col]
            fig.add_trace(go.Scatter(
                x=df['dt'], y=y, name=name, mode='lines',
                line=dict(color=color, width=1.5),
                hovertemplate=f'<b>{name}</b><br>%{{x}}<br>%{{y:.2f}}<extra></extra>',
            ), row=row_idx, col=1)
        if ylabel:
            fig.update_yaxes(title_text=ylabel, row=row_idx, col=1)
        fig.update_yaxes(showgrid=True, gridcolor='#e8edf5', rangemode='tozero',
                         row=row_idx, col=1)

    fig.update_layout(
        height=max(280 * nrows, 400),
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor='white',
        plot_bgcolor='#f8f9fc',
        font=dict(family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size=10),
        legend=dict(orientation='h', x=0, y=-0.03, font_size=10),
        hovermode='x unified',
    )
    fig.update_xaxes(showgrid=True, gridcolor='#e8edf5', tickangle=-30)

    chart_html = fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={'displayModeBar': True, 'displaylogo': False,
                'modeBarButtonsToRemove': ['select2d', 'lasso2d']},
    )

    duration = df['dt'].iloc[-1] - df['dt'].iloc[0]
    h, rem = divmod(int(duration.total_seconds()), 3600)
    duration_str = f'{h}h {rem // 60}m' if h else f'{rem // 60}m'

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">perfmon Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">{n} samples · {duration_str}</div>'
        + insights_html
        + stats_html
        + chart_html
        + '</div>'
    )
