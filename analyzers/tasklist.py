import re
import io
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Column positions from the tasklist -V header
# Image Name(25) PID(8) Session Name(16) Session#(11) Mem Usage(12) Status(15) User Name(50) CPU Time(12) Window Title
_COL_WIDTHS = [25, 8, 16, 11, 12, 15, 50, 12, None]
_COL_NAMES  = ['Image', 'PID', 'Session', 'SessionNum', 'MemKB', 'Status', 'User', 'CPUTime', 'Title']


def _parse_mem(val: str) -> float:
    """'102,648 K' -> MB as float"""
    m = re.search(r'[\d,]+', val)
    return float(m.group().replace(',', '')) / 1024 if m else 0.0


def _parse_cpu(val: str) -> float:
    """'0:52:13' -> total seconds"""
    parts = re.findall(r'\d+', val)
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0.0


def _parse_snapshot(block: str) -> pd.DataFrame | None:
    lines = []
    in_data = False
    for line in block.splitlines():
        if re.match(r'^=+\s+=+', line):
            in_data = True
            continue
        if in_data and line.strip():
            lines.append(line)
    if not lines:
        return None

    records = []
    for line in lines:
        pos = 0
        row = []
        for w in _COL_WIDTHS:
            if w is None:
                row.append(line[pos:].strip())
                break
            row.append(line[pos:pos+w].strip())
            pos += w
        records.append(row)

    df = pd.DataFrame(records, columns=_COL_NAMES)
    df['MemMB'] = df['MemKB'].apply(_parse_mem)
    df['CPUSec'] = df['CPUTime'].apply(_parse_cpu)
    return df


def _short_user(u: str) -> str:
    """'NT AUTHORITY\\SYSTEM' -> 'SYSTEM', 'DOMAIN\\user' -> 'user'"""
    return u.split('\\')[-1] if '\\' in u else u


async def analyze(section_text: str) -> str:
    # Split on snapshot boundaries
    snapshots_raw = re.split(r'sample \d+ of \d+', section_text)
    snapshots_raw = [s for s in snapshots_raw if re.search(r'={5,}', s)]

    if not snapshots_raw:
        return ''

    # Use first snapshot for static analysis
    df = _parse_snapshot(snapshots_raw[0])
    if df is None or df.empty:
        return ''

    df['ShortUser'] = df['User'].apply(_short_user)
    df = df[df['Image'] != 'System Idle Process']

    # ---- Top 15 processes by memory ----
    top_mem = df.nlargest(15, 'MemMB').copy()
    top_mem['Label'] = top_mem['Image'] + ' (' + top_mem['PID'] + ')'

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Top 15 Processes by Memory (MB)', 'Memory by User (MB)'),
        column_widths=[0.6, 0.4],
        specs=[[{'type': 'xy'}, {'type': 'domain'}]],
    )

    # Bar chart — top processes
    fig.add_trace(go.Bar(
        y=top_mem['Label'],
        x=top_mem['MemMB'],
        orientation='h',
        marker_color='#0055aa',
        hovertemplate='<b>%{y}</b><br>%{x:.1f} MB<extra></extra>',
        showlegend=False,
    ), row=1, col=1)

    # Pie chart — memory by user
    by_user = df.groupby('ShortUser')['MemMB'].sum().reset_index()
    by_user = by_user.sort_values('MemMB', ascending=False)
    # Collapse small users into "Other"
    threshold = by_user['MemMB'].sum() * 0.02
    other = by_user[by_user['MemMB'] < threshold]['MemMB'].sum()
    by_user = by_user[by_user['MemMB'] >= threshold]
    if other > 0:
        by_user = pd.concat([by_user, pd.DataFrame([{'ShortUser': 'Other', 'MemMB': other}])], ignore_index=True)

    fig.add_trace(go.Pie(
        labels=by_user['ShortUser'],
        values=by_user['MemMB'].round(1),
        hole=0.4,
        hovertemplate='<b>%{label}</b><br>%{value:.0f} MB (%{percent})<extra></extra>',
        showlegend=True,
    ), row=1, col=2)

    total_mem = df['MemMB'].sum()
    proc_count = len(df)

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor='white',
        plot_bgcolor='#f8f9fc',
        font=dict(family='-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size=11),
        legend=dict(orientation='v', x=1.0, y=0.5),
        annotations=[
            dict(text=f'{proc_count} processes<br>{total_mem/1024:.1f} GB total',
                 x=0.82, y=0.5, font_size=11, showarrow=False, xref='paper', yref='paper')
        ]
    )
    fig.update_xaxes(title_text='MB', row=1, col=1)
    fig.update_yaxes(autorange='reversed', row=1, col=1)

    chart_html = fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={'displayModeBar': False},
    )

    # Summary stats
    top3 = top_mem.head(3)
    top3_rows = ''.join(
        f'<tr><td>{r.Image}</td><td style="text-align:right">{r.MemMB:.0f} MB</td><td>{r.ShortUser}</td></tr>'
        for _, r in top3.iterrows()
    )

    return f'''
<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em">
    Process Analysis &mdash; Snapshot 1 of {len(snapshots_raw)}
  </div>
  {chart_html}
</div>
'''
