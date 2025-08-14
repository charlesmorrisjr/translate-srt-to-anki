## translate-srt-to-anki

Convert a Spanish `.srt` subtitle file into an Anki‑ready CSV. Optionally, take a video timestamp screenshot per subtitle and add an Image column with an HTML `<img>` tag for easy importing into Anki.

### Features
- **Spanish → English translation**: Uses `deep-translator` (GoogleTranslator).
- **Subtitle parsing**: Merges multi-line subtitle blocks; keeps timing to compute midpoints for screenshots.
- **Noise filtering**: Drops trivial interjections (e.g., "ah", "oh"), single-letter lines, and speaker/name-only lines.
- **Duplicate removal**: When not generating images, deduplicates identical subtitle text to reduce repetition.
- **Optional screenshots**: If a matching video is provided, extracts a frame at each subtitle midpoint via `ffmpeg` and adds an Image column containing an `<img src="...">` tag.

## Requirements
- **Python**: 3.8+
- **Packages**: `deep-translator`
- **Optional**: `ffmpeg` (required only for `--video` screenshots)

Install Python dependency:
```bash
pip install deep-translator
```

Install `ffmpeg` (if using `--video`):
- Debian/Ubuntu: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Arch: `sudo pacman -S ffmpeg`

## Usage
Basic:
```bash
python translate-srt-to-anki.py input.srt [output.csv]
```
With screenshots from a matching video and optional media directory:
```bash
python translate-srt-to-anki.py input.srt [output.csv] --video /path/to/video.mp4 [--media-dir images]
```
Show help:
```bash
python translate-srt-to-anki.py -h
```

### Behavior and outputs
- If `output.csv` is omitted, it will be written next to `input.srt` with the same name and a `.csv` extension.
- When `--video` is provided:
  - One screenshot is extracted per subtitle at the midpoint of its time range.
  - An additional `Image` column is added to the CSV containing `<img src='FILENAME.jpg'>`.
  - Images are saved in a folder (default `images` next to the CSV, or `--media-dir` if provided).
  - Keep the CSV and images together when importing into Anki so the importer can copy media.
- When `--video` is not provided:
  - Duplicate subtitle texts are removed to reduce repetition.

### Examples
- Minimal translation only, CSV saved as `movie.csv` alongside `movie.srt`:
```bash
python translate-srt-to-anki.py /path/to/movie.srt
```
- Explicit output path:
```bash
python translate-srt-to-anki.py /path/to/movie.srt /path/to/out/movie.csv
```
- With screenshots, images saved to `images/` alongside the CSV:
```bash
python translate-srt-to-anki.py /path/to/movie.srt /path/to/out/movie.csv --video /path/to/movie.mp4
```
- With screenshots, custom media folder:
```bash
python translate-srt-to-anki.py /path/to/movie.srt /path/to/out/movie.csv --video /path/to/movie.mp4 --media-dir /path/to/out/subtitle-images
```

## CSV format
- Columns without `--video`: `Spanish`, `English`
- Columns with `--video`: `Spanish`, `English`, `Image`
  - The `Image` field contains HTML like: `<img src='somefile.jpg'>`
  - The filename is relative; keep images in the same folder you point Anki to during import.

## Importing into Anki
1. Open Anki → File → Import.
2. Select the generated CSV.
3. In the import options:
   - **Type**: Notes (choose or create a note type that has fields for Spanish, English, and optionally Image).
   - **Fields**: Map 1 → Spanish, 2 → English, 3 → Image (if present).
   - **Separator**: Comma.
   - **Allow HTML**: Enabled (Anki accepts HTML by default; the `<img>` tag will render the image).
4. Ensure the images folder is colocated so Anki can copy the media.
5. Finish import.

## Filtering rules
- Removes bracketed notes like `[Música]`.
- Removes trivial interjections (e.g., "ah", "oh", "hmm"), including variants with trailing punctuation.
- Removes single-letter lines (e.g., `M` / `M.`) and speaker/name-only lines.

## Troubleshooting
- **ffmpeg not found**: Install `ffmpeg` and ensure it’s on your `PATH` (see Requirements).
- **Translation errors/rate limiting**: The `deep-translator` Google backend may occasionally throttle or fail; retry later.
- **Garbled characters**: Ensure your `.srt` is UTF‑8 encoded. The script reads with `encoding="utf-8"`.

## Notes
- Screenshots are taken at each subtitle’s midpoint timestamp for best context.
- When generating images, duplicates are not removed to keep image filenames aligned with subtitle order. 