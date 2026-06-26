import re


def _parse_lscpu(text: str) -> dict:
    """Parse lscpu key:value output into a dict."""
    kv = {}
    for line in text.splitlines():
        m = re.match(r'^([^:]+):\s+(.+)', line)
        if m:
            kv[m.group(1).strip()] = m.group(2).strip()
    return kv


def _float(s: str) -> float:
    try:
        return float(re.search(r'[\d.]+', s).group())
    except Exception:
        return 0.0


def _int(s: str) -> int:
    try:
        return int(re.search(r'\d+', s).group())
    except Exception:
        return 0


def _card(label: str, value: str, sub: str = '') -> str:
    return f'''
<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;padding:14px 18px;min-width:150px;flex:1">
  <div style="font-size:0.72rem;color:#666;text-transform:uppercase;letter-spacing:.05em">{label}</div>
  <div style="font-size:1.3rem;font-weight:700;color:#003366;margin:4px 0;line-height:1.2">{value}</div>
  {f'<div style="font-size:0.72rem;color:#888;margin-top:2px">{sub}</div>' if sub else ''}
</div>'''


def _insight(level: str, text: str) -> str:
    cfg = {
        'red':   ('#fef2f2', '#dc2626', '#fee2e2', '✖'),
        'amber': ('#fffbeb', '#d97706', '#fef3c7', '⚠'),
        'info':  ('#eff6ff', '#2563eb', '#dbeafe', 'ℹ'),
        'green': ('#f0fdf4', '#16a34a', '#dcfce7', '✔'),
    }
    bg, fg, border_bg, icon = cfg.get(level, cfg['info'])
    return f'''
<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:{bg};border-left:3px solid {fg};border-radius:4px;margin-bottom:6px">
  <span style="color:{fg};font-size:1rem;flex-shrink:0">{icon}</span>
  <span style="font-size:0.8rem;color:#1a1a2e;line-height:1.5">{text}</span>
</div>'''


async def analyze(section_text: str) -> str:
    kv = _parse_lscpu(section_text)
    if not kv:
        return ''

    # --- extract fields ---
    arch         = kv.get('Architecture', 'N/A')
    model_name   = kv.get('Model name', kv.get('CPU', 'N/A'))
    vendor       = kv.get('Vendor ID', '')
    sockets      = _int(kv.get('Socket(s)', '1'))
    cores_per    = _int(kv.get('Core(s) per socket', '1'))
    threads_per  = _int(kv.get('Thread(s) per core', '1'))
    cpus         = _int(kv.get('CPU(s)', str(sockets * cores_per * threads_per)))
    numa_nodes   = _int(kv.get('NUMA node(s)', '1'))
    max_mhz      = _float(kv.get('CPU max MHz', kv.get('CPU MHz', '0')))
    min_mhz      = _float(kv.get('CPU min MHz', '0'))
    cur_mhz      = _float(kv.get('CPU MHz', '0'))
    l1d          = kv.get('L1d cache', '')
    l1i          = kv.get('L1i cache', '')
    l2           = kv.get('L2 cache', '')
    l3           = kv.get('L3 cache', '')
    flags        = kv.get('Flags', kv.get('flags', ''))
    virt_type    = kv.get('Virtualization type', kv.get('Hypervisor vendor', ''))
    hypervisor   = kv.get('Hypervisor vendor', '')
    stepping     = kv.get('Stepping', '')
    cpu_family   = kv.get('CPU family', '')
    bogomips     = _float(kv.get('BogoMIPS', '0'))

    physical_cores = sockets * cores_per
    logical_cpus   = physical_cores * threads_per

    # --- L3 per physical core ---
    l3_per_core_mb = None
    if l3:
        m = re.search(r'([\d.]+)\s*(K|M|G)?', l3, re.IGNORECASE)
        if m:
            val  = float(m.group(1))
            unit = (m.group(2) or 'K').upper()
            l3_mb = val / 1024 if unit == 'K' else val if unit == 'M' else val * 1024
            l3_per_core_mb = l3_mb / physical_cores if physical_cores else None

    # --- is_vm ---
    is_vm = bool(hypervisor or virt_type)
    has_ht = threads_per > 1

    # --- flag checks ---
    has_numa_flag  = 'numa' in flags.lower() or numa_nodes > 1
    has_aes        = 'aes' in flags.lower()
    has_avx        = 'avx' in flags.lower()
    has_avx512     = 'avx512f' in flags.lower()

    # ---- Build cards ----
    freq_val = f'{max_mhz/1000:.2f} GHz' if max_mhz else (f'{cur_mhz/1000:.2f} GHz' if cur_mhz else 'N/A')
    freq_sub = f'min {min_mhz/1000:.2f} GHz' if min_mhz and max_mhz else ''

    topo_sub = f'{sockets} socket{"s" if sockets > 1 else ""} × {cores_per} core{"s" if cores_per > 1 else ""} × {threads_per} thread{"s" if threads_per > 1 else ""}'

    cards_html = (
        _card('Model', model_name[:40] + ('…' if len(model_name) > 40 else ''), vendor) +
        _card('Physical Cores', str(physical_cores), topo_sub) +
        _card('Logical CPUs', str(logical_cpus), 'Hyper-Threading on' if has_ht else 'No Hyper-Threading') +
        _card('Max Frequency', freq_val, freq_sub) +
        _card('NUMA Nodes', str(numa_nodes), f'~{logical_cpus // numa_nodes} CPUs/node' if numa_nodes > 1 else 'UMA (single node)') +
        (_card('L3 Cache', l3, f'{l3_per_core_mb:.1f} MB/core' if l3_per_core_mb else '') if l3 else '') +
        (_card('Environment', ('VM — ' + hypervisor) if hypervisor else 'Virtual Machine', virt_type) if is_vm else _card('Environment', 'Bare Metal', arch)) +
        (_card('L2 Cache', l2) if l2 else '')
    )

    # ---- Build insights ----
    insights = []

    # Frequency insight
    if max_mhz:
        if max_mhz < 2000:
            insights.append(_insight('red', f'<b>Low max CPU frequency: {max_mhz/1000:.2f} GHz.</b> IRIS workloads are highly single-thread sensitive — low clock speed is a primary cause of slower throughput vs. a faster system.'))
        elif max_mhz < 2800:
            insights.append(_insight('amber', f'<b>Moderate CPU frequency: {max_mhz/1000:.2f} GHz.</b> Compare with the faster system — a significant GHz gap (>20%) will directly impact IRIS response times.'))
        else:
            insights.append(_insight('green', f'<b>CPU frequency looks healthy: {max_mhz/1000:.2f} GHz.</b> If this system is slower, look at core count, NUMA, cache, or I/O rather than raw clock speed.'))

    # Frequency throttling
    if max_mhz and cur_mhz and cur_mhz < max_mhz * 0.85:
        insights.append(_insight('red', f'<b>CPU is running below max frequency ({cur_mhz/1000:.2f} GHz vs max {max_mhz/1000:.2f} GHz).</b> This suggests thermal throttling, power-cap limits (common in VMs), or a power governor set to "powersave". Check <code>cpupower frequency-info</code> and thermal logs.'))

    # HT insight
    if not has_ht:
        insights.append(_insight('info', '<b>Hyper-Threading is disabled.</b> This halves visible CPU count. It can be intentional for latency-sensitive IRIS workloads, but compare with the other system — if it has HT on, the raw CPU counts will differ.'))

    # Core count comparison hint
    if physical_cores < 8:
        insights.append(_insight('amber', f'<b>Only {physical_cores} physical core{"s" if physical_cores > 1 else ""}.</b> Low core count limits parallelism for concurrent IRIS users. Check whether the faster system has more cores.'))

    # NUMA
    if numa_nodes > 1:
        cpus_per_node = logical_cpus // numa_nodes
        insights.append(_insight('amber', f'<b>NUMA: {numa_nodes} nodes, ~{cpus_per_node} CPUs each.</b> If IRIS is not NUMA-aware or spans nodes, cross-node memory latency (~2× slower) can cause uneven performance. Check <code>numactl --hardware</code> and IRIS NUMA settings.'))

    # L3 per core
    if l3_per_core_mb is not None:
        if l3_per_core_mb < 2:
            insights.append(_insight('amber', f'<b>Low L3 cache per core: {l3_per_core_mb:.1f} MB/core.</b> Small per-core cache increases cache misses under concurrent load. The faster system may have a larger L3 — compare this value directly.'))
        else:
            insights.append(_insight('green', f'<b>L3 cache per core: {l3_per_core_mb:.1f} MB/core.</b> Adequate cache per core helps IRIS keep hot globals in CPU cache.'))

    # VM penalty
    if is_vm:
        vm_env = hypervisor or virt_type or 'unknown hypervisor'
        insights.append(_insight('amber', f'<b>Running inside a virtual machine ({vm_env}).</b> CPU steal time, vCPU scheduling latency, and overcommitted resources can cause irregular slowdowns that don\'t appear in lscpu. Check <code>vmstat</code> for CPU steal and compare with a bare-metal peer.'))

    # Multi-socket
    if sockets > 1:
        insights.append(_insight('info', f'<b>{sockets}-socket system.</b> Ensure IRIS is configured to take advantage of all sockets. Cross-socket memory access incurs NUMA penalties — verify IRIS affinity settings.'))

    # BogoMIPS hint
    if bogomips and max_mhz:
        expected_bogomips = max_mhz * 2 / 1000 * 1000  # ~2× GHz in MHz units
        if bogomips < expected_bogomips * 0.8:
            insights.append(_insight('amber', f'<b>BogoMIPS ({bogomips:,.0f}) is lower than expected for this frequency.</b> This can indicate a VM with a mismatched timer, or a kernel with frequency scaling active during boot.'))

    insights_html = ''
    if insights:
        insights_html = '<!--INS-->' + f'''
<div style="margin-top:16px">
  <div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">Insights — comparing two systems</div>
  {''.join(insights)}
</div>''' + '<!--/INS-->'

    # ---- Comparison table hint ----
    compare_rows = [
        ('Architecture', arch),
        ('CPU Model', model_name),
        ('Physical Cores', str(physical_cores)),
        ('Logical CPUs', str(logical_cpus)),
        ('Sockets', str(sockets)),
        ('Cores/Socket', str(cores_per)),
        ('Threads/Core', str(threads_per)),
        ('Max Frequency', freq_val),
        ('L1d / L1i', f'{l1d} / {l1i}' if l1d or l1i else '—'),
        ('L2 Cache', l2 or '—'),
        ('L3 Cache', l3 or '—'),
        ('L3/Core', f'{l3_per_core_mb:.1f} MB' if l3_per_core_mb else '—'),
        ('NUMA Nodes', str(numa_nodes)),
        ('Hyper-Threading', 'Yes' if has_ht else 'No'),
        ('Environment', ('VM (' + (hypervisor or virt_type) + ')') if is_vm else 'Bare Metal'),
        ('AES-NI', 'Yes' if has_aes else 'No'),
        ('AVX / AVX-512', ('AVX-512' if has_avx512 else 'AVX') if has_avx else 'No'),
    ]
    rows_html = ''.join(
        f'<tr style="border-bottom:1px solid #f0f2f5">'
        f'<td style="padding:6px 12px;font-size:0.78rem;color:#556;white-space:nowrap;font-weight:500">{k}</td>'
        f'<td style="padding:6px 12px;font-size:0.78rem;color:#1a1a2e;font-family:monospace">{v}</td>'
        f'</tr>'
        for k, v in compare_rows if v and v != 'N/A'
    )
    table_html = f'''
<div style="margin-top:16px">
  <div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">Key metrics for side-by-side comparison</div>
  <div style="overflow-x:auto">
    <table style="border-collapse:collapse;background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;overflow:hidden;min-width:340px">
      {rows_html}
    </table>
  </div>
  <div style="font-size:0.72rem;color:#aaa;margin-top:6px">Copy this table from both SystemPerformance reports to compare systems directly.</div>
</div>'''

    return f'''
<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em">CPU Summary</div>
  <div style="display:flex;flex-wrap:wrap;gap:10px">
    {cards_html}
  </div>
  {insights_html}
  {table_html}
</div>
'''
