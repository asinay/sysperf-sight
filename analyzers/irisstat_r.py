"""
Analyzer for the 'irisstat -R' (routine buffer pool) section in pButtons files.

irisstat -R dumps the current state of the IRIS routine buffer pool. Each row
is one buffer slot:

  hash:buf  size  sys  sfn  inuse  old  type  rcrc  rtime  rver  rctentry  rouname

  size    — buffer size in bytes (4096, 16384, or 65536)
  sys     — namespace index (0=SYS, others are user namespaces)
  sfn     — sub-file number (which database the routine lives in)
  inuse   — number of processes currently executing this routine (>0 = active)
  old     — marked for eviction on next opportunity
  type    — P=pure (read-only), M=modified (dirty, being compiled/updated),
             D=deleted (still in memory but logically removed)

The header block (before the table) contains pool configuration:
  - Number of routine buffers per size tier
  - gmaxsharedclsvec / classes inuse — class descriptor pool
  - LRU = number of class descriptors currently being evicted
"""
import re

_HEADER_LINE = re.compile(r'Dumping Routine Buffer Pool Currently Inuse')
_POOL_CONFIG_RE = re.compile(
    r'Number of rtn buf:\s*(.*?)(?=\n\n|\ngmax|\Z)', re.DOTALL)
_CLS_RE = re.compile(
    r'Dumping gmaxsharedclsvec (\d+),\s*gmaxclsvec (\d+).*?classes inuse (\d+) classes LRU (\d+)',
    re.DOTALL)
_SHM_RE = re.compile(r'shared cls memused\s+(\d+)')

# Each data row: optional "hash:buf" or bare buf, then fixed fields
_ROW_RE = re.compile(
    r'^\s*(?:\d+:)?(\d+)\s+'   # buf id (ignore hash prefix)
    r'(\d+)\s+'                # size
    r'(\d+)\s+'                # sys
    r'(\d+)\s+'                # sfn
    r'(\d+)\s+'                # inuse
    r'(\d+)\s+'                # old
    r'([PMD])\s+'              # type
    r'[0-9a-f]+\s+'            # rcrc
    r'[0-9a-f]+\s+'            # rtime
    r'(\d+)\s+'                # rver
    r'[0-9a-f]+\s+'            # rctentry
    r'(.+?)\s*$',              # rouname
    re.MULTILINE,
)

# Extract top-level package from routine name: "Pkg.Sub.Class.method.N" → "Pkg"
def _package(rouname: str) -> str:
    # Strip trailing .0 / .1 segment count
    name = re.sub(r'\.\d+$', '', rouname)
    # %Package.X → %Package
    parts = name.split('.')
    if not parts:
        return rouname
    # Group %system routines under their prefix
    if parts[0].startswith('%'):
        return parts[0] if len(parts) == 1 else f'{parts[0]}.{parts[1]}' if len(parts) > 1 else parts[0]
    return parts[0]


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


def _table(headers: list, rows: list, col_align: list = None, table_id: str = None) -> str:
    if not rows:
        return ''
    col_align = col_align or ['left'] * len(headers)
    id_attr = f' id="{table_id}"' if table_id else ''
    th_base = ('padding:5px 10px;font-size:0.72rem;font-weight:700;'
               'color:#555;text-transform:uppercase;letter-spacing:.05em;'
               'border-bottom:2px solid #dde3ee;white-space:nowrap')
    if table_id:
        ths = ''.join(
            f'<th onclick="sortTable(\'{table_id}\',{i},this)" '
            f'style="{th_base};text-align:{col_align[i]};cursor:pointer;user-select:none">'
            f'{h} ↕</th>'
            for i, h in enumerate(headers)
        )
    else:
        ths = ''.join(
            f'<th style="{th_base};text-align:{col_align[i]}">{h}</th>'
            for i, h in enumerate(headers)
        )
    tbody = ''
    for i, row in enumerate(rows):
        bg = '#f8f9fc' if i % 2 == 0 else 'white'
        tds = ''
        for j, cell in enumerate(row):
            align = col_align[j] if j < len(col_align) else 'left'
            tds += (f'<td style="padding:4px 10px;font-size:0.78rem;color:#222;'
                    f'text-align:{align};white-space:nowrap">{cell}</td>')
        tbody += f'<tr style="background:{bg}">{tds}</tr>'
    return (f'<table{id_attr} style="border-collapse:collapse;width:100%;margin-bottom:16px">'
            f'<thead><tr>{ths}</tr></thead><tbody>{tbody}</tbody></table>')


async def analyze(section_text: str) -> str:
    # ── Parse header config block ─────────────────────────────────────────────
    cls_m = _CLS_RE.search(section_text)
    max_shared_cls = int(cls_m.group(1)) if cls_m else None
    classes_inuse  = int(cls_m.group(3)) if cls_m else None
    classes_lru    = int(cls_m.group(4)) if cls_m else None

    shm_m = _SHM_RE.search(section_text)
    cls_mem_kb = int(shm_m.group(1)) // 1024 if shm_m else None

    # Parse "Number of rtn buf: 4 KB-> 32736, 16 KB-> 24552, 64 KB-> 8184"
    pool_cfg: dict[str, int] = {}
    cfg_m = _POOL_CONFIG_RE.search(section_text)
    if cfg_m:
        for kb, count in re.findall(r'(\d+)\s*KB->\s*(\d+)', cfg_m.group(1)):
            pool_cfg[f'{kb} KB'] = int(count)

    # ── Parse buffer rows ─────────────────────────────────────────────────────
    rows = []
    for m in _ROW_RE.finditer(section_text):
        rows.append({
            'size':   int(m.group(2)),
            'sys':    int(m.group(3)),
            'sfn':    int(m.group(4)),
            'inuse':  int(m.group(5)),
            'old':    int(m.group(6)),
            'type':   m.group(7),
            'rver':   int(m.group(8)),
            'rouname': m.group(9).strip(),
        })

    if not rows:
        return ''

    n_total   = len(rows)
    n_inuse   = sum(1 for r in rows if r['inuse'] > 0)
    n_old     = sum(1 for r in rows if r['old'] > 0)
    n_dirty   = sum(1 for r in rows if r['type'] == 'M')
    n_deleted = sum(1 for r in rows if r['type'] == 'D')

    # Total memory across all buffer sizes (bytes → MB)
    total_mem_bytes = sum(r['size'] for r in rows)
    total_mem_mb    = total_mem_bytes // (1024 * 1024)

    # ── Insights ──────────────────────────────────────────────────────────────
    flags = []

    if classes_lru is not None and classes_lru > 0:
        flags.append(_flag('amber',
            f'<b>Class descriptor LRU evictions active</b>: {classes_lru} class(es) being '
            f'evicted from the descriptor pool ({classes_inuse} in use of {max_shared_cls} max). '
            f'If this is sustained, increase <code>gmaxsharedclsvec</code> (shared class vectors) '
            f'to reduce reloading overhead.'))
    elif classes_inuse is not None and max_shared_cls is not None:
        pct = classes_inuse / max_shared_cls * 100 if max_shared_cls else 0
        if pct > 85:
            flags.append(_flag('amber',
                f'<b>Class descriptor pool near capacity</b>: {classes_inuse} of {max_shared_cls} '
                f'slots in use ({pct:.0f}%). Consider increasing <code>gmaxsharedclsvec</code>.'))
        else:
            flags.append(_flag('green',
                f'Class descriptor pool healthy: {classes_inuse} of {max_shared_cls} slots '
                f'in use ({pct:.0f}%), LRU evictions: 0.'))

    old_pct = n_old / n_total * 100 if n_total else 0
    if old_pct > 20:
        flags.append(_flag('amber',
            f'<b>{n_old} buffer(s) marked old</b> ({old_pct:.0f}% of pool) — '
            f'a large fraction of cached routines are candidates for eviction. '
            f'The pool may be undersized relative to the active routine set.'))

    if n_deleted > 0:
        flags.append(_flag('info',
            f'{n_deleted} buffer(s) of deleted routines still occupying pool space (type D) — '
            f'these will be reclaimed on next eviction pass.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:14px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(flags) + '</div>'
        + '<!--/INS-->'
    )

    # ── Stat cards ────────────────────────────────────────────────────────────
    stat_items = [
        _stat('Buffers loaded', f'{n_total:,}'),
        _stat('Pool memory', f'{total_mem_mb:,}', 'MB'),
        _stat('In use now', str(n_inuse)),
        _stat('Marked old', str(n_old)),
        _stat('Modified (M)', str(n_dirty)),
        _stat('Deleted (D)', str(n_deleted)),
    ]
    if classes_inuse is not None:
        stat_items.append(_stat('Classes in use', str(classes_inuse)))
    if classes_lru is not None:
        stat_items.append(_stat('Class LRU evictions', str(classes_lru)))

    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + ''.join(stat_items) + '</div>'
    )

    # ── Buffer pool config ────────────────────────────────────────────────────
    if pool_cfg:
        cfg_cards = ''.join(
            _stat(f'{tier} buffers', f'{count:,}')
            for tier, count in sorted(pool_cfg.items())
        )
        pool_cfg_html = (
            '<div style="font-size:0.78rem;font-weight:600;color:#333;margin-bottom:6px">'
            'Buffer Pool Configuration</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
            + cfg_cards + '</div>'
        )
    else:
        pool_cfg_html = ''

    # ── Currently in-use routines ─────────────────────────────────────────────
    inuse_rows = sorted(
        [r for r in rows if r['inuse'] > 0],
        key=lambda r: r['inuse'], reverse=True
    )[:20]

    inuse_table = ''
    if inuse_rows:
        inuse_table = (
            '<div style="font-size:0.78rem;font-weight:600;color:#333;margin-bottom:6px">'
            'Currently In-Use Routines'
            '<span style="font-size:0.72rem;color:#888;font-weight:400;margin-left:8px">'
            'processes actively executing at snapshot time</span></div>'
            + _table(
                ['Routine', 'Type', 'Size', 'Processes'],
                [[r['rouname'],
                  {'P': 'Pure (read-only)', 'M': 'Modified (dirty)', 'D': 'Deleted'}[r['type']],
                  f'{r["size"]//1024}K',
                  str(r['inuse'])]
                 for r in inuse_rows],
                ['left', 'left', 'right', 'right'],
                table_id='irisr-inuse',
            )
        )

    # ── Top packages by buffer count ──────────────────────────────────────────
    pkg_counts: dict[str, int] = {}
    pkg_inuse:  dict[str, int] = {}
    pkg_mem:    dict[str, int] = {}
    for r in rows:
        pkg = _package(r['rouname'])
        pkg_counts[pkg] = pkg_counts.get(pkg, 0) + 1
        pkg_inuse[pkg]  = pkg_inuse.get(pkg, 0) + r['inuse']
        pkg_mem[pkg]    = pkg_mem.get(pkg, 0) + r['size']

    top_pkgs = sorted(pkg_counts.items(), key=lambda x: x[1], reverse=True)[:20]

    pkg_table = (
        '<div style="font-size:0.78rem;font-weight:600;color:#333;margin-bottom:6px">'
        'Top Packages by Buffer Count'
        '<span style="font-size:0.72rem;color:#888;font-weight:400;margin-left:8px">'
        'top 20 by number of loaded routine buffers</span></div>'
        + _table(
            ['Package', 'Buffers', 'In-Use', 'Memory (MB)'],
            [[pkg, str(cnt),
              str(pkg_inuse[pkg]) if pkg_inuse[pkg] > 0 else '—',
              f'{pkg_mem[pkg] / (1024*1024):.1f}']
             for pkg, cnt in top_pkgs],
            ['left', 'right', 'right', 'right'],
            table_id='irisr-pkgs',
        )
    )

    # ── Buffer type breakdown ─────────────────────────────────────────────────
    type_counts = {'P': 0, 'M': 0, 'D': 0}
    type_mem    = {'P': 0, 'M': 0, 'D': 0}
    for r in rows:
        type_counts[r['type']] += 1
        type_mem[r['type']]    += r['size']

    type_labels = {'P': 'Pure (read-only)', 'M': 'Modified (dirty)', 'D': 'Deleted (pending eviction)'}
    type_table = (
        '<div style="font-size:0.78rem;font-weight:600;color:#333;margin-bottom:6px">'
        'Buffer Types</div>'
        + _table(
            ['Type', 'Description', 'Count', 'Memory (MB)'],
            [[t, type_labels[t], str(type_counts[t]),
              f'{type_mem[t] / (1024*1024):.1f}']
             for t in ('P', 'M', 'D')],
            ['center', 'left', 'right', 'right'],
        )
    )

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">irisstat -R Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">'
        f'Routine buffer pool snapshot · {n_total:,} buffers loaded</div>'
        + insights_html
        + stats_html
        + pool_cfg_html
        + inuse_table
        + pkg_table
        + type_table
        + '</div>'
    )
