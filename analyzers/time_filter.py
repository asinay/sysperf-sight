import re
from datetime import time as Time, datetime


def _parse_hhmm(s: str) -> Time | None:
    m = re.match(r'^(\d{1,2}):(\d{2})$', s.strip())
    if not m:
        return None
    try:
        return Time(int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def _in_range(t: Time, lo: Time | None, hi: Time | None) -> bool:
    if lo is None and hi is None:
        return True
    if lo is None:
        return t <= hi
    if hi is None:
        return t >= lo
    if lo <= hi:
        return lo <= t <= hi
    # crosses midnight (e.g. 22:00 – 04:00)
    return t >= lo or t <= hi


def filter_mgstat(text: str, time_from: str, time_to: str) -> str:
    lo = _parse_hhmm(time_from) if time_from else None
    hi = _parse_hhmm(time_to) if time_to else None
    if lo is None and hi is None:
        return text

    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\d{2}/\d{2}/\d{4}', stripped):
            m = re.match(r'^\d{2}/\d{2}/\d{4}\s*,\s*(\d{1,2}):(\d{2}):\d{2}', stripped)
            if m:
                try:
                    row_time = Time(int(m.group(1)), int(m.group(2)))
                    if _in_range(row_time, lo, hi):
                        result.append(line)
                except ValueError:
                    result.append(line)
            else:
                result.append(line)
        else:
            result.append(line)
    return ''.join(result)


_IOSTAT_TS_RE = re.compile(
    r'^\s*(\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*(?:[AP]M))\s*$',
    re.IGNORECASE,
)


def filter_iostat(text: str, time_from: str, time_to: str) -> str:
    lo = _parse_hhmm(time_from) if time_from else None
    hi = _parse_hhmm(time_to) if time_to else None
    if lo is None and hi is None:
        return text

    lines = text.splitlines(keepends=True)
    ts_indices = [(i, m.group(1).strip()) for i, line in enumerate(lines) if (m := _IOSTAT_TS_RE.match(line))]

    if not ts_indices:
        return text

    result = list(lines[:ts_indices[0][0]])
    for idx, (line_idx, ts_str) in enumerate(ts_indices):
        end_idx = ts_indices[idx + 1][0] if idx + 1 < len(ts_indices) else len(lines)
        ts_norm = re.sub(r'\s+', ' ', ts_str.strip())
        try:
            try:
                dt = datetime.strptime(ts_norm, '%m/%d/%Y %I:%M:%S %p')
            except ValueError:
                dt = datetime.strptime(ts_norm, '%m/%d/%Y %H:%M:%S')
            block_time = Time(dt.hour, dt.minute)
        except ValueError:
            result.extend(lines[line_idx:end_idx])
            continue
        if _in_range(block_time, lo, hi):
            result.extend(lines[line_idx:end_idx])
    return ''.join(result)


# Captures sar timestamps correctly, including optional AM/PM.
# Also supports optional date prefixes.
_SAR_DATA_RE = re.compile(
    r'''
    ^\s*
    (?:
        (?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})
        \s+
    )?
    (?P<ts>\d{1,2}:\d{2}:\d{2}(?:\s+[AP]M)?)
    \s+
    (?P<first>\S+)
    ''',
    re.IGNORECASE | re.VERBOSE,
)


def _parse_sar_ts(ts: str) -> Time | None:
    ts = re.sub(r'\s+', ' ', ts.strip())

    # If SAR says AM/PM, force 12-hour parsing.
    # This prevents "03:45:09 PM" from being treated as "03:45".
    if re.search(r'\b[AP]M\b', ts, re.IGNORECASE):
        try:
            dt = datetime.strptime(ts.upper(), '%I:%M:%S %p')
            return Time(dt.hour, dt.minute)
        except ValueError:
            return None

    # Otherwise parse normal 24-hour SAR timestamps.
    try:
        dt = datetime.strptime(ts, '%H:%M:%S')
        return Time(dt.hour, dt.minute)
    except ValueError:
        return None


def filter_sar(text: str, time_from: str, time_to: str) -> str:
    lo = _parse_hhmm(time_from) if time_from else None
    hi = _parse_hhmm(time_to) if time_to else None
    if lo is None and hi is None:
        return text

    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        m = _SAR_DATA_RE.match(line)
        if m:
            row_time = _parse_sar_ts(m.group('ts'))
            if row_time is None or _in_range(row_time, lo, hi):
                result.append(line)
        else:
            result.append(line)
    return ''.join(result)


_VMSTAT_DATA_RE = re.compile(
    r'^\s*\d{2}/\d{2}/\d{2,4}\s+(\d{2}):(\d{2}):\d{2}\s+\d',
)


def filter_vmstat(text: str, time_from: str, time_to: str) -> str:
    lo = _parse_hhmm(time_from) if time_from else None
    hi = _parse_hhmm(time_to) if time_to else None
    if lo is None and hi is None:
        return text

    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        m = _VMSTAT_DATA_RE.match(line)
        if m:
            try:
                row_time = Time(int(m.group(1)), int(m.group(2)))
                if _in_range(row_time, lo, hi):
                    result.append(line)
            except ValueError:
                result.append(line)
        else:
            result.append(line)
    return ''.join(result)


# Keyed by section title (more stable than IDs for sar/vmstat whose div ids vary)
TITLE_TIME_FILTERS: dict[str, callable] = {
    'mgstat': filter_mgstat,
    'iostat': filter_iostat,
    'sar -u': filter_sar,
    'sar -d': filter_sar,
    'vmstat': filter_vmstat,
}
