"""Ollama debug mode integration and log scanning.

When MTGAI_DEBUG=1, checks that Ollama is running with OLLAMA_DEBUG
enabled and provides a log scanner to detect truncation, OOM, and
other issues from Ollama's server.log.

On Windows, Ollama logs to: %LOCALAPPDATA%/Ollama/server.log
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# MTGAI debug flag - set MTGAI_DEBUG=1 to enable verbose diagnostics
MTGAI_DEBUG = os.environ.get("MTGAI_DEBUG", "").strip() in ("1", "true", "yes")

# Ollama log location (Windows)
_OLLAMA_LOG_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log"


# ── Log entry patterns ──────────────────────────────────────────────

# Patterns that indicate problems, with severity and description.
# Checked in order - first match wins per line. Specific patterns before generic ones.
_PROBLEM_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, severity, description)
    # Truncation (the main thing we care about)
    (r"truncating input messages which exceed context length", "CRITICAL", "Input truncated"),
    (r"truncated=(\d+)", "CRITICAL", "Messages dropped from context"),
    # GPU / memory
    (r"out of memory", "CRITICAL", "GPU out of memory"),
    (r"CUDA out of memory", "CRITICAL", "CUDA OOM"),
    (r"CUDA error", "ERROR", "CUDA error"),
    (r"not enough memory", "ERROR", "Insufficient memory"),
    # Model loading / generation
    (r"failed to load model", "ERROR", "Model load failure"),
    (r"failed to generate", "ERROR", "Generation failure"),
    (r"context length exceeded", "ERROR", "Context length exceeded"),
    # Generic warn/error from Ollama's structured logs
    (r"level=ERROR", "ERROR", "Ollama error"),
    (r"level=WARN", "WARNING", "Ollama warning"),
    # GIN HTTP errors (4xx/5xx)
    (r"\| [45]\d{2} \|", "WARNING", "HTTP error response"),
]

# Informational patterns we extract but don't flag as problems
_INFO_PATTERNS: dict[str, str] = {
    "default_num_ctx": r"default_num_ctx=(\d+)",
    "ollama_debug": r"OLLAMA_DEBUG:(\w+)",
    "total_vram": r'total_vram="([^"]+)"',
    "gpu_name": r'description="([^"]+)"',
    "gpu_available": r'available="([^"]+)"',
    "ollama_version": r"Listening on .+ \(version (.+?)\)",
    "context_length_env": r"OLLAMA_CONTEXT_LENGTH:(\d+)",
    "kv_cache_type": r"OLLAMA_KV_CACHE_TYPE:(\w*)",
    "flash_attention": r"OLLAMA_FLASH_ATTENTION:(\w+)",
}


@dataclass
class LogProblem:
    """A problem found in Ollama's server log."""

    severity: str  # CRITICAL, ERROR, WARNING
    description: str
    line: str
    timestamp: str = ""


@dataclass
class ScanResult:
    """Result of scanning Ollama's server log."""

    log_path: str
    log_exists: bool
    line_count: int = 0
    debug_enabled: bool = False
    server_info: dict[str, str] = field(default_factory=dict)
    problems: list[LogProblem] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(p.severity == "CRITICAL" for p in self.problems)

    @property
    def has_errors(self) -> bool:
        return any(p.severity in ("CRITICAL", "ERROR") for p in self.problems)

    def summary(self) -> str:
        """Human-readable summary of scan results."""
        lines = [f"Ollama log: {self.log_path}"]
        if not self.log_exists:
            lines.append("  Log file not found")
            return "\n".join(lines)

        lines.append(f"  Lines: {self.line_count}")
        lines.append(f"  Debug mode: {'ON' if self.debug_enabled else 'OFF'}")

        if self.server_info:
            for key, val in self.server_info.items():
                lines.append(f"  {key}: {val}")

        if self.problems:
            lines.append(f"\n  Problems found: {len(self.problems)}")
            for p in self.problems:
                ts = f" [{p.timestamp}]" if p.timestamp else ""
                lines.append(f"    [{p.severity}]{ts} {p.description}")
                if len(p.line) > 200:
                    lines.append(f"      {p.line[:200]}...")
                else:
                    lines.append(f"      {p.line}")
        else:
            lines.append("\n  No problems found")

        return "\n".join(lines)


def _parse_timestamp(line: str) -> str:
    """Extract timestamp from an Ollama log line."""
    match = re.match(r"time=(\S+)", line)
    if match:
        return match.group(1)
    # GIN format: [GIN] 2026/04/12 - 21:01:35
    match = re.match(r"\[GIN\] (\S+ - \S+)", line)
    if match:
        return match.group(1)
    return ""


def scan_log(
    log_path: Path | None = None,
    since_lines: int | None = None,
) -> ScanResult:
    """Scan Ollama's server.log for problems.

    Args:
        log_path: Override log path (default: auto-detect).
        since_lines: Only scan the last N lines (default: all).

    Returns:
        ScanResult with server info and any problems found.
    """
    path = log_path or _OLLAMA_LOG_PATH
    result = ScanResult(log_path=str(path), log_exists=path.exists())

    if not path.exists():
        logger.warning("Ollama log not found at %s", path)
        return result

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        logger.error("Failed to read Ollama log: %s", e)
        return result

    result.line_count = len(lines)

    if since_lines and since_lines < len(lines):
        scan_lines = lines[-since_lines:]
    else:
        scan_lines = lines

    # Extract server info from all lines (config is usually near the top)
    for line in lines:
        for key, pattern in _INFO_PATTERNS.items():
            if key not in result.server_info:
                match = re.search(pattern, line)
                if match:
                    result.server_info[key] = match.group(1)

    # Check debug mode
    debug_val = result.server_info.get("ollama_debug", "")
    result.debug_enabled = debug_val.upper() in ("1", "TRUE", "DEBUG")

    # Scan for problems
    seen_lines: set[str] = set()
    for line in scan_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        for pattern, severity, description in _PROBLEM_PATTERNS:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                # Deduplicate identical lines
                if line_stripped not in seen_lines:
                    seen_lines.add(line_stripped)
                    result.problems.append(
                        LogProblem(
                            severity=severity,
                            description=description,
                            line=line_stripped,
                            timestamp=_parse_timestamp(line_stripped),
                        )
                    )
                break  # Only match first pattern per line

    return result


def check_ollama_debug_mode() -> None:
    """Check that Ollama has debug mode enabled when MTGAI_DEBUG is set.

    Logs a warning with instructions if debug mode is not enabled.
    Called at startup when MTGAI_DEBUG=1.
    """
    if not MTGAI_DEBUG:
        return

    result = scan_log()
    if not result.log_exists:
        logger.warning(
            "MTGAI_DEBUG is set but Ollama log not found at %s. "
            "Cannot verify Ollama debug mode.",
            _OLLAMA_LOG_PATH,
        )
        return

    if not result.debug_enabled:
        logger.warning(
            "MTGAI_DEBUG=1 but Ollama is NOT running in debug mode. "
            "Truncation warnings will not appear in Ollama's log. "
            "To enable: set OLLAMA_DEBUG=1 as a system environment variable "
            "and restart the Ollama service. On Windows:\n"
            "  1. Open System Properties > Environment Variables\n"
            "  2. Add OLLAMA_DEBUG=1 (system or user variable)\n"
            "  3. Restart Ollama (right-click tray icon > Quit, then relaunch)"
        )
    else:
        logger.info("Ollama debug mode confirmed: %s", result.server_info.get("ollama_debug"))

    # Also log useful server info
    ctx = result.server_info.get("default_num_ctx", "unknown")
    gpu = result.server_info.get("gpu_name", "unknown")
    vram = result.server_info.get("gpu_available", "unknown")
    logger.info("Ollama: default_num_ctx=%s, GPU=%s, available VRAM=%s", ctx, gpu, vram)


def scan_after_call(since_lines: int = 50) -> list[LogProblem]:
    """Quick scan of recent log lines after an Ollama API call.

    Returns any problems found in the last N lines. Useful for
    catching truncation warnings that our token-based detection
    might miss.
    """
    if not MTGAI_DEBUG:
        return []

    result = scan_log(since_lines=since_lines)
    if result.problems:
        for p in result.problems:
            log_fn = logger.error if p.severity in ("CRITICAL", "ERROR") else logger.warning
            log_fn("Ollama log [%s]: %s - %s", p.severity, p.description, p.line[:150])

    return result.problems


# ── CLI entry point ─────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Parse args
    since = None
    for arg in sys.argv[1:]:
        if arg.startswith("--since="):
            since = int(arg.split("=", 1)[1])
        elif arg == "--help":
            print("Usage: python -m mtgai.generation.ollama_debug [--since=N]")
            print("  Scan Ollama server.log for truncation, OOM, and other issues.")
            print("  --since=N  Only scan last N lines (default: all)")
            sys.exit(0)

    result = scan_log(since_lines=since)
    print(result.summary())

    if result.has_critical:
        sys.exit(2)
    elif result.has_errors:
        sys.exit(1)
    sys.exit(0)
