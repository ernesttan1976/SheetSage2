from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import gradio as gr

from split_youtube_songs import DEFAULT_URL, safe_name


def command(args: list[str], capture: bool = False) -> str:
    result = subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def chapters_from_file(source: Path) -> list[dict]:
    raw = command([
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_chapters",
        str(source),
    ], True)
    return json.loads(raw).get("chapters", [])


def split_source(source: Path, title: str, chapters: list[dict], output: Path, extension: str) -> Path:
    if not chapters:
        raise ValueError("No chapters were found. Use a media file with chapter timestamps or a YouTube video with chapters.")

    root = output / safe_name(title)
    root.mkdir(parents=True, exist_ok=True)
    codec = {"m4a": "aac", "mp3": "libmp3lame", "wav": "pcm_s16le"}[extension]
    for index, chapter in enumerate(chapters, 1):
        chapter_title = safe_name(chapter.get("title", f"Song {index:02d}"))
        start = float(chapter.get("start_time", 0))
        end = float(chapter.get("end_time", 0))
        if end <= start:
            continue
        song_dir = root / chapter_title
        song_dir.mkdir(parents=True, exist_ok=True)
        destination = song_dir / f"{chapter_title}.{extension}"
        args = [
            "ffmpeg", "-hide_banner", "-y", "-ss", str(start), "-to", str(end),
            "-i", str(source), "-map", "0:a:0", "-vn", "-c:a", codec,
        ]
        if extension == "m4a":
            args += ["-b:a", "192k"]
        elif extension == "mp3":
            args += ["-q:a", "2"]
        command(args + [str(destination)])
    return root


def process(url: str, media_file: str | None, output_format: str) -> tuple[str | None, str]:
    if not url.strip() and not media_file:
        return None, "Provide a YouTube URL or choose a local audio/video file."
    if url.strip() and media_file:
        return None, "Choose one input source, not both."

    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        output = work / "songs"
        output.mkdir()
        if url.strip():
            info = json.loads(command([
                "yt-dlp", "--no-warnings", "--dump-single-json", "--skip-download", url.strip()
            ], True))
            title = info.get("title", "YouTube Audio")
            chapters = info.get("chapters") or []
            source = work / "source.m4a"
            command([
                "yt-dlp", "--no-playlist", "-f", "bestaudio/best", "-x",
                "--audio-format", "m4a", "-o", str(source), url.strip()
            ])
        else:
            source = Path(media_file)
            title = source.stem
            chapters = chapters_from_file(source)

        root = split_source(source, title, chapters, output, output_format)
        archive_base = work / safe_name(title)
        archive = Path(shutil.make_archive(str(archive_base), "zip", root.parent, root.name))
        destination = Path("/tmp") / archive.name
        shutil.copy2(archive, destination)
        return str(destination), f"Completed: {len(chapters)} song folder(s) created for {safe_name(title)}."


def process_safe(url: str, media_file: str | None, output_format: str):
    try:
        return process(url, media_file, output_format)
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else str(error)
        return None, f"Command failed: {details}"
    except Exception as error:
        return None, str(error)


with gr.Blocks(title="Song Splitter") as demo:
    gr.Markdown("# Song Splitter\nExtract audio and split chaptered media into song-title folders.")
    with gr.Row():
        url = gr.Textbox(label="YouTube URL", placeholder=DEFAULT_URL)
        media_file = gr.File(label="Or choose a local audio/video file", type="filepath", file_types=[".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".wav"])
    output_format = gr.Radio(["m4a", "mp3", "wav"], value="m4a", label="Output format")
    run_button = gr.Button("Extract and split", variant="primary")
    status = gr.Textbox(label="Status", interactive=False)
    download = gr.File(label="Download ZIP", interactive=False)
    run_button.click(process_safe, inputs=[url, media_file, output_format], outputs=[download, status])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
