"""
Analyzer for the 'mount' section in Linux pButtons files.

Format: one mount per line:
  <device> on <mountpoint> type <fstype> (<options,...>)

Device can contain spaces (long CIFS/NFS share paths), so parsing anchors on
" on /<path> type <word> (" from the right of each line.
"""
import re

_MOUNT_RE = re.compile(
    r'^(.+?) on (\/\S*) type (\S+) \((.+)\)\s*$'
)

_VIRTUAL_TYPES = frozenset({
    'sysfs', 'proc', 'devtmpfs', 'securityfs', 'tmpfs', 'devpts', 'cgroup',
    'cgroup2', 'pstore', 'efivarfs', 'bpf', 'rpc_pipefs', 'autofs',
    'hugetlbfs', 'mqueue', 'debugfs', 'fusectl', 'binfmt_misc', 'tracefs',
    'configfs', 'sunrpc', 'selinuxfs', 'systemd-1', 'overlay', 'nsfs',
})

_LOCAL_TYPES  = frozenset({'xfs', 'ext4', 'ext3', 'ext2', 'btrfs', 'zfs', 'vfat', 'ntfs'})
_NETWORK_TYPES = frozenset({'cifs', 'nfs', 'nfs4', 'nfs3', 'smb', 'smbfs'})

_IRIS_PATHS = ('iris', 'cache', 'ensemble', 'healthshare', 'hs-', '/mgr', '/db', '/jrn', '/sys')


def _parse_mounts(text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('<'):
            continue
        m = _MOUNT_RE.match(line)
        if not m:
            continue
        device, mountpoint, fstype, opts_str = m.groups()
        opts = {k: v for k, _, v in
                (p.partition('=') for p in opts_str.split(','))}
        entries.append({
            'device':     device.strip(),
            'mountpoint': mountpoint,
            'fstype':     fstype,
            'opts_str':   opts_str,
            'opts':       opts,
            'rw':         'rw' in opts_str.split(','),
        })
    return entries


def _opt(opts: dict, key: str, default: str = '—') -> str:
    return opts[key] if key in opts else default


def _is_iris(mp: str) -> bool:
    mp_lower = mp.lower()
    return any(p in mp_lower for p in _IRIS_PATHS)


def _fmt_bytes(val: str) -> str:
    try:
        b = int(val)
        return f'{b // 1024}K' if b >= 1024 else f'{b}B'
    except (ValueError, TypeError):
        return val


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
    th_base = ('padding:5px 10px;font-size:0.72rem;font-weight:700;color:#555;'
               'text-transform:uppercase;letter-spacing:.05em;'
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
            last = j == len(row) - 1
            ws = 'white-space:normal;word-break:break-all' if last else 'white-space:nowrap'
            tds += (f'<td style="padding:4px 10px;font-size:0.78rem;color:#222;'
                    f'text-align:{align};{ws}">{cell}</td>')
        tbody += f'<tr style="background:{bg}">{tds}</tr>'
    return (f'<table{id_attr} style="border-collapse:collapse;width:100%;margin-bottom:16px">'
            f'<thead><tr>{ths}</tr></thead><tbody>{tbody}</tbody></table>')


def _section_heading(title: str, subtitle: str = '') -> str:
    sub = (f'<span style="font-size:0.72rem;color:#888;font-weight:400;margin-left:8px">'
           f'{subtitle}</span>') if subtitle else ''
    return (f'<div style="font-size:0.78rem;font-weight:600;color:#333;margin:14px 0 6px 0">'
            f'{title}{sub}</div>')


async def analyze(section_text: str) -> str:
    all_mounts = _parse_mounts(section_text)
    if not all_mounts:
        return ''

    real    = [m for m in all_mounts if m['fstype'] not in _VIRTUAL_TYPES]
    local   = [m for m in real if m['fstype'] in _LOCAL_TYPES]
    network = [m for m in real if m['fstype'] in _NETWORK_TYPES]
    ro_real = [m for m in real if not m['rw']]
    virtual = [m for m in all_mounts if m['fstype'] in _VIRTUAL_TYPES]

    # ── Insights ──────────────────────────────────────────────────────────────
    flags = []

    # Soft network mounts — can silently drop I/O on timeout
    soft_net = [m for m in network if 'soft' in m['opts_str'].split(',')]
    if soft_net:
        iris_soft = [m for m in soft_net if _is_iris(m['mountpoint'])]
        if iris_soft:
            paths = ', '.join(m['mountpoint'] for m in iris_soft[:3])
            flags.append(_flag('amber',
                f'<b>IRIS path(s) mounted with <code>soft</code></b>: {paths}. '
                f'Soft mounts silently return I/O errors after a timeout instead of retrying — '
                f'this can cause data corruption or silent write failures on IRIS databases. '
                f'Consider <code>hard</code> with <code>timeo</code> and <code>retrans</code> tuning.'))
        else:
            n = len(soft_net)
            flags.append(_flag('info',
                f'{n} network mount{"s" if n > 1 else ""} use <code>soft</code> '
                f'(silently drops I/O on timeout). None are IRIS paths, but verify data '
                f'integrity requirements for these shares.'))

    # Read-only real mounts
    for m in ro_real:
        iris_note = ' (IRIS path)' if _is_iris(m['mountpoint']) else ''
        level = 'amber' if _is_iris(m['mountpoint']) else 'info'
        flags.append(_flag(level,
            f'<b>{m["mountpoint"]}{iris_note} is mounted read-only</b> '
            f'(type: {m["fstype"]}).'))

    # NFS sync option — safe but can hurt write throughput
    nfs_sync = [m for m in network
                if m['fstype'] in ('nfs', 'nfs4', 'nfs3')
                and 'sync' in m['opts_str'].split(',')]
    if nfs_sync:
        paths = ', '.join(m['mountpoint'] for m in nfs_sync[:3])
        flags.append(_flag('info',
            f'<b>NFS <code>sync</code> mount(s)</b>: {paths}. '
            f'Synchronous NFS writes wait for server acknowledgement — safe but '
            f'reduces write throughput. Use only where write-ordering guarantees are required.'))

    if not flags:
        flags.append(_flag('green',
            f'No notable mount configuration issues detected. '
            f'{len(network)} network mount{"s" if len(network) != 1 else ""}, '
            f'all appear to use safe options.'))

    insights_html = (
        '<!--INS-->'
        '<div style="margin-bottom:14px">'
        '<div style="font-size:0.72rem;font-weight:700;color:#555;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px">Insights</div>'
        + ''.join(flags) + '</div>'
        + '<!--/INS-->'
    )

    # ── Stat cards ────────────────────────────────────────────────────────────
    stats_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">'
        + _stat('Total mounts', str(len(all_mounts)))
        + _stat('Local filesystems', str(len(local)))
        + _stat('Network mounts', str(len(network)))
        + _stat('Virtual/pseudo', str(len(virtual)))
        + _stat('Read-only', str(len(ro_real)))
        + '</div>'
    )

    # ── Filesystem type summary ───────────────────────────────────────────────
    type_counts: dict[str, int] = {}
    for m in all_mounts:
        type_counts[m['fstype']] = type_counts.get(m['fstype'], 0) + 1

    type_rows = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    category = lambda t: ('Virtual' if t in _VIRTUAL_TYPES
                          else 'Local' if t in _LOCAL_TYPES
                          else 'Network' if t in _NETWORK_TYPES
                          else 'Other')
    type_table_html = (
        _section_heading('Filesystem Types')
        + _table(
            ['Type', 'Category', 'Count'],
            [[t, category(t), str(c)] for t, c in type_rows],
            ['left', 'left', 'right'],
        )
    )

    # ── Local filesystem table ────────────────────────────────────────────────
    local_table_html = ''
    if local:
        def _local_opts(m: dict) -> str:
            parts = []
            if not m['rw']:
                parts.append('<span style="color:#ef4444;font-weight:700">ro</span>')
            opts = m['opts_str'].split(',')
            for flag in ('noquota', 'quota', 'noexec', 'nosuid', 'noatime', 'relatime'):
                if flag in opts:
                    parts.append(flag)
            return ', '.join(parts) if parts else '—'

        local_table_html = (
            _section_heading('Local Filesystems')
            + _table(
                ['Mount Point', 'Device', 'Type', 'Notable Options'],
                [[m['mountpoint'], m['device'], m['fstype'], _local_opts(m)]
                 for m in sorted(local, key=lambda x: x['mountpoint'])],
                ['left', 'left', 'left', 'left'],
                table_id='mount-local',
            )
        )

    # ── Network mounts table ──────────────────────────────────────────────────
    network_table_html = ''
    if network:
        def _net_row(m: dict) -> list:
            opts = m['opts']
            vers    = _opt(opts, 'vers')
            addr    = _opt(opts, 'addr')
            rsize   = _fmt_bytes(_opt(opts, 'rsize', ''))
            wsize   = _fmt_bytes(_opt(opts, 'wsize', ''))
            blksz   = f'r:{rsize} w:{wsize}' if rsize != '—' or wsize != '—' else '—'
            opt_str = m['opts_str'].split(',')
            durability = (
                '<span style="color:#ef4444;font-weight:700">soft</span>'
                if 'soft' in opt_str else 'hard'
            )
            access = (
                '<span style="color:#ef4444;font-weight:700">ro</span>'
                if not m['rw'] else 'rw'
            )
            return [m['mountpoint'], m['device'], m['fstype'],
                    vers, durability, access, blksz, addr]

        network_table_html = (
            _section_heading('Network Mounts',
                             'soft = silently drops I/O on timeout; hard = retries until server responds')
            + _table(
                ['Mount Point', 'Source', 'Type', 'Version', 'Mode', 'Access', 'Block Sizes', 'Server'],
                [_net_row(m) for m in sorted(network, key=lambda x: x['mountpoint'])],
                ['left', 'left', 'left', 'center', 'center', 'center', 'left', 'left'],
                table_id='mount-network',
            )
        )

    return (
        '<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif">'
        '<div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:4px;'
        'text-transform:uppercase;letter-spacing:.06em">mount Analysis</div>'
        f'<div style="font-size:0.72rem;color:#999;margin-bottom:12px">'
        f'{len(all_mounts)} total mounts · {len(local)} local · {len(network)} network</div>'
        + insights_html
        + stats_html
        + type_table_html
        + local_table_html
        + network_table_html
        + '</div>'
    )
