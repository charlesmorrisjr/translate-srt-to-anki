#!/usr/bin/env python3
"""
Convert a Spanish SRT subtitle file to an Anki-ready CSV.
Requires: pip install deep-translator
Usage:
  python translate-srt-to-anki.py input.srt [output.csv]
  python translate-srt-to-anki.py input.srt [output.csv] --video /path/to/video.mp4 [--media-dir images]
If output is not provided, the CSV will be written next to the input with the same name and a .csv extension.
If --video is provided, a screenshot will be extracted for each subtitle at the midpoint of its time range
and an additional Image column will be added to the CSV with an <img src="..."> tag referencing the file.
Place the CSV and images in the same folder when importing into Anki so the importer can copy the media.
"""

import sys
import re
import csv
import argparse
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple


def parse_timestamp_to_seconds(timestamp: str) -> float:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", timestamp)
    if not match:
        raise ValueError(f"Invalid timestamp: {timestamp}")
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def parse_srt_with_timing(lines: List[str]) -> List[Tuple[int, float, float, str]]:
    """
    Returns a list of tuples: (index, start_seconds, end_seconds, text)
    Joins multi-line subtitle text within the same block with spaces.
    Filters out bracketed notes-only lines within a block.
    """
    blocks: List[Tuple[int, float, float, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        # Skip empty lines
        if not lines[i].strip():
            i += 1
            continue
        # Index line
        index_line = lines[i].strip()
        if not re.match(r"^\d+$", index_line):
            # Unexpected; try to continue searching
            i += 1
            continue
        try:
            idx = int(index_line)
        except ValueError:
            i += 1
            continue
        i += 1
        if i >= n:
            break
        # Timestamp line
        time_line = lines[i].strip()
        time_match = re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})", time_line)
        if not time_match:
            i += 1
            continue
        start_ts, end_ts = time_match.groups()
        start_s = parse_timestamp_to_seconds(start_ts)
        end_s = parse_timestamp_to_seconds(end_ts)
        i += 1
        # Collect text lines until blank line
        text_lines: List[str] = []
        while i < n and lines[i].strip():
            line_text = lines[i].strip()
            # Skip bracketed notes like [Música]
            if re.match(r"^\[.*\]$", line_text):
                i += 1
                continue
            text_lines.append(line_text)
            i += 1
        # Skip the blank line separator
        while i < n and not lines[i].strip():
            i += 1
        if not text_lines:
            continue
        merged_text = " ".join(text_lines)
        blocks.append((idx, start_s, end_s, merged_text))
    return blocks


def extract_screenshot(video_path: str, timestamp_sec: float, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Use -ss before input for fast seek and after input for accuracy
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{timestamp_sec:.3f}",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg and try again.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed when extracting {output_path.name}") from e


def should_filter_subtitle_text(text: str) -> bool:
    """Return True if the subtitle text should be removed as trivial or name-only."""
    t = text.strip()
    if not t:
        return True
    lower = t.lower()
    trivial = {
        "ah", "ah.", "eh", "eh.", "uh", "uh.", "oh", "oh.",
        "mm", "mm.", "mmm", "mmm.", "hmm", "hmm.", "m", "m."
    }
    # Remove leading dashes and trailing punctuation for checks
    lower_stripped = re.sub(r"^[\-—–_\s]+|[\s\.,!\?…·•;:¡¿]+$", "", lower)
    if lower in trivial or lower_stripped in trivial:
        return True
    # Single-letter with optional period, e.g., "M" or "M."
    if re.match(r"^[a-záéíóúñ]\.?$", lower_stripped):
        return True
    # Speaker/name-only line: allow trailing punctuation like '.', '!', '?', ':'
    caps_stripped = re.sub(r"^[\-—–_\s]+|[\s\.,!\?…·•;:¡¿]+$", "", t)
    if re.match(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+$", caps_stripped):
        return True
    if re.match(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+:$", t.strip()):
        return True
    # Very short 1-2 token interjection-like phrases
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", t)
    if len(tokens) <= 2:
        joined = " ".join(tok.lower() for tok in tokens)
        if joined in trivial:
            return True
    return False


def srt_to_anki_csv(input_path: str, output_path: str, video_path: Optional[str] = None, media_dir: Optional[str] = None, image_name_prefix: Optional[str] = None):
    print(f"Reading SRT: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    print("Parsing subtitles ...")
    blocks = parse_srt_with_timing(lines)
    print(f"Parsed {len(blocks)} blocks")

    before_filter = len(blocks)
    blocks = [b for b in blocks if not should_filter_subtitle_text(b[3])]
    removed_filter = before_filter - len(blocks)
    print(f"Filtering trivial/name-only lines: kept {len(blocks)} (removed {removed_filter})")

    if video_path is None:
        print("Removing duplicate subtitle texts ...")
        seen_texts = set()
        filtered_blocks = []
        for idx, start_s, end_s, text in blocks:
            if text in seen_texts:
                continue
            seen_texts.add(text)
            filtered_blocks.append((idx, start_s, end_s, text))
        dup_removed = len(blocks) - len(filtered_blocks)
        blocks = filtered_blocks
        print(f"Deduped: kept {len(blocks)} (removed {dup_removed})")

    # Translate (lazy import so -h works without deep-translator installed)
    try:
        from deep_translator import GoogleTranslator
    except ModuleNotFoundError as e:
        raise SystemExit("Missing dependency: deep-translator. Install with: pip install deep-translator") from e
    translator = GoogleTranslator(source="es", target="en")

    output_csv_path = Path(output_path)
    if video_path:
        media_root = Path(media_dir) if media_dir else output_csv_path.with_suffix("").parent / "images"
        if not media_dir:
            media_root = output_csv_path.parent / "images"
        media_root.mkdir(parents=True, exist_ok=True)
        image_rel_prefix = media_root.name

    total = len(blocks)
    if video_path:
        print(f"Translating and extracting screenshots for {total} subtitles ...")
    else:
        print(f"Translating {total} subtitles ...")

    rows: List[List[str]] = []
    prefix = image_name_prefix or Path(input_path).stem
    for i, (idx, start_s, end_s, es_text) in enumerate(blocks, start=1):
        en_text = translator.translate(es_text)
        if video_path:
            midpoint = start_s + max(0.0, (end_s - start_s)) / 2.0
            image_name = f"{prefix}-{i:04d}.jpg"
            image_path = media_root / image_name
            extract_screenshot(video_path, midpoint, image_path)
            image_field = f"<img src='{image_name}'>"
            rows.append([es_text, en_text, image_field])
        else:
            rows.append([es_text, en_text])
        if i == total or i % 25 == 0:
            sys.stdout.write(f"\r  progress: {i}/{total}")
            sys.stdout.flush()
    if total:
        sys.stdout.write("\n")
        sys.stdout.flush()

    print(f"Writing CSV to {output_path} ...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if video_path:
            writer.writerow(["Spanish", "English", "Image"])
        else:
            writer.writerow(["Spanish", "English"])
        writer.writerows(rows)

    print(f"CSV saved to {output_path}")


def _choose_best_srt_file(candidates: List[Path]) -> Optional[Path]:
    if not candidates:
        return None
    def lang_score(p: Path) -> int:
        name = p.name
        return 0 if re.search(r"\.es([\._\-].*)?\.srt$", name) else 1
    def is_auto(p: Path) -> int:
        return 1 if "auto" in p.name.lower() else 0
    sorted_candidates = sorted(
        candidates,
        key=lambda p: (lang_score(p), is_auto(p), -p.stat().st_mtime)
    )
    return sorted_candidates[0]


def download_subtitles_with_yt_dlp(url: str, out_dir: Path, sub_langs: str = "es,es-ES,es-419") -> Path:
    print(f"[yt-dlp] Downloading subtitles ({sub_langs}) to {out_dir} ...")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", sub_langs,
        "--sub-format", "srt",
        "--convert-subs", "srt",
        "--windows-filenames",
        "-o", out_tmpl,
        url,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Please install yt-dlp and try again.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("yt-dlp failed while downloading subtitles") from e
    srt_files = list(out_dir.glob("*.srt"))
    best = _choose_best_srt_file(srt_files)
    if not best:
        raise RuntimeError("No .srt subtitles were downloaded by yt-dlp. Check language availability with --list-subs.")
    print(f"[yt-dlp] Found subtitles: {best}")
    return best


def download_video_with_yt_dlp(url: str, out_dir: Path) -> Path:
    print(f"[yt-dlp] Downloading video to {out_dir} ...")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--windows-filenames",
        "-o", out_tmpl,
        url,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Please install yt-dlp and try again.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("yt-dlp failed while downloading the video") from e
    preferred_exts = ["*.mp4", "*.mkv", "*.webm", "*.mov"]
    candidates: List[Path] = []
    for pattern in preferred_exts:
        candidates.extend(out_dir.glob(pattern))
    if not candidates:
        raise RuntimeError("Video download completed but no output video file was found.")
    chosen = sorted(candidates, key=lambda p: -p.stat().st_mtime)[0]
    print(f"[yt-dlp] Video saved: {chosen}")
    return chosen


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _derive_title_from_srt_filename(srt_path: Path) -> str:
    """Return a clean title from an SRT filename like 'Title.es.srt' -> 'Title'."""
    stem = srt_path.stem  # e.g., 'My Video.es'
    m = re.match(r"^(?P<title>.+?)\.(?P<lang>[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?)$", stem)
    if m:
        return m.group("title")
    return stem


def _extract_youtube_id(url: str) -> Optional[str]:
    """Attempt to extract the 11-char YouTube video ID from common URL forms."""
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"/shorts/([A-Za-z0-9_-]{11})",
        r"/embed/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _sanitize_title_for_filename(title: str) -> str:
    """Replace filesystem-problematic characters with hyphens and normalize dashes."""
    # Normalize Unicode to fold full-width punctuation, etc.
    s = unicodedata.normalize('NFKC', title)
    # Normalize various dash-like characters to ASCII hyphen
    s = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]", "-", s)
    # Replace forbidden characters with '-'
    s = re.sub(r"[\\/:*?\"<>|]", "-", s)
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s).strip()
    # Collapse multiple hyphens
    s = re.sub(r"-+", "-", s)
    # Avoid names ending with a dot or space
    s = s.rstrip(" .")
    return s


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a Spanish SRT subtitle file to an Anki-ready CSV, optionally with screenshots from a matching video.")
    parser.add_argument("input", nargs="?", help="Path to input .srt file or a YouTube URL")
    parser.add_argument("output", nargs="?", help="Path to output .csv file. Defaults to input name with .csv extension")
    parser.add_argument("--video", dest="video", help="Path to the corresponding video file for taking screenshots")
    parser.add_argument("--media-dir", dest="media_dir", help="Directory to save images (default: images next to CSV)")
    # yt-dlp integration
    parser.add_argument("--yt-url", dest="yt_url", help="Video URL to download Spanish subtitles via yt-dlp (and optionally the video)")
    parser.add_argument("--yt-sub-langs", dest="yt_sub_langs", default="es,es-ES,es-419", help="Comma-separated subtitle language codes to request (default: es,es-ES,es-419)")
    parser.add_argument("--lang", dest="single_lang", help="Single subtitle language code (alias for --yt-sub-langs)")
    parser.add_argument("--yt-out-dir", dest="yt_out_dir", help="Directory to place yt-dlp downloads (default: temporary directory)")
    parser.add_argument("--yt-download-video", dest="yt_download_video", action="store_true", help="Also download the video via yt-dlp for --video screenshots if --video not provided")

    args = parser.parse_args()

    input_path: Optional[str] = args.input
    output_path: Optional[str] = args.output

    # If the first positional input looks like a URL, treat it as --yt-url
    if input_path and _is_url(input_path):
        args.yt_url = input_path
        input_path = None

    temp_dir_obj = None
    try:
        # If a yt URL is provided and no input SRT, fetch subtitles (and maybe video)
        if args.yt_url and not input_path:
            from tempfile import TemporaryDirectory
            # Decide download directory: explicit --yt-out-dir, else output CSV's directory if provided, else temp
            if args.yt_out_dir:
                yt_out_dir = Path(args.yt_out_dir)
                temp_dir_obj = None
            elif output_path:
                yt_out_dir = Path(output_path).parent
                temp_dir_obj = None
            else:
                temp_dir_obj = TemporaryDirectory()
                yt_out_dir = Path(temp_dir_obj.name)
            sub_langs = args.single_lang or args.yt_sub_langs
            srt_path = download_subtitles_with_yt_dlp(args.yt_url, yt_out_dir, sub_langs=sub_langs)
            input_path = str(srt_path)

            # Derive a safe base title and append the video ID
            raw_title = _derive_title_from_srt_filename(Path(input_path))
            video_id = _extract_youtube_id(args.yt_url)
            base_title = f"{raw_title} [{video_id}]" if video_id else raw_title

            # Default output in the current working directory if not given
            if not output_path:
                output_path = str(Path.cwd() / f"{base_title}.csv")
            # Download video only if requested and not already given
            if args.yt_download_video and not args.video:
                video_file = download_video_with_yt_dlp(args.yt_url, yt_out_dir)
                args.video = str(video_file)

        if not input_path:
            raise SystemExit("You must provide an input .srt file or a URL.")

        final_output_path = output_path or str(Path(input_path).with_suffix(".csv"))

        # Decide image prefix: prefer derived safe title + [id] when URL flow is used
        image_prefix = None
        if args.yt_url:
            raw_title = _derive_title_from_srt_filename(Path(input_path))
            video_id = _extract_youtube_id(args.yt_url)
            image_prefix = f"{raw_title} [{video_id}]" if video_id else raw_title

        srt_to_anki_csv(input_path, final_output_path, video_path=args.video, media_dir=args.media_dir, image_name_prefix=image_prefix)
    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()
