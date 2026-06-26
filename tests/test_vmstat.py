"""
Standalone vmstat analyzer test.
Usage:  ./venv/Scripts/python test_vmstat.py <sysperf_file.html>
Output: test_vmstat_out.html  (open in browser to see charts)
"""
import re
import sys
import asyncio
from sysperfsight_parser import parse_sections
from analyzers.vmstat import analyze, _parse_vmstat

PLOTLY_CDN = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>'


async def main(path: str):
    raw = open(path, encoding='iso-8859-1', errors='replace').read()
    # Strip any leading </pre> from a previous section
    raw = re.sub(r'^\s*</pre>', '', raw, count=1).lstrip()
    # Ensure unclosed <pre> at end of file is closed so regex extraction works
    if re.search(r'<pre>', raw, re.IGNORECASE) and not re.search(r'</pre>', raw, re.IGNORECASE):
        raw += '\n</pre>'
    _, sections = parse_sections(raw)

    sec = next((s for s in sections if s.id == 'vmstat'), None)
    if sec is None:
        print('ERROR: no vmstat section found in', path)
        print('Sections found:', [s.id for s in sections])
        return

    text = '\n'.join(re.findall(r'<pre>(.*?)</pre>', sec.content_html, re.DOTALL | re.IGNORECASE))
    print(f'vmstat section found — pre text length: {len(text)} chars')

    df = _parse_vmstat(text)
    if df is None:
        print('ERROR: _parse_vmstat returned None — header not matched')
        print('First 300 chars of text:', repr(text[:300]))
        return

    print(f'Parsed {len(df)} rows, columns: {list(df.columns)}')
    print(df.head(3).to_string())

    result = await analyze(text)
    if not result:
        print('ERROR: analyze() returned empty string')
        return

    print(f'analyze() returned {len(result)} chars — writing test_vmstat_out.html')
    out = f'<!DOCTYPE html><html><head><meta charset="UTF-8">{PLOTLY_CDN}</head><body>{result}</body></html>'
    open('test_vmstat_out.html', 'w', encoding='utf-8').write(out)
    print('Done — open test_vmstat_out.html in your browser')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: ./venv/Scripts/python test_vmstat.py <file.html|file.log>')
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
