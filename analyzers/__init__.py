"""
Analyzer interface: each module exposes an async `analyze(section_text) -> str`
that returns an HTML fragment injected after the section's <pre> block.
Return empty string if the section can't be parsed or has no useful data.
"""
from .windows_info import analyze as analyze_windows_info
from .tasklist import analyze as analyze_tasklist
from .mgstat import analyze as analyze_mgstat
from .iostat import analyze as analyze_iostat
from .cpu import analyze as analyze_cpu
from .ss import analyze as analyze_ss
from .sar_d import analyze as analyze_sar_d
from .sar_u import analyze as analyze_sar_u
from .vmstat import analyze as analyze_vmstat
from .irisstat_d import analyze as analyze_irisstat_d
from .perfmon import analyze as analyze_perfmon
from .cpf import analyze as analyze_cpf

SECTION_ANALYZERS = {
    "Windowsinfo": analyze_windows_info,
    "tasklist": analyze_tasklist,
    "mgstat": analyze_mgstat,
    "iostat": analyze_iostat,
    "cpu": analyze_cpu,
    "%SS": analyze_ss,
    "sar-d": analyze_sar_d,
    "sar-u": analyze_sar_u,
    "vmstat": analyze_vmstat,
    "irisstat-D": analyze_irisstat_d,
    "perfmon": analyze_perfmon,
    "CPFfile": analyze_cpf,
}
