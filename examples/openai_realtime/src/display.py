"""
Terminal display, logging, and user-prompt helpers for the agent.

Kept separate from agent.py so the core integration code (OpenAI Realtime ↔
Thymia Sentinel) stays small and easy to read. None of this file is required
by the integration — it's purely about rendering output and prompting input.

Public surface used by agent.py:
- configure_logging()
- prompt_user_profile()
- log_user_profile(), log_startup(), log_audio_device()
- log_user_transcript(), log_agent_transcript()
- log_progress(), log_policy()
- is_valid_user_transcript()
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import textwrap

from loguru import logger
from thymia_sentinel import PolicyResult


# --- Logger setup ------------------------------------------------------------

def configure_logging() -> None:
    """Replace loguru's default handler with our column-aligned format and
    silence the Sentinel SDK's verbose internal logging (we render our own).
    """
    level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<dim>{time:HH:mm:ss}</dim> <level>{level: <7}</level> {message}",
        colorize=True,
    )
    logger.disable("thymia_sentinel")


# --- Column-aligned line primitives ------------------------------------------
#
# All conversation lines share a single column-aligned prefix:
#
#   TAG    │ text
#          │   ▸ continuation / subtext
#
# Loguru's format renders "HH:MM:SS LEVEL___" as a 17-char prefix before the
# message body. _line then adds "tag(6) │ "(3) = 9 more, so text starts at
# column 26. _sub uses "indent(6) │   ▸ "(7) = 13 more, text at column 30.

_TAG_WIDTH = 6
_BAR_WIDTH = 12
_INDENT = " " * _TAG_WIDTH
_LINE_TEXT_COL = 17 + _TAG_WIDTH + 3
_SUB_TEXT_COL = 17 + _TAG_WIDTH + 7


def _wrap(text: str, indent_col: int) -> str:
    """Word-wrap `text` so continuation lines indent under the text column.

    Bails out if `text` contains inline loguru color tags — textwrap can't
    see those and would split them awkwardly. Caps the effective width at
    110 chars by default for readability, even when the terminal reports a
    much wider buffer (e.g. VSCode's integrated terminal). Override with
    WRAP_WIDTH=N (set 0 to disable wrap entirely).
    """
    if "<" in text or ">" in text:
        return text
    override = os.getenv("WRAP_WIDTH")
    if override is not None:
        try:
            override_width = int(override)
            if override_width <= 0:
                return text
            effective_width = override_width
        except ValueError:
            effective_width = 110
    else:
        term_width = shutil.get_terminal_size((120, 24)).columns
        effective_width = min(term_width, 110)
    available = max(effective_width - indent_col - 2, 40)
    if len(text) <= available:
        return text
    return textwrap.fill(
        text,
        width=indent_col + available,
        initial_indent="",
        subsequent_indent=" " * indent_col,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _line(tag: str, color: str, text: str, full: bool = False) -> None:
    """Emit one column-aligned log line.

    By default only the tag prefix is coloured; pass `full=True` to colour
    the entire row (for policy result lines that should stand out).
    """
    text = _wrap(text, _LINE_TEXT_COL)
    if full:
        logger.opt(colors=True).info(
            f"<{color}>{tag:<{_TAG_WIDTH}} │ {text}</{color}>"
        )
    else:
        logger.opt(colors=True).info(
            f"<{color}>{tag:<{_TAG_WIDTH}}</{color}> │ {text}"
        )


def _sub(text: str, color: str = "dim") -> None:
    text = _wrap(text, _SUB_TEXT_COL)
    logger.opt(colors=True).info(f"{_INDENT} <{color}>│   ▸ {text}</{color}>")


def _bar(speech: float, trigger: float, width: int = _BAR_WIDTH) -> str:
    pct = min(speech / trigger, 1.0) if trigger else 0.0
    filled = int(round(pct * width))
    return "█" * filled + "░" * (width - filled)


def _level_color(level: int) -> str:
    return {0: "green", 1: "yellow", 2: "yellow", 3: "red"}.get(level or 0, "white")


# --- Transcript validation ---------------------------------------------------

_MIN_TRANSCRIPT_CHARS = 12  # filter out fragments like "Um", "Bye.", language hiccups


def _is_mostly_latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isascii()) / len(letters) >= 0.6


def is_valid_user_transcript(text: str) -> bool:
    """True if the transcript is long enough and mostly Latin script.

    Drops fragments (partial transcriptions) and Whisper hallucinations like
    Japanese "ha ha ha" sounds when the configured language is en-GB.
    """
    return len(text) >= _MIN_TRANSCRIPT_CHARS and _is_mostly_latin(text)


# --- Startup banners ---------------------------------------------------------

def log_startup(
    model: str,
    sample_rate: int,
    voice: str,
    allow_interruption: bool,
    policies: list,
    biomarkers: list,
) -> None:
    interrupt_mode = "full-duplex" if allow_interruption else "half-duplex (no interruption)"
    _line(
        "ok", "green",
        f"<bold>{model}</bold> @ {sample_rate}Hz · voice={voice}"
        f" · {interrupt_mode}"
        f" · policies={policies} · biomarkers={biomarkers}",
    )


def log_audio_device(role: str, name: str) -> None:
    """role is "mic" or "out"."""
    _line("audio", "blue", f"{role} ▸ {name}")


def log_user_profile(dob: str | None, birth_sex: str | None) -> None:
    parts = []
    if dob:
        parts.append(f"dob={dob}")
    if birth_sex:
        parts.append(f"sex={birth_sex}")
    _line(
        "you", "blue",
        f"<dim>{' · '.join(parts) if parts else 'imputed from voice'}</dim>",
    )


# --- Conversation transcripts ------------------------------------------------

def log_user_transcript(text: str) -> None:
    _line("user", "cyan", text)


def log_agent_transcript(text: str) -> None:
    _line("agent", "magenta", text)


# --- Biomarker progress (debounced) ------------------------------------------

_PROGRESS_ADVANCE_THRESHOLD = 1.5  # seconds of new speech before re-rendering bio
_PROGRESS_DEBOUNCE_SECS = 1.0  # collapse rapid bio updates into one line per window

_last_progress_speech: dict[str, float] = {}
_pending_progress: dict = {"parts": [], "cycled": []}
_pending_progress_task: asyncio.Task | None = None


async def _flush_progress() -> None:
    await asyncio.sleep(_PROGRESS_DEBOUNCE_SECS)
    parts = _pending_progress["parts"]
    cycled = _pending_progress["cycled"]
    if not parts and not cycled:
        return

    annotated_parts = []
    for part in parts:
        name = part.split()[0]
        marker = "▶ " if name in cycled else "  "
        annotated_parts.append(f"{marker}{part}")
    if annotated_parts:
        _line("bio", "blue", f"<dim>{'  '.join(annotated_parts)}</dim>")
    elif cycled:
        _line("bio", "blue", f"<dim>▶ analyzing {', '.join(cycled)}…</dim>")

    _pending_progress["parts"] = []
    _pending_progress["cycled"] = []


def log_progress(biomarkers: dict, agent_speaking: bool = False) -> None:
    """Feed the debounce buffer with the latest biomarker progress.

    All updates within a ~1s window are collapsed into one consolidated bio
    line: latest bar values + any biomarkers that cycled in the window get
    a ▶ marker. Skipped while the agent is mid-utterance.
    """
    global _pending_progress_task

    if agent_speaking:
        return

    parts = []
    advanced = False
    for name, status in biomarkers.items():
        speech = float(status.get("speech_seconds", 0.0))
        trigger = float(status.get("trigger_seconds", 1.0))
        last = _last_progress_speech.get(name, -1.0)

        # Detect a cycle reset: buffer was nearly full, has now dropped.
        if last >= trigger * 0.95 and speech < trigger * 0.3:
            if name not in _pending_progress["cycled"]:
                _pending_progress["cycled"].append(name)
        if speech - last >= _PROGRESS_ADVANCE_THRESHOLD or status.get("processing"):
            advanced = True

        _last_progress_speech[name] = speech
        display_speech = min(speech, trigger)
        parts.append(
            f"{name:<7} {_bar(speech, trigger)} {display_speech:4.1f}/{trigger:.0f}s"
        )

    # Skip the all-zero bar that arrives right after a cycle reset.
    if advanced and parts and not all(s == 0.0 for s in _last_progress_speech.values()):
        _pending_progress["parts"] = parts

    if _pending_progress_task is None or _pending_progress_task.done():
        _pending_progress_task = asyncio.create_task(_flush_progress())


# --- Policy result rendering -------------------------------------------------

_ELEVATED_RE = re.compile(
    r"\b(elevated|high|increased|significant|moderate|severe|strong)\b",
    re.IGNORECASE,
)
_last_policy_signature: tuple | None = None


def _has_elevated_signals(concerns: tuple[str, ...]) -> bool:
    return any(_ELEVATED_RE.search(c) for c in concerns)


def _top_biomarker_scores(summary: dict, n: int = 2) -> list[tuple[str, float]]:
    if not isinstance(summary, dict):
        return []
    numeric = [
        (k, float(v)) for k, v in summary.items()
        if isinstance(v, (int, float))
    ]
    numeric.sort(key=lambda kv: kv[1], reverse=True)
    return numeric[:n]


def log_policy(result: PolicyResult) -> None:
    """Render a Thymia Sentinel policy result as a single consolidated line.

    Dedupes consecutive identical results. Applies colour priority:
    red (suicidal flag) > yellow (alert or level-0 mismatch) > dim (all clear).
    """
    global _last_policy_signature
    inner = result.get("result", {})
    rtype = inner.get("type", "unknown")

    if rtype == "safety_analysis":
        # Read level/alert/confidence from the top level of `inner`. Older
        # payloads nested them under `classification` — fall back to that.
        classification = inner.get("classification") or {}
        level = inner.get("level", classification.get("level", 0)) or 0
        alert = inner.get("alert", classification.get("alert", "none")) or "none"
        confidence = inner.get("confidence", classification.get("confidence"))
        concerns = tuple(inner.get("concerns") or [])
        for_agent = (inner.get("recommended_actions") or {}).get("for_agent", "")

        signature = (level, alert, concerns, for_agent)
        if signature == _last_policy_signature:
            return
        _last_policy_signature = signature

        color = _level_color(level)
        if isinstance(confidence, (int, float)):
            conf_str = f" · {confidence:.0%}"
        elif isinstance(confidence, str) and confidence:
            conf_str = f" · {confidence}"
        else:
            conf_str = ""

        suicidal = bool((inner.get("flags") or {}).get("suicidal_content"))
        is_level_zero_mismatch = level == 0 and _has_elevated_signals(concerns)

        prefix_parts = []
        if suicidal:
            prefix_parts.append("🚨")
        if is_level_zero_mismatch:
            prefix_parts.append("⚠ mismatch")
        prefix = " · ".join(prefix_parts) + " · " if prefix_parts else ""

        body = f"level {level} {alert}{conf_str}"
        if concerns:
            body += f" — {concerns[0]}"

        top = _top_biomarker_scores(inner.get("biomarker_summary") or {}, n=2)
        scores_suffix = ""
        if top:
            rendered = ", ".join(f"{name} {value:.2f}" for name, value in top)
            scores_suffix = f" · top: {rendered}"

        head = f"{prefix}{body}{scores_suffix}"

        if suicidal:
            line_color = "red"
        elif is_level_zero_mismatch:
            line_color = "yellow"
        elif level == 0:
            line_color = "dim"
        else:
            line_color = color

        _line("result", line_color, head, full=True)
        if level >= 1 and for_agent:
            _sub(for_agent, color=line_color)

    elif rtype == "extracted_fields":
        fields = inner.get("fields", {})
        extracted = {k: v.get("value") for k, v in fields.items() if v.get("value") is not None}
        if extracted:
            _line("result", "blue", f"extracted · {extracted}", full=True)
        else:
            _line("result", "dim", f"extracted · (no fields yet, {len(fields)} candidates)", full=True)

    else:
        _line("result", "dim", f"type={rtype} · {inner}", full=True)


# --- Terminal prompts --------------------------------------------------------

_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEFAULT_DOB = "1997-11-18"
_DEFAULT_BIRTH_SEX = "MALE"


def prompt_user_profile() -> tuple[str | None, str | None]:
    """Ask for date of birth and birth sex on the terminal before connecting.

    Defaults are pre-filled (press Enter to accept). Type a new value to
    override, or "skip" to omit the field (Sentinel will impute from voice).
    Values can also be supplied via THYMIA_DOB / THYMIA_BIRTH_SEX env vars
    to bypass the prompts entirely.
    """
    dob = os.getenv("THYMIA_DOB", "").strip()
    if not dob:
        raw = input(f"Date of birth (YYYY-MM-DD) [{_DEFAULT_DOB}, 'skip' to omit]: ").strip()
        if raw.lower() == "skip":
            dob = ""
        elif not raw:
            dob = _DEFAULT_DOB
        elif _DOB_RE.match(raw):
            dob = raw
        else:
            print(f"  ⚠ '{raw}' isn't YYYY-MM-DD — using default {_DEFAULT_DOB}.")
            dob = _DEFAULT_DOB

    birth_sex = os.getenv("THYMIA_BIRTH_SEX", "").strip().upper()
    if birth_sex not in {"MALE", "FEMALE"}:
        raw = input(f"Birth sex (MALE/FEMALE) [{_DEFAULT_BIRTH_SEX}, 'skip' to omit]: ").strip().upper()
        if raw == "SKIP":
            birth_sex = ""
        elif not raw:
            birth_sex = _DEFAULT_BIRTH_SEX
        elif raw in {"M", "MALE"}:
            birth_sex = "MALE"
        elif raw in {"F", "FEMALE"}:
            birth_sex = "FEMALE"
        else:
            print(f"  ⚠ '{raw}' must be MALE or FEMALE — using default {_DEFAULT_BIRTH_SEX}.")
            birth_sex = _DEFAULT_BIRTH_SEX

    return (dob or None), (birth_sex or None)
