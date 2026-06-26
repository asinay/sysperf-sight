"""
Analyzer for the 'free' section in Linux SystemPerformance files.

Expected format: CSV with header row, one sample per line.
  Date,     Time,      Memtotal,     used,     free,   shared,  buffers,   cached,  adjused,  adjfree,swaptotal, swapused, swapfree,
  06/15/26, 00:05:01,    514823,   120945,   149623, ...

All memory values are in MB. Trailing swap columns may be absent on some
SystemPerformance versions — columns are mapped by header name, not position.
"""
import re
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _parse_free(text: str) -> pd.DataFrame | None:
    lines = [ln.rstrip() for ln in text.splitlines()]

    # Find header line (contains Memtotal or memtotal)
    hdr_idx = None
    for i, ln in enumerate(lines):
        if re.search(r'memtotal', ln, re.IGNORECASE):
            hdr_idx = i
            break
    if hdr_idx is None:
        return None

    raw_cols = [c.strip().lower() for c in lines[hdr_idx].split(',') if c.strip()]

    records = []
    for ln in lines[hdr_idx + 1:]:
        parts = [p.strip() for p in ln.split(',')]
        if len(parts) < 3:
            continue
        # First two columns are Date and Time
        date_s = parts[0]
        time_s = parts[1]
        if not re.match(r'\d{2}/\d{2}/\d{2,4}', date_s):
            continue
        # Expand 2-digit year
        dp = date_s.split('/')
        if len(dp[2]) == 2:
            date_s = f'{dp[0]}/{dp[1]}/20{dp[2]}'
        try:
            ts = pd.to_datetime(f'{date_s} {time_s}', format='%m/%d/%Y %H:%M:%S')
        except Exception:
            continue
        row = {'dt': ts}
        for col, val in zip(raw_cols[2:], parts[2:]):
            try:
                row[col] = float(val)
            except (ValueError, TypeError):
                pass
        records.append(row)

    if not records:
        return None
    df = pd.DataFrame(records).sort_values('dt').reset_index(drop=True)
    if len(df) > 500:
        step = len(df) // 500
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
    df = _parse_free(section_text)
    if df is None or df.empty:
        return ''

    cols = set(df.columns) - {'dt'}
    n = len(df)

    has_total    = 'memtotal'  in cols
    has_used     = 'used'      in cols
    has_free     = 'free'      in cols
    has_buffers  = 'buffers'   in cols
    has_cached   = 'cached'    in cols
    has_adjused  = 'adjused'   in cols
    has_adjfree  = 'adjfree'   in cols
    has_swaptot  = 'swaptotal' in cols
    has_swapused = 'swapused'  in cols
    has_swapfree = 'swapfree'  in cols
    has_swap     = has_swaptot and has_swapused

    total_mb = df['memtotal'].iloc[0] if has_total else None

    # ── Insights ─────────────────────────────────────────────────────────────
    flags = []

    if has_adjfree and total_mb:
        adjfree_min = df['adjfree'].min()
        adjfree_pct = adjfree_min / total_mb * 100
        adjfree_avg = df['adjfree'].mean()
        if adjfree_pct < 5:
            flags.append(_flag('red',
                f'<b>Critically low adjusted free RAM</b>: minimum {adjfree_min:.0f} MB '
                f'({adjfree_pct:.1f}% of total) — system is under severe memory pressure. '
                f'IRIS global buffers may be getting evicted by the OS.'))
        elif adjfree_pct < 15:
            flags.append(_flag('amber',
                f'<b>Low adjusted free RAM</b>: minimum {adjfree_min:.0f} MB '
                f'({adjfree_pct:.1f}% of total) — limited headroom. '
                f'Monitor for swap activity and buffer evictions.'))
        else:
            flags.append(_flag('green',
                f'Adjusted free RAM is healthy: avg {adjfree_avg:.0f} MB, '
                f'min {adjfree_min:.0f} MB ({adjfree_pct:.1f}% of {total_mb:.0f} MB total).'))

    if has_swap and has_swapused:
        swapused_max = df['swapused'].max()
        swaptotal = df['swaptotal'].iloc[0] if has_swaptot else 0
        if swapused_max > 0 and swaptotal > 0:
            swap_pct = swapused_max / swaptotal * 100
            if swap_pct > 20:
                flags.append(_flag('red',
                    f'<b>Significant swap usage</b>: peak {swapused_max:.0f} MB used '
                    f'({swap_pct:.1f}% of swap) — active paging is likely. '
                    f'Cross-reference with vmstat si/so.'))
            elif swapused_max > 0:
                flags.append(_flag('amber',
                    f'<b>Swap in use</b>: peak {swapused_max:.0f} MB — '
                    f'some paging has occurred. Monitor for increases.'))
        elif swapused_max == 0:
            flags.append(_flag('green', 'No swap usage detected.'))

    if not flags:
        flags.append(_flag('green', 'Memory usage appears normal.'))

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
    if total_mb:
        stat_items.append(_stat('Total RAM', f'{total_mb/1024:.1f}', 'GB'))
    if has_adjfree:
        stat_items.append(_stat('Adj free min', f'{df["adjfree"].min():.0f}', 'MB'))
        stat_items.append(_stat('Adj free avg', f'{df["adjfree"].mean():.0f}', 'MB'))
    if has_used:
        stat_items.append(_stat('Used peak', f'{df["used"].max():.0f}', 'MB'))
    if has_swap and has_swapused:
        stat_items.append(_stat('Swap used peak', f'{df["swapused"].max():.0f}', 'MB'))

    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + ''.join(stat_items) + '</div>'
    ) if stat_items else ''

    # ── Charts ────────────────────────────────────────────────────────────────
    row_defs = []

    # RAM breakdown: used, buffers, cached, adjfree
    ram_traces = []
    if has_used:
        ram_traces.append(('used', '#e74c3c', 'used'))
    if has_buffers:
        ram_traces.append(('buffers', '#0055aa', 'buffers'))
    if has_cached:
        ram_traces.append(('cached', '#27ae60', 'cached'))
    if ram_traces:
        row_defs.append(('RAM Usage (MB)', 'MB', ram_traces))

    # Adjusted free — most useful single line
    if has_adjfree:
        row_defs.append(('Adjusted Free RAM (MB)', 'MB', [('adjfree', '#0055aa', 'adj free')]))

    # Swap usage
    if has_swap and has_swapused:
        row_defs.append(('Swap Used (MB)', 'MB', [('swapused', '#e74c3c', 'swap used')]))

    if not row_defs:
        return ''

    nrows = len(row_defs)
    fig = make_subplots(
        rows=nrows, cols=1,
        subplot_titles=[rd[0] for rd in row_defs],
        vertical_spacing=0.08 if nrows > 2 else 0.12,
    )

    for row_idx, (title, ylabel, traces) in enumerate(row_defs, start=1):
        for col, color, name in traces:
            fig.add_trace(go.Scatter(
                x=df['dt'], y=df[col], name=name, mode='lines',
                line=dict(color=color, width=1.5),
                hovertemplate=f'<b>{name}</b><br>%{{x}}<br>%{{y:.0f}} MB<extra></extra>',
            ), row=row_idx, col=1)
        fig.update_yaxes(title_text=ylabel, showgrid=True,
                         gridcolor='#e8edf5', rangemode='tozero',
                         row=row_idx, col=1)

    fig.update_layout(
        height=240 * nrows,
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor='white',
        plot_bgcolor='#f8f9fc',
        font=dict(family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size=10),
        legend=dict(orientation='h', x=0, y=-0.04, font_size=10),
        hovermode='x unified',
    )
    fig.update_xaxes(showgrid=True, gridcolor='#e8edf5', tickangle=-30)

    chart_html = fig.to_html(
        full_html=False, include_plotlyjs=False,
        config={'displayModeBar': True, 'displaylogo': False,
                'modeBarButtonsToRemove': ['select2d', 'lasso2d']},
    )

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">free Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">{n} intervals</div>'
        + insights_html
        + stats_html
        + chart_html
        + '</div>'
    )
