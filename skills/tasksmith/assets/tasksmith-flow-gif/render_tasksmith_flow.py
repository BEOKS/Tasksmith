#!/usr/bin/env python3
"""Render the Tasksmith GSAP demo to WebM and GIF."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "index.html"
GIF_SCRIPT = Path("/Users/leejs/.codex/skills/gsap-gif-creator/scripts/video_to_gif.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the Tasksmith flow demo.")
    parser.add_argument(
        "--webm",
        default=str(ROOT / "tasksmith-flow.webm"),
        help="Output WebM path",
    )
    parser.add_argument(
        "--gif",
        default=str(ROOT / "tasksmith-flow.gif"),
        help="Output GIF path",
    )
    parser.add_argument("--width", type=int, default=1200, help="Viewport width")
    parser.add_argument("--height", type=int, default=675, help="Viewport height")
    parser.add_argument("--gif-width", type=int, default=560, help="GIF width")
    parser.add_argument("--fps", type=int, default=12, help="GIF fps")
    parser.add_argument("--colors", type=int, default=80, help="GIF palette size")
    return parser.parse_args()


def run_http_server(directory: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def convert_to_gif(input_path: Path, output_path: Path, gif_width: int, fps: int, colors: int) -> None:
    cmd = [
        sys.executable,
        str(GIF_SCRIPT),
        str(input_path),
        str(output_path),
        "--width",
        str(gif_width),
        "--fps",
        str(fps),
        "--colors",
        str(colors),
        "--overwrite",
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    webm_path = Path(args.webm).expanduser().resolve()
    gif_path = Path(args.gif).expanduser().resolve()
    webm_path.parent.mkdir(parents=True, exist_ok=True)
    gif_path.parent.mkdir(parents=True, exist_ok=True)

    if not HTML_FILE.exists():
        raise SystemExit(f"Missing HTML source: {HTML_FILE}")
    if not GIF_SCRIPT.exists():
        raise SystemExit(f"Missing GIF converter: {GIF_SCRIPT}")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required but was not found in PATH.")

    server, thread = run_http_server(ROOT)
    base_url = f"http://127.0.0.1:{server.server_port}/index.html"

    try:
        with tempfile.TemporaryDirectory(prefix="tasksmith-flow-video-") as temp_dir:
            video_dir = Path(temp_dir)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": args.width, "height": args.height},
                    record_video_dir=str(video_dir),
                    record_video_size={"width": args.width, "height": args.height},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(base_url, wait_until="networkidle")
                page.wait_for_function("window.__TASKSMITH_READY === true")
                loop_ms = int(page.evaluate("window.__TASKSMITH_LOOP_MS"))
                page.evaluate("window.startTasksmithAnimation()")
                page.wait_for_timeout(loop_ms + 120)
                context.close()
                browser.close()

            video_files = sorted(video_dir.glob("*.webm"))
            if not video_files:
                raise SystemExit("Playwright did not record a WebM output.")

            shutil.move(str(video_files[0]), str(webm_path))
            convert_to_gif(webm_path, gif_path, args.gif_width, args.fps, args.colors)

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    print(f"[OK] WebM: {webm_path}")
    print(f"[OK] GIF:  {gif_path}")


if __name__ == "__main__":
    main()
