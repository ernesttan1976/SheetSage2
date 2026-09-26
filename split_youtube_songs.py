from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_URL = "https://www.youtube.com/watch?v=6H6re5ECEZQ"


def require_program(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required program: {name}. Install it and add it to PATH.")


def run(command: list[str], capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=None,
    )
    return result.stdout if capture else ""


def safe_name(value: str) -> str:
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", value)
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    return value or "Untitled"


def get_video_info(url: str) -> dict:
    raw = run(["yt-dlp", "--no-warnings", "--dump-single-json", "--skip-download", url], True)
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract YouTube audio and split chaptered music videos into song folders."
    )
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("-o", "--output", default="songs", help="Output directory")
    parser.add_argument("--format", choices=["m4a", "mp3", "wav"], default="m4a")
    args = parser.parse_args()

    require_program("yt-dlp")
    require_program("ffmpeg")

    info = get_video_info(args.url)
    video_title = safe_name(info.get("title", "YouTube Audio"))
    chapters = info.get("chapters") or []
    if not chapters:
        raise SystemExit(
            "No YouTube chapters were found. Add song timestamps as chapters, or provide a manual segment list."
        )

    root = Path(args.output).expanduser().resolve() / video_title
    root.mkdir(parents=True, exist_ok=True)
    source = root / "_full_audio.m4a"

    print(f"Downloading audio: {video_title}")
    run([
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestaudio/best",
        "-x",
        "--audio-format",
        "m4a",
        "-o",
        str(source),
        args.url,
    ])

    extension = args.format
    codec = {"m4a": "aac", "mp3": "libmp3lame", "wav": "pcm_s16le"}[extension]
    for index, chapter in enumerate(chapters, 1):
        title = safe_name(chapter.get("title", f"Song {index:02d}"))
        start = float(chapter.get("start_time", 0))
        end = chapter.get("end_time")
        if end is None:
            end = float(info.get("duration") or 0)
        if end <= start:
            continue

        song_dir = root / title
        song_dir.mkdir(parents=True, exist_ok=True)
        output = song_dir / f"{title}.{extension}"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-ss",
            str(start),
            "-to",
            str(end),
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-c:a",
            codec,
        ]
        if extension == "m4a":
            command += ["-b:a", "192k"]
        elif extension == "mp3":
            command += ["-q:a", "2"]
        command.append(str(output))
        print(f"[{index}/{len(chapters)}] {title}")
        run(command)

    source.unlink(missing_ok=True)
    print(f"Saved songs to: {root}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
