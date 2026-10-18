# YT Downloader Pro 🚀

A modern, fast, and robust YouTube Downloader built with Python, `customtkinter`, and `yt-dlp`.
Download video or audio from YouTube in the highest quality directly to your PC, while preserving the best audio bitrates and codecs!

## Features
- **Dark Mode UI**: Professional dark aesthetic using CustomTkinter.
- **Top Quality Video**: Automatically fetches the best visual feeds and merges them using `ffmpeg`.
- **Top Quality Audio**: Extracts lossless or high-bitrate MP3/FLAC music tracks.
- **Resolution Picker**: Automatically detects available resolutions (up to 4K) for each video.
- **One-Click Launch**: `run.bat` finds Python, installs missing dependencies and starts the app. No console window left behind.

## Prerequisites

### 1. Python
Install **Python 3.10+** from [python.org](https://www.python.org/downloads/).

> **Windows users**: Make sure to check ✅ **"Add Python to PATH"** during installation.

### 2. FFmpeg (required for audio extraction & video merging)

**Windows:**
1. Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (select a Windows build).
2. Extract the archive and copy the `bin` folder contents to `C:\ffmpeg\bin\`.
3. Add `C:\ffmpeg\bin` to your system `PATH` environment variable.

The app also checks `C:\ffmpeg\bin` automatically, so if ffmpeg lives there you can skip the PATH step.

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Linux (apt):**
```bash
sudo apt update && sudo apt install ffmpeg
```

### 3. Python Dependencies
Install all required packages with a single command:
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install yt-dlp customtkinter Pillow
```

## Usage

**Windows:** double-click `run.bat`. On first run it verifies the dependencies, installs anything missing, and then the app window opens without a console hanging around.

**Any OS, from source:**
```bash
git clone https://github.com/ErynVornTechnologies/yt-downloader-pro.git
cd yt-downloader-pro
python downloader.py
```

Then paste a YouTube URL, click **Check** to load formats, select your desired resolution or audio settings, choose the output folder, and hit **DOWNLOAD**!

## What's new in v2.0
- **Thread-safe UI**: download workers never touch the GUI directly, so the window can no longer crash mid-download (the v1 progress hook did exactly that).
- **The link you Check is the link you download**: pasting a different URL after Check no longer downloads the wrong video with a stale resolution.
- **Locale-proof progress**: computed from byte counts instead of parsing localized percent strings.
- **`run.bat` launcher** with automatic dependency installation.
- **ErynVorn Technologies** branding and logo.

## Custom Logo
The window header shows `logo.png` from the app folder. Swap the file to use your own branding; if it is missing, a text title is displayed instead.

## Troubleshooting

| Problem | Solution |
|---|---|
| `ffmpeg` not found | Make sure FFmpeg is installed and added to your system PATH |
| No audio in downloaded video | Install or update FFmpeg: it is required for merging audio + video streams |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` to install all dependencies |
| App crashed during a download | Fixed in v2.0, update to the latest version |
| `Sign in to confirm you're not a bot` | YouTube rate-limited your IP (too many extractions in a short window). Wait a while, or pass cookies: add `'cookiefile': 'cookies.txt'` to the yt-dlp options in `downloader.py` with a `cookies.txt` exported from a signed-in browser |

## License
MIT License. Free for personal and commercial use.

---
*Brought to you by [ErynVorn Technologies](https://erynvorntechnologies.com/). Follow us for more AI toolkits and autonomous engineering insights!*