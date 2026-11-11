#!/usr/bin/env python3
"""Render RunSpecimen onboarding GIFs from a captured CLI session.

Rebuild (uses the committed transcript; no TTY required):

    python3 -m pip install pillow
    python3 web/onboarding/build_gifs.py

Recapture a live session (needs ``runspecimen`` on PATH and a TTY), then
rebuild:

    python3 web/onboarding/build_gifs.py --capture
"""

from __future__ import annotations

import argparse
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TRANSCRIPTS = ROOT / "transcripts"
SESSION_PATH = TRANSCRIPTS / "session.json"

WIDTH = 960
HEIGHT = 600
COLS = 88
ROWS = 20

# Product-demo palette (light, high contrast).
PAPER = (243, 238, 228)
CARD = (255, 252, 246)
TITLEBAR = (231, 223, 208)
INK = (28, 27, 22)
INK_SOFT = (90, 85, 74)
RULE = (216, 206, 187)
FOREST = (30, 92, 72)
AMBER = (184, 106, 28)
DOT_RED = (176, 92, 80)
DOT_AMBER = (196, 148, 64)
DOT_GREEN = (90, 140, 110)

FONT_MONO = Path("/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf")
FONT_MONO_BOLD = Path("/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf")
FONT_UI = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
FONT_UI_BOLD = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
FONT_DISPLAY = Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf")

PLACEHOLDER = "$WORKSPACE"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def dumps(obj: object) -> str:
    """Match the CLI: indent=2, sort_keys=True. Show the demo path as '.'."""
    return json.dumps(obj, indent=2, sort_keys=True).replace(PLACEHOLDER, ".")


def wrap_line(line: str, width: int = COLS) -> list[str]:
    if len(line) <= width:
        return [line]
    indent = len(line) - len(line.lstrip(" "))
    hang = " " * min(indent + 2, 20)
    out: list[str] = []
    rest = line
    while len(rest) > width:
        window = rest[:width]
        brk = window.rfind(" ")
        if brk < max(8, indent):
            chunk, rest = rest[:width], hang + rest[width:]
        else:
            chunk, rest = rest[:brk], hang + rest[brk + 1 :]
        out.append(chunk)
        if len(out) > 12:
            out.append(hang + rest[: max(0, width - len(hang))])
            return out
    if rest:
        out.append(rest)
    return out


def wrap_text(text: str, width: int = COLS) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        lines.extend(wrap_line(raw, width) or [""])
    return lines


class Terminal:
    """Light-theme terminal viewport with a marketing caption."""

    def __init__(self, title: str, kicker: str, caption: str) -> None:
        self.title = title
        self.kicker = kicker
        self.caption = caption
        self.lines: list[tuple[str, str]] = []
        self.cursor_visible = False
        self.offset: int | None = None  # None = pin to the bottom of the buffer
        self.mono = _font(FONT_MONO, 16)
        self.mono_bold = _font(FONT_MONO_BOLD, 16)
        self.ui = _font(FONT_UI, 15)
        self.ui_bold = _font(FONT_UI_BOLD, 15)
        self.display = _font(FONT_DISPLAY, 26)

    def clear(self) -> None:
        self.lines = []

    def add(self, text: str, kind: str = "text") -> None:
        for line in wrap_text(text):
            self.lines.append((line, kind))

    def add_prompt_command(self, command: str) -> None:
        pieces = command.split("\n")
        for i, piece in enumerate(pieces):
            prefix = "$ " if i == 0 else "  "
            self.add(prefix + piece, "cmd")

    def set_last(self, text: str, kind: str = "text") -> None:
        wrapped = wrap_text(text)
        if not wrapped:
            wrapped = [""]
        # Replace the tail so wrapping stays consistent.
        if self.lines:
            self.lines.pop()
        for line in wrapped:
            self.lines.append((line, kind))

    def render(self) -> Image.Image:
        img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        draw = ImageDraw.Draw(img)

        draw.text((36, 18), self.kicker.upper(), font=self.ui_bold, fill=FOREST)
        draw.text((36, 38), self.title, font=self.display, fill=INK)
        draw.text((36, 74), self.caption, font=self.ui, fill=INK_SOFT)

        win = (28, 108, WIDTH - 28, HEIGHT - 24)
        draw.rounded_rectangle(win, radius=14, fill=CARD, outline=RULE, width=2)
        draw.rounded_rectangle((win[0], win[1], win[2], win[1] + 36), radius=14, fill=TITLEBAR, outline=RULE)
        draw.rectangle((win[0] + 2, win[1] + 18, win[2] - 2, win[1] + 36), fill=TITLEBAR)
        for i, color in enumerate((DOT_RED, DOT_AMBER, DOT_GREEN)):
            cx = win[0] + 22 + i * 16
            cy = win[1] + 18
            draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=color)
        draw.text((win[0] + 78, win[1] + 10), "runspecimen  ·  demo-campaign / run-001", font=self.ui, fill=INK_SOFT)

        x0 = win[0] + 22
        y0 = win[1] + 52
        line_h = 20
        if len(self.lines) <= ROWS:
            view = self.lines
        elif self.offset is None:
            view = self.lines[-ROWS:]
        else:
            start = max(0, min(self.offset, len(self.lines) - ROWS))
            view = self.lines[start : start + ROWS]
        for row, (text, kind) in enumerate(view):
            y = y0 + row * line_h
            fill = INK
            font = self.mono
            if kind == "cmd":
                fill = FOREST
                font = self.mono_bold
            elif kind == "prompt":
                fill = INK
            elif kind == "typed":
                fill = AMBER
                font = self.mono_bold
            elif kind == "ok":
                fill = FOREST
                font = self.mono_bold
            elif kind == "muted":
                fill = INK_SOFT
            draw.text((x0, y), text, font=font, fill=fill)

        if self.cursor_visible:
            last = view[-1][0] if view else ""
            bbox = draw.textbbox((x0, y0 + (len(view) - 1) * line_h), last, font=self.mono)
            cx, cy = bbox[2] + 1, bbox[1] + 2
            draw.rectangle((cx, cy, cx + 9, cy + 16), fill=AMBER)

        return img


def frames_type_command(term: Terminal, command: str, *, start_pause: int = 160) -> list[tuple[Image.Image, int]]:
    """Type a command in short chunks. The CLI itself does not type; this is pedagogy."""
    frames: list[tuple[Image.Image, int]] = []
    pieces = command.split("\n")
    term.add("$ ", "cmd")
    term.cursor_visible = True
    frames.append((term.render(), start_pause))
    step = 4
    for i, piece in enumerate(pieces):
        prefix = "$ " if i == 0 else "  "
        if i > 0:
            term.add(prefix, "cmd")
        built = ""
        for idx in range(0, len(piece), step):
            built = piece[: idx + step]
            term.set_last(prefix + built, "cmd")
            frames.append((term.render(), 40))
        if i < len(pieces) - 1:
            term.set_last(prefix + built + " \\", "cmd")
            frames.append((term.render(), 100))
    term.cursor_visible = False
    frames.append((term.render(), 180))
    return frames


def frames_type_approve(term: Terminal, prompt_line: str) -> list[tuple[Image.Image, int]]:
    frames: list[tuple[Image.Image, int]] = []
    term.add(prompt_line, "prompt")
    term.cursor_visible = True
    frames.append((term.render(), 400))
    typed = ""
    for ch in "APPROVE":
        typed += ch
        term.set_last(prompt_line + typed, "typed")
        frames.append((term.render(), 140))
    term.cursor_visible = False
    frames.append((term.render(), 280))
    return frames


def frames_dump_lines(
    term: Terminal,
    text: str,
    *,
    hold: int = 1800,
    kind_for: callable | None = None,
    bookmarks: tuple[str, ...] = (),
    pin_bottom: bool = True,
) -> list[tuple[Image.Image, int]]:
    """Print a block the way the CLI does — all at once — then hold.

    Long JSON is scrolled through a few real viewport positions so a visitor
    still sees binding fields such as confirm_channel and ok.
    """
    frames: list[tuple[Image.Image, int]] = []
    start_at = len(term.lines)
    for line in wrap_text(text):
        kind = kind_for(line) if kind_for is not None else json_kind(line)
        term.add(line, kind)
    term.cursor_visible = False
    total = len(term.lines)
    added = total - start_at
    if added <= ROWS and total <= ROWS:
        frames.append((term.render(), hold))
        return frames

    positions: list[int] = []
    for mark in bookmarks:
        for idx in range(start_at, total):
            if mark in term.lines[idx][0]:
                positions.append(max(0, idx - 3))
                break
    if pin_bottom:
        positions.append(max(0, total - ROWS))
    if not positions:
        positions.append(max(0, total - ROWS))
    seen: set[int] = set()
    ordered: list[int] = []
    for pos in positions:
        pos = max(0, min(pos, max(0, total - ROWS)))
        if pos not in seen:
            seen.add(pos)
            ordered.append(pos)
    for i, pos in enumerate(ordered):
        term.offset = pos
        duration = hold if i == len(ordered) - 1 else 700
        frames.append((term.render(), duration))
    term.offset = None
    return frames


def json_kind(line: str) -> str:
    if any(
        token in line
        for token in (
            '"ok": true',
            '"run_result": "completed"',
            '"event_chain": "ok"',
            '"confirm_channel": "local_tty_approve"',
            '"exit_code": 0',
        )
    ):
        return "ok"
    if "APPROVE" in line:
        return "typed"
    return "text"


def save_gif(frames: Iterable[tuple[Image.Image, int]], path: Path, *, colors: int = 16) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_list = list(frames)
    if not frame_list:
        raise SystemExit(f"no frames for {path}")
    quantized: list[Image.Image] = []
    durations: list[int] = []
    base = frame_list[0][0].convert("P", palette=Image.Palette.ADAPTIVE, colors=colors, dither=Image.Dither.NONE)
    for im, ms in frame_list:
        quantized.append(im.convert("RGB").quantize(palette=base, dither=Image.Dither.NONE))
        durations.append(max(20, int(ms)))
    quantized[0].save(
        path,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def rewrite_workspace(obj: object, workspace: str) -> object:
    if isinstance(obj, str):
        return obj.replace(workspace, PLACEHOLDER)
    if isinstance(obj, list):
        return [rewrite_workspace(item, workspace) for item in obj]
    if isinstance(obj, dict):
        return {k: rewrite_workspace(v, workspace) for k, v in obj.items()}
    return obj


def capture_session(runspecimen: str) -> dict:
    parent = Path(tempfile.mkdtemp(prefix="rs-onboarding-"))
    workspace = parent / "demo"
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"

    def run(args: list[str]) -> dict:
        proc = subprocess.run(args, env=env, capture_output=True, text=True, check=True)
        return json.loads(proc.stdout)

    version = subprocess.run(
        [runspecimen, "--version"], env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    init = run([runspecimen, "init-demo", "--workspace", str(workspace)])
    doctor = run([runspecimen, "doctor", "--workspace", str(workspace)])
    validate = run(
        [runspecimen, "validate", "--workspace", str(workspace), "--contract", str(workspace / "contract.json")]
    )

    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(str(workspace))
        os.execvpe(
            runspecimen,
            [runspecimen, "approve", "--workspace", str(workspace), "--contract", str(workspace / "contract.json")],
            env,
        )
    buf = b""
    sent = False
    start = time.time()
    while True:
        if time.time() - start > 20:
            os.close(fd)
            os.waitpid(pid, 0)
            raise TimeoutError("approve timed out")
        ready, _, _ = select.select([fd], [], [], 0.15)
        if ready:
            try:
                chunk = os.read(fd, 8192)
            except OSError:
                chunk = b""
            if not chunk:
                break
            buf += chunk
            text = buf.decode("utf-8", "replace")
            if (not sent) and "Type " in text and "to bind" in text:
                os.write(fd, b"APPROVE\n")
                sent = True
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid != 0:
            while True:
                more, _, _ = select.select([fd], [], [], 0.05)
                if not more:
                    break
                try:
                    extra = os.read(fd, 8192)
                except OSError:
                    break
                if not extra:
                    break
                buf += extra
            os.close(fd)
            if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
                raise RuntimeError(buf.decode("utf-8", "replace"))
            break

    approve_out = buf.decode("utf-8", "replace").replace("\r", "")
    marker = "Type 'APPROVE' to bind this approval:"
    if marker not in approve_out:
        raise RuntimeError("approval prompt missing from capture")
    prompt, rest = approve_out.split(marker, 1)
    prompt = (prompt + marker + " ").rstrip(" ") + " "
    json_start = rest.find("{")
    approve_result = json.loads(rest[json_start:])

    preflight = run(
        [runspecimen, "preflight", "--workspace", str(workspace), "--contract", str(workspace / "contract.json")]
    )
    run_result = run(
        [runspecimen, "run", "--workspace", str(workspace), "--contract", str(workspace / "contract.json")]
    )
    postflight = run(
        [runspecimen, "postflight", "--workspace", str(workspace), "--contract", str(workspace / "contract.json")]
    )
    verify = run(
        [
            runspecimen,
            "verify",
            "--workspace",
            str(workspace),
            "--contract",
            str(workspace / "contract.json"),
            "--campaign-id",
            "demo-campaign",
            "--run-id",
            "run-001",
        ]
    )

    ws = str(workspace)
    session = {
        "cli_version": version,
        "source": "live CLI capture of `runspecimen init-demo` via PTY",
        "contract": "init-demo contract.json (demo-campaign / run-001)",
        "init": rewrite_workspace(init, ws),
        "doctor": rewrite_workspace(doctor, ws),
        "validate": rewrite_workspace(validate, ws),
        "approve_prompt": rewrite_workspace(prompt.replace(ws, PLACEHOLDER), ws),
        "approve_result": rewrite_workspace(approve_result, ws),
        "preflight_result": rewrite_workspace(preflight, ws),
        "run_result": rewrite_workspace(run_result, ws),
        "postflight_result": rewrite_workspace(postflight, ws),
        "verify_result": rewrite_workspace(verify, ws),
    }
    shutil.rmtree(parent, ignore_errors=True)
    return session


def load_session() -> dict:
    if not SESSION_PATH.is_file():
        raise SystemExit(f"missing {SESSION_PATH}; run with --capture first")
    return json.loads(SESSION_PATH.read_text(encoding="utf-8"))


def display_prompt(prompt: str) -> str:
    return prompt.replace(PLACEHOLDER, ".")


def scene_review(session: dict) -> list[tuple[Image.Image, int]]:
    term = Terminal(
        title="Review the contract",
        kicker="Step 1 of 4",
        caption="A person reads the command, inputs, output, timeout, and approval lifetime.",
    )
    frames = frames_type_command(
        term, "runspecimen approve --workspace . --contract contract.json"
    )
    prompt = display_prompt(session["approve_prompt"]).rstrip()
    # Stop before the trailing "Type 'APPROVE'…" so this clip is the review.
    body = prompt
    type_line = "Type 'APPROVE' to bind this approval:"
    if type_line in body:
        body = body.split(type_line, 1)[0].rstrip()
    frames.extend(frames_dump_lines(term, body, hold=2400))
    return frames


def scene_approve(session: dict) -> list[tuple[Image.Image, int]]:
    term = Terminal(
        title="Type APPROVE yourself",
        kicker="Step 2 of 4",
        caption="The phrase must be typed at an interactive TTY. Assistants cannot enter it.",
    )
    prompt = display_prompt(session["approve_prompt"])
    type_line = "Type 'APPROVE' to bind this approval: "
    keep = ("campaign:", "run_id:", "argv:", "ttl_sec:")
    for line in wrap_text(prompt.split(type_line, 1)[0].rstrip()):
        if any(token in line for token in keep):
            term.add(line, "muted")
    frames = frames_type_approve(term, type_line)
    frames.extend(
        frames_dump_lines(
            term,
            dumps(session["approve_result"]),
            hold=2000,
            kind_for=json_kind,
            bookmarks=('confirm_channel": "local_tty_approve"',),
            pin_bottom=False,
        )
    )
    return frames


def scene_run(session: dict) -> list[tuple[Image.Image, int]]:
    term = Terminal(
        title="Run once, then stop",
        kicker="Step 3 of 4",
        caption="Preflight re-checks the approval. Then exactly the declared command runs once.",
    )
    term.add_prompt_command("runspecimen preflight --workspace . --contract contract.json")
    frames = frames_dump_lines(term, dumps(session["preflight_result"]), hold=1100, kind_for=json_kind)
    term.clear()
    term.add_prompt_command("runspecimen run --workspace . --contract contract.json")
    term.cursor_visible = True
    frames.append((term.render(), 700))
    term.cursor_visible = False
    frames.extend(frames_dump_lines(term, dumps(session["run_result"]), hold=2200, kind_for=json_kind))
    return frames


def scene_verify(session: dict) -> list[tuple[Image.Image, int]]:
    term = Terminal(
        title="Verify the certified receipt",
        kicker="Step 4 of 4",
        caption="Postflight issues a certificate. Verify re-hashes live files against that receipt.",
    )
    term.add_prompt_command("runspecimen postflight --workspace . --contract contract.json")
    cert_lines = wrap_text(dumps(session["postflight_result"]))
    hit = next(i for i, line in enumerate(cert_lines) if "certificate_id" in line)
    window = cert_lines[max(0, hit - 1) : hit + 8]
    for line in window:
        term.add(line, json_kind(line))
    frames = [(term.render(), 1500)]
    term.clear()
    term.add_prompt_command("runspecimen verify --workspace . --contract contract.json")
    term.add("  --campaign-id demo-campaign --run-id run-001", "cmd")
    frames.extend(frames_dump_lines(term, dumps(session["verify_result"]), hold=2400, kind_for=json_kind))
    return frames


def scene_combined(session: dict) -> list[tuple[Image.Image, int]]:
    """Shorter join of the four completed states — no typing, small file."""
    frames: list[tuple[Image.Image, int]] = []

    review = Terminal(
        title="Review the contract",
        kicker="The core flow",
        caption="Four beats: review, type APPROVE, run once, verify the receipt.",
    )
    review.add_prompt_command("runspecimen approve --workspace . --contract contract.json")
    prompt = display_prompt(session["approve_prompt"])
    type_line = "Type 'APPROVE' to bind this approval: "
    body = prompt.split("Type 'APPROVE' to bind this approval:", 1)[0].rstrip()
    for line in wrap_text(body):
        review.add(line)
    frames.append((review.render(), 2200))

    approve = Terminal(
        title="Type APPROVE yourself",
        kicker="The core flow",
        caption="Interactive TTY only. Piped or unattended approval is refused.",
    )
    prompt_body = display_prompt(session["approve_prompt"])
    keep = ("campaign:", "run_id:", "argv:", "ttl_sec:")
    for line in wrap_text(prompt_body.split(type_line, 1)[0].rstrip()):
        if any(token in line for token in keep):
            approve.add(line, "muted")
    approve.add(type_line + "APPROVE", "typed")
    frames.append((approve.render(), 2000))

    run = Terminal(
        title="Run once, then stop",
        kicker="The core flow",
        caption="The declared argv runs once inside the wall-clock limit.",
    )
    run.add_prompt_command("runspecimen run --workspace . --contract contract.json")
    for line in wrap_text(dumps(session["run_result"])):
        run.add(line, json_kind(line))
    frames.append((run.render(), 2000))

    verify = Terminal(
        title="Verify the certified receipt",
        kicker="The core flow",
        caption="Live contract, source, runtime, and outputs must still match.",
    )
    verify.add_prompt_command(
        "runspecimen verify --workspace . --contract contract.json \\\n"
        "  --campaign-id demo-campaign --run-id run-001"
    )
    for line in wrap_text(dumps(session["verify_result"])):
        verify.add(line, json_kind(line))
    frames.append((verify.render(), 2600))
    return frames


def write_manifest(paths: list[Path]) -> None:
    rows = []
    for path in paths:
        with Image.open(path) as im:
            rows.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "width": im.size[0],
                    "height": im.size[1],
                    "frames": getattr(im, "n_frames", 1),
                    "bytes": path.stat().st_size,
                }
            )
    (ASSETS / "manifest.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print("Wrote", ASSETS / "manifest.json")
    for row in rows:
        kb = row["bytes"] / 1024
        print(f"  {row['file']:40} {row['width']}x{row['height']}  {row['frames']:4} frames  {kb:7.1f} KiB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Run a live init-demo lifecycle and overwrite transcripts/session.json",
    )
    parser.add_argument(
        "--runspecimen",
        default=shutil.which("runspecimen") or "runspecimen",
        help="Path to the runspecimen CLI (for --capture)",
    )
    args = parser.parse_args(argv)

    if args.capture:
        print("Capturing live CLI session…")
        session = capture_session(args.runspecimen)
        TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
        SESSION_PATH.write_text(json.dumps(session, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Wrote", SESSION_PATH)
    else:
        session = load_session()

    ASSETS.mkdir(parents=True, exist_ok=True)
    outputs = [
        (scene_review(session), ASSETS / "01-review-contract.gif"),
        (scene_approve(session), ASSETS / "02-type-approve.gif"),
        (scene_run(session), ASSETS / "03-run-execute.gif"),
        (scene_verify(session), ASSETS / "04-verify-receipt.gif"),
        (scene_combined(session), ASSETS / "00-full-lifecycle.gif"),
    ]
    paths: list[Path] = []
    for frames, path in outputs:
        print("Rendering", path.name, "…")
        save_gif(frames, path)
        paths.append(path)
    write_manifest(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
