"""
Cross-section synthesis: produces a Performance Summary injected at the top
of the output report.

Called after all individual analyzers have run. Receives the full dict of
{section_id: raw_text} for every selected section that was parsed. Each
sub-analyser in this module is defensive — it returns None signals when the
required section is absent or unparseable, and the summary silently omits
that subsection.

The summary is rendered as collapsible subsections so the user can expand
only what interests them, with a top-level signal strip (green/amber/red
pills) giving an at-a-glance health overview.
"""
import re


# ── Signal helpers ────────────────────────────────────────────────────────────

_COLOURS = {
    'red':   ('#fef2f2', '#fca5a5', '#7f1d1d', '#ef4444'),
    'amber': ('#fffbeb', '#fcd34d', '#78350f', '#f59e0b'),
    'green': ('#f0fdf4', '#bbf7d0', '#14532d', '#22c55e'),
    'info':  ('#eff6ff', '#93c5fd', '#1e3a5f', '#3b82f6'),
}


def _pill(level: str, text: str, evidence: str = '') -> str:
    """Single-finding pill with optional collapsible evidence."""
    bg, border, fg, dot = _COLOURS[level]
    ev_html = ''
    if evidence:
        ev_html = (
            f'<details style="margin-top:5px">'
            f'<summary style="font-size:0.7rem;opacity:0.65;cursor:pointer;'
            f'list-style:none;display:inline-flex;align-items:center;gap:3px;'
            f'user-select:none">&#9656; Show evidence</summary>'
            f'<div style="font-size:0.71rem;opacity:0.8;margin-top:4px;padding:4px 8px;'
            f'border-left:2px solid {border};font-style:italic">{evidence}</div>'
            f'</details>'
        )
    return (
        f'<div style="display:flex;align-items:flex-start;gap:8px;padding:7px 11px;'
        f'background:{bg};border:1px solid {border};border-radius:6px;'
        f'font-size:0.78rem;color:{fg};line-height:1.4;margin-bottom:5px">'
        f'<span style="color:{dot};flex-shrink:0;margin-top:1px">&#9679;</span>'
        f'<div><span>{text}</span>{ev_html}</div></div>'
    )


def _pill_grouped(level: str, headline: str, items: list[str], evidence_footer: str = '') -> str:
    """
    A pill showing a rolled-up headline + collapsible detail list.
    items: list of HTML strings, one per individual finding.
    evidence_footer: optional source/threshold note shown at the bottom of details.
    """
    bg, border, fg, dot = _COLOURS[level]
    n = len(items)
    label = f'Show {n} detail{"s" if n > 1 else ""}'
    rows = ''.join(
        f'<div style="padding:2px 0;font-size:0.76rem;border-bottom:1px solid {border}40;'
        f'padding:3px 0">{item}</div>'
        for item in items
    )
    ev_line = (
        f'<div style="font-size:0.7rem;opacity:0.65;margin-top:5px;font-style:italic">'
        f'{evidence_footer}</div>'
    ) if evidence_footer else ''
    details_html = (
        f'<details style="margin-top:5px">'
        f'<summary style="font-size:0.7rem;opacity:0.65;cursor:pointer;'
        f'list-style:none;display:inline-flex;align-items:center;gap:3px;'
        f'user-select:none">&#9656; {label}</summary>'
        f'<div style="margin-top:6px;padding:6px 8px;background:{bg}88;'
        f'border-left:2px solid {border};border-radius:0 4px 4px 0">'
        f'{rows}{ev_line}</div>'
        f'</details>'
    )
    return (
        f'<div style="display:flex;align-items:flex-start;gap:8px;padding:7px 11px;'
        f'background:{bg};border:1px solid {border};border-radius:6px;'
        f'font-size:0.78rem;color:{fg};line-height:1.4;margin-bottom:5px">'
        f'<span style="color:{dot};flex-shrink:0;margin-top:1px">&#9679;</span>'
        f'<div style="flex:1"><span>{headline}</span>{details_html}</div></div>'
    )


def _badge(level: str) -> str:
    bg, border, fg, _ = _COLOURS[level]
    label = {'red': 'Action needed', 'amber': 'Warning', 'green': 'Healthy', 'info': 'Info'}[level]
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;'
        f'background:{bg};border:1px solid {border};color:{fg};'
        f'font-size:0.7rem;font-weight:700;white-space:nowrap">{label}</span>'
    )


def _subsection(title: str, badge_level: str, sub_id: str, body: str) -> str:
    return f'''
<div class="synth-sub" id="synth-{sub_id}">
  <div class="synth-sub-header" onclick="synthToggle('{sub_id}')">
    <span class="synth-sub-title">{title}</span>
    {_badge(badge_level)}
    <span class="synth-chevron" id="synth-chev-{sub_id}">▾</span>
  </div>
  <div class="synth-sub-body" id="synth-body-{sub_id}">
    {body}
  </div>
</div>'''


# ── Sub-analyses ──────────────────────────────────────────────────────────────

def _analyse_memory(texts: dict) -> tuple[str, str] | None:
    signals = []  # (level, rendered_pill_html)

    free_text = texts.get('free', '')
    if free_text:
        total_m = re.search(r'memtotal', free_text, re.IGNORECASE)
        if total_m:
            nums = re.findall(r'\d{4,}', free_text)
            if nums:
                total = int(nums[0])
                adjfree_vals = []
                for ln in free_text.splitlines():
                    parts = [p.strip() for p in ln.split(',')]
                    if len(parts) >= 10 and re.match(r'\d{2}/\d{2}', parts[0]):
                        try:
                            adjfree_vals.append(float(parts[9]))
                        except (ValueError, IndexError):
                            pass
                if adjfree_vals:
                    mn = min(adjfree_vals)
                    pct = mn / total * 100
                    ev = (f'Source: <b>free</b> &mdash; adjfree min&nbsp;=&nbsp;{mn:.0f}&nbsp;MB'
                          f' ({pct:.1f}% of {total:,}&nbsp;MB) &middot; '
                          f'threshold: &lt;15%&nbsp;&#8594;&nbsp;amber, &lt;5%&nbsp;&#8594;&nbsp;red')
                    if pct < 5:
                        signals.append(('red', _pill('red',
                            f'<b>Critically low adjusted free RAM</b>: minimum {mn:.0f} MB ({pct:.1f}% of {total:,} MB total). IRIS global buffers may be evicted by the OS.', ev)))
                    elif pct < 15:
                        signals.append(('amber', _pill('amber',
                            f'<b>Low adjusted free RAM</b>: minimum {mn:.0f} MB ({pct:.1f}% of total). Limited headroom — monitor for swap and evictions.', ev)))
                    else:
                        signals.append(('green', _pill('green',
                            f'Adjusted free RAM healthy: minimum {mn:.0f} MB ({pct:.1f}% of total).', ev)))

        swap_vals = []
        for ln in free_text.splitlines():
            parts = [p.strip() for p in ln.split(',')]
            if len(parts) >= 12 and re.match(r'\d{2}/\d{2}', parts[0]):
                try:
                    swap_vals.append(float(parts[11]))
                except (ValueError, IndexError):
                    pass
        if swap_vals and max(swap_vals) > 0:
            pk_swap = max(swap_vals)
            ev = f'Source: <b>free</b> &mdash; swapused peak&nbsp;=&nbsp;{pk_swap:.0f}&nbsp;MB across {len(swap_vals)} samples'
            signals.append(('amber', _pill('amber',
                f'<b>Swap in use</b>: peak {pk_swap:.0f} MB. Cross-reference with vmstat si/so columns.', ev)))

    mgstat_text = texts.get('mgstat', '')
    if mgstat_text:
        phyrds = []
        for ln in mgstat_text.splitlines():
            parts = [p.strip() for p in ln.split(',')]
            if len(parts) >= 6 and re.match(r'\d{2}/\d{2}', parts[0]):
                try:
                    phyrds.append(float(parts[4]))
                except (ValueError, IndexError):
                    pass
        if phyrds:
            avg = sum(phyrds) / len(phyrds)
            pk  = max(phyrds)
            if pk > avg * 5 and pk > 500:
                ratio = pk / avg if avg > 0 else 0
                ev = (f'Source: <b>mgstat</b> &mdash; PhyRds: peak&nbsp;{pk:.0f}, avg&nbsp;{avg:.0f}'
                      f' (ratio&nbsp;{ratio:.1f}&times;) &middot; threshold: peak&gt;avg&times;5 and&gt;500')
                signals.append(('amber', _pill('amber',
                    f'<b>mgstat PhyRds spike</b>: peak {pk:.0f} vs avg {avg:.0f}/interval. Sustained physical reads may indicate global buffer pressure.', ev)))

    if not signals:
        return None
    level = 'red' if any(s[0] == 'red' for s in signals) else 'amber' if any(s[0] == 'amber' for s in signals) else 'green'
    return level, ''.join(html for _, html in signals)


def _analyse_disk(texts: dict) -> tuple[str, str] | None:
    """Combine df -m + mount + iostat/sar-d. Groups findings to avoid one pill per filesystem."""
    pills = []  # (level, rendered_html)

    _IRIS_TAGS = ('iris', 'hs-', '/db', '/jrn', '/sys', '/mgr')

    # ── df -m: group near-full filesystems ────────────────────────────────────
    df_text = texts.get('df-m', '')
    red_capacity = []   # (mp, pct, used_mb, total_mb, is_iris)
    amber_capacity = []

    if df_text:
        for ln in df_text.splitlines():
            m = re.search(r'(\d+)%\s+(\S+)\s*$', ln)
            if not m:
                continue
            pct = int(m.group(1))
            mp  = m.group(2)
            iris = any(p in mp.lower() for p in _IRIS_TAGS)
            parts = ln.split()
            used_mb = total_mb = None
            if len(parts) >= 5:
                try:
                    used_mb  = int(parts[-4])
                    total_mb = int(parts[-5])
                except (ValueError, IndexError):
                    pass
            entry = (mp, pct, used_mb, total_mb, iris)
            if pct >= 90:
                red_capacity.append(entry)
            elif pct >= 75:
                amber_capacity.append(entry)

    def _cap_item(mp, pct, used_mb, total_mb, iris):
        label = f'<b>{mp}</b>' if iris else mp
        size_str = (f'&nbsp;({used_mb:,}&thinsp;MB of {total_mb:,}&thinsp;MB)'
                    if used_mb is not None and total_mb is not None else '')
        iris_tag = ' <i style="opacity:.7">(IRIS)</i>' if iris else ''
        return f'{label}{iris_tag}: {pct}%{size_str}'

    if red_capacity:
        n = len(red_capacity)
        s = 's' if n > 1 else ''
        items = [_cap_item(*e) for e in sorted(red_capacity, key=lambda x: -x[1])]
        iris_n = sum(1 for e in red_capacity if e[4])
        note = f' — {iris_n} on IRIS path{"s" if iris_n > 1 else ""}' if iris_n else ''
        pills.append(('red', _pill_grouped('red',
            f'<b>{n} filesystem{s} critically full (≥90%)</b>{note} — immediate action required.',
            items,
            'Source: df&nbsp;-m &middot; threshold: ≥90% → red')))

    if amber_capacity:
        n = len(amber_capacity)
        s = 's' if n > 1 else ''
        items = [_cap_item(*e) for e in sorted(amber_capacity, key=lambda x: -x[1])]
        iris_n = sum(1 for e in amber_capacity if e[4])
        note = f' — {iris_n} on IRIS path{"s" if iris_n > 1 else ""}' if iris_n else ''
        pills.append(('amber', _pill_grouped('amber',
            f'<b>{n} filesystem{s} at warning capacity (75–89%)</b>{note} — monitor closely.',
            items,
            'Source: df&nbsp;-m &middot; threshold: ≥75% → amber')))

    # ── mount: group soft network mounts ──────────────────────────────────────
    mount_text = texts.get('mount', '')
    soft_iris  = []   # (mp, fstype)
    soft_other = []

    if mount_text:
        for ln in mount_text.splitlines():
            m = re.match(r'.+ on (/\S*) type (\S+) \((.+)\)', ln)
            if not m:
                continue
            mp, fstype, opts = m.groups()
            if fstype not in ('cifs', 'nfs', 'nfs4', 'nfs3'):
                continue
            if 'soft' not in opts.split(','):
                continue
            iris = any(p in mp.lower() for p in _IRIS_TAGS)
            (soft_iris if iris else soft_other).append((mp, fstype))

    if soft_iris:
        n = len(soft_iris)
        s = 's' if n > 1 else ''
        items = [f'<b>{mp}</b> ({fstype})' for mp, fstype in soft_iris]
        pills.append(('amber', _pill_grouped('amber',
            f'<b>{n} soft network mount{s} on IRIS path{s}</b>. Soft mounts can silently drop I/O — risk of data corruption.',
            items,
            'Source: mount &middot; option: soft')))

    if soft_other:
        n = len(soft_other)
        s = 's' if n > 1 else ''
        items = [f'{mp} ({fstype})' for mp, fstype in soft_other]
        pills.append(('info', _pill_grouped('info',
            f'{n} soft network mount{s} (non-IRIS paths). Soft mounts silently drop I/O on timeout.',
            items,
            'Source: mount &middot; option: soft')))

    # ── iostat / sar-d: peak %util ─────────────────────────────────────────────
    for sid in ('iostat', 'sar-d'):
        t = texts.get(sid, '')
        if not t:
            continue
        utils = []
        for ln in t.splitlines():
            parts = ln.split()
            if not parts or parts[0] in ('avg-cpu:', 'Device', 'Average:'):
                continue
            try:
                u = float(parts[-1])
                if 0 <= u <= 100:
                    utils.append(u)
            except ValueError:
                pass
        if utils:
            pk = max(utils)
            ev = (f'Source: <b>{sid}</b> &mdash; %util peak&nbsp;=&nbsp;{pk:.0f}%'
                  f' across {len(utils)} data points &middot; threshold: ≥90% → red, ≥70% → amber')
            if pk >= 90:
                pills.append(('red', _pill('red',
                    f'<b>Disk saturation detected</b> ({sid}): peak {pk:.0f}% util. Check {sid} section for device breakdown.', ev)))
            elif pk >= 70:
                pills.append(('amber', _pill('amber',
                    f'<b>High disk utilisation</b> ({sid}): peak {pk:.0f}% util.', ev)))
            break

    if not pills:
        return None
    level = 'red' if any(p[0] == 'red' for p in pills) else 'amber' if any(p[0] == 'amber' for p in pills) else 'green'
    return level, ''.join(html for _, html in pills)


def _analyse_cpu(texts: dict) -> tuple[str, str] | None:
    signals = []

    vm_text = texts.get('vmstat', '')
    if vm_text:
        rq_vals = []
        for ln in vm_text.splitlines():
            parts = ln.split()
            if len(parts) >= 3 and re.match(r'\d{2}/\d{2}', parts[0]):
                try:
                    rq_vals.append(float(parts[2]))
                except (ValueError, IndexError):
                    pass
        if rq_vals:
            avg_rq = sum(rq_vals) / len(rq_vals)
            pk_rq  = max(rq_vals)
            ev = (f'Source: <b>vmstat</b> &mdash; r&nbsp;column: avg&nbsp;{avg_rq:.1f}, peak&nbsp;{pk_rq:.0f}'
                  f' across {len(rq_vals)} samples &middot; threshold: avg&gt;4 → red, &gt;2 → amber')
            if avg_rq > 4:
                signals.append(('red', _pill('red',
                    f'<b>CPU run queue saturated</b>: avg {avg_rq:.1f}, peak {pk_rq:.0f} runnable processes. System is CPU-bound.', ev)))
            elif avg_rq > 2:
                signals.append(('amber', _pill('amber',
                    f'<b>Elevated CPU run queue</b>: avg {avg_rq:.1f}, peak {pk_rq:.0f}.', ev)))

    sar_text = texts.get('sar-u', '')
    if sar_text:
        iowait_vals = []
        for ln in sar_text.splitlines():
            parts = ln.split()
            if len(parts) >= 7 and parts[0] not in ('Average:', 'Linux') and re.search(r'\d', parts[0]):
                try:
                    iowait_vals.append(float(parts[5]))
                except (ValueError, IndexError):
                    pass
        if iowait_vals:
            avg_wa = sum(iowait_vals) / len(iowait_vals)
            pk_wa  = max(iowait_vals)
            ev = (f'Source: <b>sar-u</b> &mdash; %iowait: avg&nbsp;{avg_wa:.1f}%, peak&nbsp;{pk_wa:.1f}%'
                  f' across {len(iowait_vals)} samples &middot; threshold: avg&gt;20% → red, &gt;10% → amber')
            if avg_wa > 20:
                signals.append(('red', _pill('red',
                    f'<b>High iowait</b>: avg {avg_wa:.1f}%, peak {pk_wa:.1f}%. Processes are frequently blocked waiting for disk I/O.', ev)))
            elif avg_wa > 10:
                signals.append(('amber', _pill('amber',
                    f'<b>Elevated iowait</b>: avg {avg_wa:.1f}%, peak {pk_wa:.1f}%.', ev)))

    if not signals:
        return None
    level = 'red' if any(s[0] == 'red' for s in signals) else 'amber' if any(s[0] == 'amber' for s in signals) else 'green'
    return level, ''.join(html for _, html in signals)


def _analyse_iris(texts: dict) -> tuple[str, str] | None:
    signals = []

    mgstat_text = texts.get('mgstat', '')
    if mgstat_text:
        wdphase_cols = None
        for ln in mgstat_text.splitlines():
            parts = [p.strip() for p in ln.split(',')]
            if 'WDphase' in ln and 'Glorefs' in ln:
                wdphase_cols = {v.lower(): i for i, v in enumerate(parts)}
                break
        if wdphase_cols and 'wdphase' in wdphase_cols:
            idx = wdphase_cols['wdphase']
            phase8 = 0
            total  = 0
            for ln in mgstat_text.splitlines():
                parts = [p.strip() for p in ln.split(',')]
                if len(parts) > idx and re.match(r'\d{2}/\d{2}', parts[0]):
                    try:
                        total += 1
                        if float(parts[idx]) == 8:
                            phase8 += 1
                    except (ValueError, IndexError):
                        pass
            if total and phase8 / total > 0.1:
                ev = (f'Source: <b>mgstat</b> &mdash; WDphase=8 in {phase8} of {total} intervals'
                      f' ({phase8/total*100:.0f}%) &middot; threshold: &gt;10% → red')
                signals.append(('red', _pill('red',
                    f'<b>Write daemon saturated</b>: WDphase=8 in {phase8/total*100:.0f}% of mgstat intervals. IRIS write throughput is maxed — check disk %util and consider WD tuning.', ev)))

        nseize_vals = []
        hdr = None
        for ln in mgstat_text.splitlines():
            parts = [p.strip() for p in ln.split(',')]
            if 'pGblNsz' in ln or 'pGblAsz' in ln:
                hdr = {v.lower(): i for i, v in enumerate(parts)}
            elif hdr and re.match(r'\d{2}/\d{2}', parts[0]):
                try:
                    if 'pgblnsz' in hdr:
                        nseize_vals.append(float(parts[hdr['pgblnsz']]))
                except (ValueError, IndexError):
                    pass
        if nseize_vals:
            avg_n = sum(nseize_vals) / len(nseize_vals)
            ev = (f'Source: <b>mgstat</b> &mdash; pGblNsz avg&nbsp;{avg_n:.1f}%'
                  f' across {len(nseize_vals)} samples &middot; threshold: &gt;5% → red, &gt;1% → amber')
            if avg_n > 5:
                signals.append(('red', _pill('red',
                    f'<b>High NSeize contention</b>: avg {avg_n:.1f}% global seize failures. Processes are sleeping on lock.', ev)))
            elif avg_n > 1:
                signals.append(('amber', _pill('amber',
                    f'<b>Elevated NSeize rate</b>: avg {avg_n:.1f}% global seize failures.', ev)))

    irisd_text = texts.get('irisstat-D', '')
    if irisd_text:
        crit = ['Global', 'LockHTAB', 'LockLHB', 'TransCB']
        for name in crit:
            m = re.search(
                rf'^\s*\d+\s*-\s*{name}\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
                irisd_text, re.MULTILINE
            )
            if m:
                seize, _, _, bseize = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                if bseize > 0 and seize > 0:
                    pct = bseize / seize * 100
                    ev = (f'Source: <b>irisstat-D</b> &mdash; {name}: {bseize} Bseize of {seize} total'
                          f' ({pct:.2f}%) &middot; threshold: &gt;1% → red')
                    signals.append(('red' if pct > 1 else 'amber', _pill(
                        'red' if pct > 1 else 'amber',
                        f'<b>{name} lock contention</b>: {bseize} blocking seize(s) ({pct:.2f}% of {seize} total). Processes sleeping on this lock.', ev)))

    if not signals:
        return None
    level = 'red' if any(s[0] == 'red' for s in signals) else 'amber' if any(s[0] == 'amber' for s in signals) else 'green'
    return level, ''.join(html for _, html in signals)


def _analyse_filesystem_combined(texts: dict) -> tuple[str, str] | None:
    """Cross-reference df -m and mount to produce a unified per-filesystem view."""
    df_text    = texts.get('df-m', '')
    mount_text = texts.get('mount', '')
    if not df_text and not mount_text:
        return None

    df_rows: dict[str, dict] = {}
    if df_text:
        for ln in df_text.splitlines():
            parts = ln.split()
            if len(parts) < 6:
                continue
            try:
                mp    = parts[-1]
                pct   = int(parts[-2].rstrip('%'))
                avail = int(parts[-3])
                used  = int(parts[-4])
                total = int(parts[-5])
                fs    = ' '.join(parts[:-5])
            except (ValueError, IndexError):
                continue
            if not mp.startswith('/'):
                continue
            df_rows[mp] = {'total': total, 'used': used, 'avail': avail, 'pct': pct, 'fs': fs}

    _VIRT = {'sysfs','proc','devtmpfs','securityfs','tmpfs','devpts','cgroup','cgroup2',
              'pstore','efivarfs','bpf','rpc_pipefs','autofs','hugetlbfs','mqueue',
              'debugfs','fusectl','binfmt_misc','tracefs','configfs','sunrpc'}
    mount_rows: dict[str, dict] = {}
    if mount_text:
        for ln in mount_text.splitlines():
            m = re.match(r'(.+?) on (/\S*) type (\S+) \((.+)\)', ln)
            if not m:
                continue
            device, mp, fstype, opts_str = m.groups()
            if fstype in _VIRT:
                continue
            opts = {k: v for k, _, v in (p.partition('=') for p in opts_str.split(','))}
            mount_rows[mp] = {
                'device': device.strip(),
                'fstype': fstype,
                'opts_str': opts_str,
                'opts': opts,
                'rw': 'rw' in opts_str.split(','),
                'soft': 'soft' in opts_str.split(','),
                'vers': opts.get('vers', '—'),
            }

    all_mps = sorted(set(list(df_rows.keys()) + list(mount_rows.keys())))
    if not all_mps:
        return None

    _IRIS_PATHS = ('iris', 'hs-', '/db', '/jrn', '/sys', '/mgr')

    def _fmt_mb(mb: int) -> str:
        if mb >= 1024 * 1024:
            return f'{mb/(1024*1024):.1f} TB'
        if mb >= 1024:
            return f'{mb/1024:.1f} GB'
        return f'{mb} MB'

    def _pct_badge(pct: int) -> str:
        colour = '#ef4444' if pct >= 90 else '#f59e0b' if pct >= 75 else '#22c55e'
        return (f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;'
                f'background:{colour};color:white;font-weight:700;font-size:0.75rem">'
                f'{pct}%</span>')

    TBL_ID = 'synth-fstable'
    th_s = ('padding:5px 10px;text-align:left;font-size:0.72rem;font-weight:700;color:#555;'
            'text-transform:uppercase;letter-spacing:.05em;border-bottom:2px solid #dde3ee;'
            'white-space:nowrap;cursor:pointer')
    headers = ['Mount Point', 'Type', 'Size', 'Used', 'Avail', 'Use%', 'Access', 'Mode']
    ths = ''.join(
        f'<th style="{th_s}" onclick="sortTable(\'{TBL_ID}\',{i},this)">{h} &#8597;</th>'
        for i, h in enumerate(headers)
    )

    tbody = ''
    for i, mp in enumerate(all_mps):
        bg = '#f8f9fc' if i % 2 == 0 else 'white'
        df  = df_rows.get(mp)
        mnt = mount_rows.get(mp)
        iris = any(p in mp.lower() for p in _IRIS_PATHS)
        mp_label = f'<b>{mp}</b>' if iris else mp

        size_  = _fmt_mb(df['total']) if df else '—'
        used_  = _fmt_mb(df['used'])  if df else '—'
        avail_ = _fmt_mb(df['avail']) if df else '—'
        pct_   = _pct_badge(df['pct']) if df else '—'
        fstype = mnt['fstype'] if mnt else (df['fs'].split('/')[-1] if df else '—')
        access = ('<span style="color:#ef4444;font-weight:700">ro</span>'
                  if mnt and not mnt['rw'] else 'rw') if mnt else '—'
        mode   = ('<span style="color:#ef4444;font-weight:700">soft</span>'
                  if mnt and mnt['soft'] else 'hard') if mnt else '—'

        def _td(val, align='left'):
            return (f'<td style="padding:4px 10px;font-size:0.78rem;color:#222;'
                    f'text-align:{align};white-space:nowrap">{val}</td>')

        tbody += (f'<tr style="background:{bg}">'
                  + _td(mp_label) + _td(fstype) + _td(size_, 'right')
                  + _td(used_, 'right') + _td(avail_, 'right')
                  + _td(pct_, 'center') + _td(access, 'center') + _td(mode, 'center')
                  + '</tr>')

    table = (f'<div style="overflow-x:auto">'
             f'<div style="font-size:0.72rem;color:#888;margin-bottom:6px">'
             f'<b>Bold</b> mount points are IRIS paths. '
             f'<span style="color:#ef4444;font-weight:700">soft</span> = '
             f'silently drops I/O on timeout. '
             f'<span style="color:#ef4444;font-weight:700">ro</span> = read-only. '
             f'Click any column header to sort.</div>'
             f'<table id="{TBL_ID}" style="border-collapse:collapse;width:100%">'
             f'<thead><tr>{ths}</tr></thead><tbody>{tbody}</tbody></table></div>')

    has_red   = any(df_rows.get(mp, {}).get('pct', 0) >= 90 for mp in all_mps)
    has_amber = any(df_rows.get(mp, {}).get('pct', 0) >= 75 for mp in all_mps)
    has_soft_iris = any(
        mount_rows.get(mp, {}).get('soft') and any(p in mp.lower() for p in _IRIS_PATHS)
        for mp in all_mps
    )
    level = 'red' if has_red else 'amber' if (has_amber or has_soft_iris) else 'green'
    return level, table


# ── Top-level signal strip ────────────────────────────────────────────────────

def _signal_strip(subsections: list[tuple[str, str, str]]) -> str:
    chips = []
    for title, level, sub_id in subsections:
        bg, border, fg, dot = _COLOURS[level]
        chips.append(
            f'<span onclick="synthToggle(\'{sub_id}\');document.getElementById(\'synth-{sub_id}\').scrollIntoView({{behavior:\'smooth\',block:\'nearest\'}})" '
            f'style="display:inline-flex;align-items:center;gap:5px;padding:4px 10px;'
            f'background:{bg};border:1px solid {border};border-radius:12px;'
            f'font-size:0.75rem;color:{fg};cursor:pointer;user-select:none;white-space:nowrap" '
            f'title="Click to expand">'
            f'<span style="color:{dot}">&#9679;</span>{title}</span>'
        )
    return ('<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">'
            + ''.join(chips) + '</div>')


# ── JavaScript for subsection toggle ─────────────────────────────────────────

SYNTHESIS_JS = """
<script>
(function() {
  window.synthToggle = function(id) {
    var body = document.getElementById('synth-body-' + id);
    var chev = document.getElementById('synth-chev-' + id);
    if (!body) return;
    var hidden = body.style.display === 'none';
    body.style.display = hidden ? 'block' : 'none';
    if (chev) chev.textContent = hidden ? '▾' : '▸';
  };
})();
</script>
"""

# ── CSS for synthesis panel ───────────────────────────────────────────────────

SYNTHESIS_CSS = """
<style>
.synth-panel {
  background: var(--card, #fff);
  border: 1px solid var(--sidebar-border, #dde3ee);
  border-radius: 10px;
  margin: 0 0 20px 0;
  overflow: hidden;
}
.synth-panel-header {
  background: #003366;
  color: #fff;
  padding: 12px 18px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.synth-panel-title {
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: .03em;
}
.synth-panel-subtitle {
  font-size: 0.72rem;
  opacity: .7;
}
.synth-panel-body {
  padding: 16px 18px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.synth-sub {
  border: 1px solid var(--sidebar-border, #dde3ee);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}
.synth-sub-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  background: var(--raw-bg, #f8f9fc);
  cursor: pointer;
  user-select: none;
}
.synth-sub-header:hover { background: #eef2f7; }
.synth-sub-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text, #1a1a2e);
  flex: 1;
}
.synth-chevron {
  font-size: 0.85rem;
  color: var(--text-dim, #778);
  margin-left: auto;
}
.synth-sub-body {
  padding: 12px 14px;
  background: var(--card, #fff);
}
</style>
"""


# ── Public entry point ────────────────────────────────────────────────────────

async def synthesize(section_texts: dict[str, str]) -> str:
    sub_results: list[tuple[str, str, str, str]] = []  # (title, level, sub_id, body)

    checks = [
        ('Memory',           'memory',  _analyse_memory),
        ('CPU',              'cpu',     _analyse_cpu),
        ('Disk & Storage',   'disk',    _analyse_disk),
        ('IRIS Health',      'iris',    _analyse_iris),
        ('Filesystem View',  'fsview',  _analyse_filesystem_combined),
    ]

    for title, sub_id, fn in checks:
        try:
            result = fn(section_texts)
        except Exception:
            continue
        if result is None:
            continue
        level, body = result
        sub_results.append((title, level, sub_id, body))

    if len(sub_results) < 2:
        return ''

    strip = _signal_strip([(t, l, sid) for t, l, sid, _ in sub_results])

    subs_html = ''
    for title, level, sub_id, body in sub_results:
        subs_html += _subsection(title, level, sub_id, body)

    collapse_ids = [sid for _, level, sid, _ in sub_results if level != 'red']
    collapse_js = ''
    if collapse_ids:
        ids_json = ', '.join(f'"{sid}"' for sid in collapse_ids)
        collapse_js = (
            f'<script>'
            f'[{ids_json}].forEach(function(id){{'
            f'  var b=document.getElementById("synth-body-"+id);'
            f'  var c=document.getElementById("synth-chev-"+id);'
            f'  if(b)b.style.display="none";'
            f'  if(c)c.textContent="▸";'
            f'}});'
            f'</script>'
        )

    return (
        SYNTHESIS_CSS
        + SYNTHESIS_JS
        + '<div class="synth-panel" id="synth-panel">'
        + '<div class="synth-panel-header">'
        + '<div>'
        + '<div class="synth-panel-title">&#9781; Performance Summary</div>'
        + '<div class="synth-panel-subtitle">Cross-section analysis — expand a subsection for detail</div>'
        + '</div>'
        + '</div>'
        + '<div class="synth-panel-body">'
        + strip
        + subs_html
        + '</div>'
        + '</div>'
        + collapse_js
    )
