import re


def _parse_kv(text: str) -> dict:
    """Parse systeminfo key-value output into a dict."""
    kv = {}
    current_key = None
    for line in text.splitlines():
        m = re.match(r'^([A-Za-z][^:]{2,}?):\s{2,}(.+)', line)
        if m:
            current_key = m.group(1).strip()
            kv[current_key] = m.group(2).strip()
        elif current_key and line.startswith(' ') and line.strip():
            kv[current_key] += ' ' + line.strip()
    return kv


def _mb(value_str: str) -> float:
    """Extract numeric MB value from strings like '32,513 MB'."""
    m = re.search(r'[\d,]+', value_str)
    if not m:
        return 0.0
    return float(m.group().replace(',', ''))


def _card(label: str, value: str, sub: str = '', color: str = '#003366') -> str:
    return f'''
<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;padding:14px 18px;min-width:160px;flex:1">
  <div style="font-size:0.75rem;color:#666;text-transform:uppercase;letter-spacing:.05em">{label}</div>
  <div style="font-size:1.4rem;font-weight:700;color:{color};margin:4px 0">{value}</div>
  {f'<div style="font-size:0.75rem;color:#888">{sub}</div>' if sub else ''}
</div>'''


async def analyze(section_text: str) -> str:
    kv = _parse_kv(section_text)
    if not kv:
        return ''

    total_ram   = _mb(kv.get('Total Physical Memory', '0'))
    avail_ram   = _mb(kv.get('Available Physical Memory', '0'))
    used_ram    = total_ram - avail_ram
    used_pct    = (used_ram / total_ram * 100) if total_ram else 0

    virt_max    = _mb(kv.get('Virtual Memory: Max Size', '0'))
    virt_avail  = _mb(kv.get('Virtual Memory: Available', '0'))
    virt_used   = virt_max - virt_avail
    virt_pct    = (virt_used / virt_max * 100) if virt_max else 0

    hostname    = kv.get('Host Name', 'N/A')
    os_name     = kv.get('OS Name', 'N/A')
    os_ver      = kv.get('OS Version', '')
    model       = kv.get('System Model', 'N/A')
    cpu         = kv.get('Processor(s)', 'N/A')
    boot_time   = kv.get('System Boot Time', 'N/A')
    domain      = kv.get('Domain', 'N/A')
    tz          = kv.get('Time Zone', 'N/A')

    ram_color   = '#c0392b' if used_pct > 85 else '#e67e22' if used_pct > 70 else '#27ae60'
    virt_color  = '#c0392b' if virt_pct > 85 else '#e67e22' if virt_pct > 70 else '#27ae60'

    # RAM gauge bar
    def gauge(pct, color):
        return f'''
<div style="background:#e0e0e0;border-radius:4px;height:10px;margin-top:6px">
  <div style="width:{pct:.1f}%;background:{color};border-radius:4px;height:10px"></div>
</div>
<div style="font-size:0.7rem;color:#888;margin-top:2px">{pct:.1f}% used</div>'''

    cards = (
        _card('Host', hostname) +
        _card('OS', os_name, os_ver) +
        _card('Model', model, cpu[:60] if cpu != 'N/A' else '') +
        f'''
<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;padding:14px 18px;min-width:160px;flex:1">
  <div style="font-size:0.75rem;color:#666;text-transform:uppercase;letter-spacing:.05em">Physical RAM</div>
  <div style="font-size:1.4rem;font-weight:700;color:{ram_color};margin:4px 0">{used_ram/1024:.1f} / {total_ram/1024:.1f} GB</div>
  {gauge(used_pct, ram_color)}
</div>''' +
        f'''
<div style="background:#f8f9fc;border:1px solid #dde3ee;border-radius:8px;padding:14px 18px;min-width:160px;flex:1">
  <div style="font-size:0.75rem;color:#666;text-transform:uppercase;letter-spacing:.05em">Virtual Memory</div>
  <div style="font-size:1.4rem;font-weight:700;color:{virt_color};margin:4px 0">{virt_used/1024:.1f} / {virt_max/1024:.1f} GB</div>
  {gauge(virt_pct, virt_color)}
</div>''' +
        _card('Boot Time', boot_time) +
        _card('Domain', domain, tz)
    )

    return f'''
<div style="margin:16px 0 24px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <div style="font-size:0.8rem;font-weight:600;color:#555;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em">System Summary</div>
  <div style="display:flex;flex-wrap:wrap;gap:10px">
    {cards}
  </div>
</div>
'''
