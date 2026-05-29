import re
from dataclasses import dataclass, field
from typing import Optional

# Sections known to contain potentially sensitive information
SENSITIVE_SECTIONS = {
    "Configuration": "Contains instance name, machine name, GUID, license number, and product version.",
    "Profile": "Contains username/email of the person who ran the report and directory paths.",
    "License": "Contains license type, user counts, and feature codes.",
    "CPF file": "Contains full filesystem paths for all databases and namespaces.",
    "IRIS ALL": "Lists all IRIS instances on the machine with their ports and directories.",
    "Windows info": "Contains detailed OS, hardware, and network configuration.",
    "tasklist": "Lists all running processes on the machine.",
}

SECTION_DESCRIPTIONS: dict[str, str] = {
    # Common sections
    "IRIS ALL":      "Lists all IRIS instances on this machine with their ports and installation paths.",
    "License":       "License type, user capacity, and feature codes.",
    "CPF file":      "Full IRIS configuration: databases, namespaces, journal settings, and memory.",
    "mgstat":        "Core IRIS performance counters sampled over time — globals/sec, routine calls, lock table, journal writes.",
    "%SS":           "Per-process snapshot of IRIS activity — CPU, memory, lock state, and open devices.",
    "irisstat -c1":  "Shared memory and cache statistics — buffer hits, evictions, and memory pressure.",
    "irisstat -D":   "Database file I/O statistics — reads, writes, and physical vs. logical ratios per database.",
    "irisstat -R":   "Routine cache statistics — hits, misses, and cache utilization.",
    # Linux sections
    "Linux info":    "OS version, hostname, kernel version, and hardware summary.",
    "cpu":           "CPU topology, core count, clock speeds, and processor capabilities.",
    "ipcs":          "IPC shared memory segments — useful for verifying IRIS shared memory allocation.",
    "lsblk":         "Block device tree — disks, partitions, LUNs, and their sizes.",
    "mount":         "Mounted filesystems with options — check for noatime and barrier settings.",
    "df -m":         "Disk space usage by filesystem — spot full or near-full volumes.",
    "ifconfig":      "Network interface configuration — IP addresses, MTU, and interface flags.",
    "sysctl -a":     "Kernel tuning parameters — hugepages, semaphores, file handles, and TCP settings.",
    "ps":            "Snapshot of all running processes with CPU and memory usage.",
    "vmstat":        "Virtual memory, swap, CPU run queue, and context switches over time.",
    "sar -u":        "CPU utilization history — user, system, iowait, and idle percentages.",
    "free":          "RAM and swap usage — check for swap activity indicating memory pressure.",
    "iostat":        "Disk I/O throughput and latency per device — identify storage bottlenecks.",
    "sar -d":        "Historical disk I/O rates per device — correlate with mgstat spikes.",
    # Windows sections
    "Windows info":  "OS version, hostname, hardware summary, and Windows configuration.",
    "tasklist":      "Snapshot of all running processes with memory usage.",
    "perfmon":       "Windows Performance Monitor counters — CPU, disk, memory, and network over time.",
}


@dataclass
class Section:
    id: str
    title: str
    content_html: str
    sensitive: bool = False
    sensitive_reason: Optional[str] = None


def parse_sections(html: str) -> tuple[str, list[Section]]:
    """
    Parse a pButtons HTML file into its header and individual sections.
    Returns (header_html, [Section, ...]).
    """
    # The header is everything before the first <hr> separator that precedes a section
    # Sections are delimited by <hr size="4" noshade> followed by a div id=...
    # Pattern: find each section start
    section_pattern = re.compile(
        r'(<hr size="4" noshade>|<hr size="4" noshade/>)'
        r'(<b>.*?<div id=["\']?([^"\'>\s]+)["\']?></div>'
        r'(.*?)</font></b>.*?<pre>(.*?)</pre>)'
        r'(?=<p align="right">.*?Back to top|$)',
        re.DOTALL | re.IGNORECASE
    )

    # Simpler approach: split on the hr+section pattern
    # Find all section anchors with their positions
    anchor_pattern = re.compile(
        r'<hr size="4" noshade>\s*<b><font[^>]*>'
        r'<div id=["\']?([^"\'>\s]+)["\']?></div>'
        r'([^<]+)</font></b>',
        re.IGNORECASE
    )

    matches = list(anchor_pattern.finditer(html))

    if not matches:
        return html, []

    # Everything before the first section anchor is the header
    # (includes the nav table and debug comment and Configuration/Profile sections
    #  which use a slightly different pattern)
    header_end = matches[0].start()

    # Also grab Configuration and Profile which use <p>...<div id="..."> pattern
    config_pattern = re.compile(
        r'(<p>\s*<b><font[^>]*><div id=["\']([^"\'>\s]+)["\']></div>'
        r'([^<]+)</font></b></p>)(.*?)'
        r'(?=<hr size="4" noshade>)',
        re.DOTALL | re.IGNORECASE
    )

    sections: list[Section] = []

    # Parse Configuration / Profile (pre-section area)
    for m in config_pattern.finditer(html[:header_end + 5000]):
        section_id = m.group(2)
        title = m.group(3).strip()
        # grab pre content
        pre_match = re.search(r'<pre>(.*?)</pre>', m.group(0), re.DOTALL)
        content = m.group(0)
        sections.append(Section(
            id=section_id,
            title=title,
            content_html=content,
            sensitive=title in SENSITIVE_SECTIONS,
            sensitive_reason=SENSITIVE_SECTIONS.get(title),
        ))

    # Parse main sections
    for i, m in enumerate(matches):
        section_id = m.group(1)
        title = m.group(2).strip()

        # Content runs from this match to the next match (or end)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        content_html = html[start:end]

        sections.append(Section(
            id=section_id,
            title=title,
            content_html=content_html,
            sensitive=title in SENSITIVE_SECTIONS,
            sensitive_reason=SENSITIVE_SECTIONS.get(title),
        ))

    # Build header: nav table + debug comment (before first config section or first hr section)
    # Use the raw html up to the first <p> config block or first hr section
    first_config = config_pattern.search(html)
    if first_config:
        header_html = html[:first_config.start()]
    else:
        header_html = html[:header_end]

    return header_html, sections


_EXCLUDED_PLACEHOLDER = (
    '<pre>\n'
    '    [ This section was excluded by the report author. ]\n'
    '    [ Filtered using pButtons Parser - a free tool that redacts InterSystems IRIS\n'
    '      pButtons files locally, without uploading any data to the cloud. ]\n'
    '</pre>'
)


def _make_excluded_html(content_html: str) -> str:
    """Replace all <pre> content blocks with a single exclusion placeholder."""
    # Remove all pre blocks first, then insert one placeholder at the first position
    first_pre = re.search(r'<pre>', content_html, re.IGNORECASE)
    if not first_pre:
        return content_html
    stripped = re.sub(r'<pre>.*?</pre>', '', content_html, flags=re.DOTALL | re.IGNORECASE)
    return stripped[:first_pre.start()] + _EXCLUDED_PLACEHOLDER + stripped[first_pre.start():]


# Groups define sidebar structure. Sections not listed here appear under "Other".
SECTION_GROUPS = [
    ("System Info",    ["Configuration", "Profile", "IRIS ALL", "License"]),
    ("Configuration",  ["CPFfile"]),
    ("OS",             ["Windowsinfo", "tasklist", "perfmon"]),
    ("IRIS Metrics",   ["mgstat", "%SS"]),
    ("irisstat",       ["irisstat-c1", "irisstat-D", "irisstat-R"]),
]

# Sections collapsed by default (raw data, low immediate value)
COLLAPSED_BY_DEFAULT = {"CPFfile", "irisstat-c1", "irisstat-D", "irisstat-R", "tasklist", "perfmon"}


def _extract_pre_text(content_html: str) -> str:
    """Return plain text from all <pre> blocks in a section's HTML."""
    return '\n'.join(re.findall(r'<pre>(.*?)</pre>', content_html, re.DOTALL | re.IGNORECASE))


def build_output(
    header_html: str,
    sections: list[Section],
    selected_ids: list[str],
    analysis: dict[str, str] | None = None,
) -> str:
    """Build a redesigned HTML output with a fixed sidebar, grouped navigation,
    and collapsible sections. Selected sections show their data; excluded ones
    show a placeholder. Sections with analysis get charts injected above the raw data."""

    selected_set = set(selected_ids)
    analysis = analysis or {}

    # Map id -> Section for quick lookup
    sec_by_id = {s.id: s for s in sections}

    # --- extract metadata from header for the top bar ---
    instance = re.search(r'(\w+) on machine', header_html)
    machine  = re.search(r'on machine (\S+)', header_html)
    run_by   = re.search(r'started by user "([^"]+)"', header_html)
    run_at   = re.search(r'at ([\d:]+) on (.+?)\.', header_html)
    instance_name = instance.group(1) if instance else 'IRIS'
    machine_name  = machine.group(1)  if machine  else ''
    user_name     = run_by.group(1)   if run_by   else ''
    run_time      = f"{run_at.group(1)} {run_at.group(2)}" if run_at else ''

    # --- build sidebar nav ---
    # Assign each section to a group
    grouped: dict[str, list[Section]] = {g: [] for g, _ in SECTION_GROUPS}
    grouped['Other'] = []
    section_to_group: dict[str, str] = {}
    for group_name, ids in SECTION_GROUPS:
        for sid in ids:
            if sid in sec_by_id:
                grouped[group_name].append(sec_by_id[sid])
                section_to_group[sid] = group_name
    for s in sections:
        if s.id not in section_to_group:
            grouped['Other'].append(s)
            section_to_group[s.id] = 'Other'

    nav_html = ''
    for group_name, group_sections in grouped.items():
        if not group_sections:
            continue
        items = ''
        for s in group_sections:
            is_selected = s.id in selected_set
            has_analysis = s.id in analysis
            dot = '<span class="analysis-dot" title="Analysis available"></span>' if has_analysis else ''
            excluded_label = '<span class="excl-badge">excluded</span>' if not is_selected else ''
            items += f'''
<a href="#sec-{s.id}" class="nav-item {'excluded' if not is_selected else ''}" onclick="showSection('{s.id}')">
  {dot}{s.title}{excluded_label}
</a>'''
        nav_html += f'''
<div class="nav-group">
  <div class="nav-group-label" onclick="toggleGroup(this)">{group_name}<span class="chevron">▾</span></div>
  <div class="nav-group-items">{items}</div>
</div>'''

    # --- build section panels ---
    panels_html = ''
    for s in sections:
        is_selected = s.id in selected_set
        collapsed = s.id in COLLAPSED_BY_DEFAULT
        pre_text = _extract_pre_text(s.content_html)

        if is_selected:
            analysis_block = f'<div class="analysis-block">{analysis[s.id]}</div>' if s.id in analysis else ''
            raw_block = f'''
<div class="raw-toggle" onclick="toggleRaw(this)">
  <span>Raw data</span><span class="chevron">{'▸' if analysis_block else '▾'}</span>
</div>
<div class="raw-content" {'style="display:none"' if analysis_block else ''}>
<pre>{pre_text}</pre>
</div>'''
            content_block = analysis_block + raw_block
            excl_banner = ''
        else:
            content_block = f'''<div class="excluded-block">
  <div class="excl-icon">⊘</div>
  <div>
    <div class="excl-title">Section excluded by report author</div>
    <div class="excl-sub">Filtered using pButtons Parser - a free tool that redacts InterSystems IRIS pButtons files locally, without uploading any data to the cloud.</div>
  </div>
</div>'''
            excl_banner = ''

        sensitive_banner = ''
        if s.sensitive and is_selected:
            sensitive_banner = f'<div class="sensitive-banner">&#9888; This section may contain sensitive data: {s.sensitive_reason}</div>'

        panel_hidden = 'style="display:none"' if collapsed and is_selected else ''
        desc = SECTION_DESCRIPTIONS.get(s.title, '')
        desc_html = f'<p class="section-desc">{desc}</p>' if desc else ''
        panels_html += f'''
<div class="section-panel" id="sec-{s.id}" {panel_hidden}>
  <div class="section-header" onclick="toggleSection('{s.id}')">
    <div class="section-title-block"><h2>{s.title}</h2>{desc_html}</div>
    <span class="section-chevron" id="chev-{s.id}">{'▸' if collapsed and is_selected else '▾'}</span>
  </div>
  {sensitive_banner}
  <div class="section-body" id="body-{s.id}">
    {content_block}
  </div>
</div>'''

    # --- assemble full HTML ---
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>pButtons - {instance_name} {run_time}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;display:flex;flex-direction:column;height:100vh;overflow:hidden}}

/* Top bar */
.topbar{{background:#003366;color:#fff;padding:10px 20px;display:flex;align-items:center;gap:16px;flex-shrink:0;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.3)}}
.topbar h1{{font-size:1rem;font-weight:700;white-space:nowrap}}
.topbar .meta{{font-size:0.75rem;opacity:.75;display:flex;gap:12px;flex-wrap:wrap}}
.topbar .meta span::before{{content:"·";margin-right:8px;opacity:.5}}
.topbar .badge{{background:rgba(255,255,255,.15);border-radius:4px;padding:2px 8px;font-size:0.7rem;margin-left:auto;white-space:nowrap}}

/* Layout */
.layout{{display:flex;flex:1;overflow:hidden}}

/* Sidebar */
.sidebar{{width:220px;background:#fff;border-right:1px solid #dde3ee;overflow-y:auto;flex-shrink:0;padding:12px 0}}
.nav-group{{margin-bottom:4px}}
.nav-group-label{{padding:6px 16px;font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#889;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none}}
.nav-group-label:hover{{color:#003366}}
.nav-group-items{{padding:0 0 4px 0}}
.nav-item{{display:flex;align-items:center;gap:6px;padding:5px 16px 5px 24px;font-size:0.82rem;color:#334;text-decoration:none;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .1s}}
.nav-item:hover{{background:#f0f6ff;color:#003366}}
.nav-item.active{{background:#e8f0ff;color:#003366;font-weight:600;border-right:3px solid #003366}}
.nav-item.excluded{{color:#bbb;font-style:italic}}
.excl-badge{{font-size:0.65rem;background:#f3f4f6;color:#aaa;border-radius:3px;padding:1px 4px;margin-left:auto;flex-shrink:0}}
.analysis-dot{{width:6px;height:6px;background:#0055aa;border-radius:50%;flex-shrink:0}}
.chevron{{font-size:0.7rem;transition:transform .2s}}
.chevron.open{{transform:rotate(180deg)}}

/* Main content */
.main{{flex:1;overflow-y:auto;padding:24px}}

/* Section panels */
.section-panel{{background:#fff;border-radius:10px;box-shadow:0 1px 6px rgba(0,0,0,.07);margin-bottom:16px;overflow:hidden}}
.section-header{{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;cursor:pointer;border-bottom:1px solid #f0f2f5;user-select:none}}
.section-header:hover{{background:#fafbff}}
.section-title-block{{display:flex;flex-direction:column;gap:2px}}
.section-header h2{{font-size:1rem;font-weight:600;color:#003366}}
.section-desc{{font-size:0.75rem;color:#778;font-weight:400;margin:0}}
.section-chevron{{font-size:0.85rem;color:#999;transition:transform .2s}}
.section-body{{padding:16px 20px}}

/* Analysis block */
.analysis-block{{margin-bottom:8px}}

/* Raw data toggle */
.raw-toggle{{display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:#0055aa;cursor:pointer;padding:4px 0;margin-bottom:6px;user-select:none}}
.raw-toggle:hover{{text-decoration:underline}}
.raw-content pre{{background:#f8f9fc;border:1px solid #e8edf5;border-radius:6px;padding:12px;font-size:0.75rem;line-height:1.5;overflow-x:auto;white-space:pre;max-height:500px;overflow-y:auto}}

/* Excluded */
.excluded-block{{display:flex;align-items:flex-start;gap:12px;padding:16px;background:#fafafa;border:1px dashed #ddd;border-radius:6px;color:#999}}
.excl-icon{{font-size:1.4rem;line-height:1;color:#ccc}}
.excl-title{{font-weight:500;color:#bbb;font-size:0.85rem}}
.excl-sub{{font-size:0.75rem;color:#ccc;margin-top:3px}}

/* Sensitive banner */
.sensitive-banner{{background:#fffbeb;border:1px solid #f59e0b;border-radius:6px;padding:8px 14px;font-size:0.78rem;color:#92400e;margin-bottom:12px}}

/* Scrollbars */
.sidebar::-webkit-scrollbar,.main::-webkit-scrollbar{{width:5px}}
.sidebar::-webkit-scrollbar-thumb,.main::-webkit-scrollbar-thumb{{background:#ddd;border-radius:3px}}
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
</head>
<body>

<div class="topbar">
  <h1>pButtons Performance Report</h1>
  <div class="meta">
    {f'<span>{instance_name}</span>' if instance_name else ''}
    {f'<span>{machine_name}</span>' if machine_name else ''}
    {f'<span>{run_time}</span>' if run_time else ''}
    {f'<span>{user_name}</span>' if user_name else ''}
  </div>
  <span class="badge">pButtons Parser</span>
</div>

<div class="layout">
  <nav class="sidebar">{nav_html}</nav>
  <div class="main" id="main-content">
    {panels_html}
  </div>
</div>

<script>
// Show only clicked section (scroll into view + highlight nav)
function showSection(id) {{
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const link = document.querySelector(`.nav-item[onclick*="${{id}}"]`);
  if (link) link.classList.add('active');

  const panel = document.getElementById('sec-' + id);
  if (!panel) return;
  panel.style.display = 'block';

  // Expand if collapsed
  const body = document.getElementById('body-' + id);
  const chev = document.getElementById('chev-' + id);
  if (body && body.style.display === 'none') {{
    body.style.display = 'block';
    if (chev) chev.style.transform = 'rotate(0deg)';
  }}

  panel.scrollIntoView({{behavior: 'smooth', block: 'start'}});
}}

// Toggle section collapse
function toggleSection(id) {{
  const body = document.getElementById('body-' + id);
  const chev = document.getElementById('chev-' + id);
  if (!body) return;
  const collapsed = body.style.display === 'none';
  body.style.display = collapsed ? 'block' : 'none';
  if (chev) chev.style.transform = collapsed ? 'rotate(0deg)' : 'rotate(-90deg)';
}}

// Toggle nav group open/closed
function toggleGroup(el) {{
  const items = el.nextElementSibling;
  const chev = el.querySelector('.chevron');
  const hidden = items.style.display === 'none';
  items.style.display = hidden ? 'block' : 'none';
  if (chev) chev.classList.toggle('open', hidden);
}}

// Toggle raw data visibility
function toggleRaw(el) {{
  const raw = el.nextElementSibling;
  const chev = el.querySelector('.chevron');
  const hidden = raw.style.display === 'none';
  raw.style.display = hidden ? 'block' : 'none';
  chev.textContent = hidden ? '▾' : '▸';
}}

// Activate first visible section on load
document.addEventListener('DOMContentLoaded', () => {{
  const first = document.querySelector('.nav-item:not(.excluded)');
  if (first) first.click();
}});
</script>
</body>
</html>'''
