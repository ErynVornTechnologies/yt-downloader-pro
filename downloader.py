"""YT Downloader Pro - high-quality YouTube video and audio extraction.

by Erynvorn Technologies
https://erynvorntechnologies.com | https://github.com/ErynVornTechnologies

Paste a YouTube link, Check the available resolutions, then download:
- Video (Film): best video + audio pair merged with ffmpeg (mp4, or avi),
- Audio (Music): MP3/FLAC extraction at up to 320 kbps.

v2.0 changes:
- Thread-safe UI: worker threads never touch Tk widgets. They push event
  tuples onto a queue drained by a poller on the main loop (the v1 code
  called progress-bar and label updates straight from the download thread,
  which can crash the GUI mid-run).
- The URL that was Checked is the URL that downloads. v1 re-read the entry
  box at download time, so pasting a new link after Check silently
  downloaded a different video with the old resolution selection.
- Progress computed from byte counts (locale-proof) instead of parsing
  yt-dlp's percent string.
- Shorts-proof quality picker: resolutions are labelled by the short side
  of the frame (a 720x1280 vertical Short is 720p, like YouTube's own
  labels) and selected with a matching sort cap, so vertical videos
  download at the quality you picked.
- run.bat double-click launcher (auto-installs dependencies on first run).
- ErynVorn branding.
"""
import os
import queue
import threading
import time
import webbrowser

import customtkinter as ctk
import yt_dlp
from PIL import Image
from tkinter import filedialog, messagebox

APP_NAME = "YT Downloader Pro"
BRAND_URL = "https://erynvorntechnologies.com/"
FFMPEG_DIR = r"C:\ffmpeg\bin"
AUDIO_TAB = "Audio (Music)"
VIDEO_TAB = "Video (Film)"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# --- Pure helpers (unit-testable without the GUI) --------------------------

def _short_side(f):
    """Smaller frame dimension: matches YouTube's own quality labels."""
    w, h = f.get("width"), f.get("height")
    if w and h:
        return min(w, h)
    return h


def pick_resolutions(formats):
    """Resolutions offered in the picker: up to three, >=720p preferred.

    Labelled by the SHORT side of the frame, the way YouTube labels its
    own qualities: a 720x1280 vertical Short is 720p, not 1280p.
    """
    sides = sorted({_short_side(f) for f in formats
                    if f.get("vcodec") not in (None, "none", "images")
                    and (f.get("width") or f.get("height"))},
                   reverse=True)
    top = [s for s in sides if s >= 720][:3]
    return ["%dp" % s for s in (top or sides[:3])]


def display_title(title):
    """One-line title for the header label, truncated to 60 chars."""
    title = title or ""
    return title[:60] + "..." if len(title) > 60 else title


def build_ydl_opts(save_path, mode, audio_fmt=None, bitrate=None,
                   video_fmt=None, resolution=None, progress_hook=None):
    """yt-dlp options for one download. Pure function, no GUI state."""
    opts = {
        "outtmpl": os.path.join(save_path, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if os.path.exists(os.path.join(FFMPEG_DIR, "ffmpeg.exe")):
        opts["ffmpeg_location"] = FFMPEG_DIR
    if mode == AUDIO_TAB:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_fmt,
            "preferredquality": bitrate,
        }]
    else:
        short_side = str(resolution).rstrip("p")
        # Orientation-proof selection: the 'res' sort field caps the short
        # side of the frame (YouTube label semantics), so 720p resolves to
        # 1280x720 horizontal and 720x1280 vertical alike. h264 wins ties
        # over vp9/av01 so the file plays everywhere.
        opts["format"] = "bestvideo+bestaudio/best"
        opts["format_sort"] = ["res:%s" % short_side, "vcodec:h264"]
        opts["merge_output_format"] = "mp4"
        if video_fmt == "avi":
            opts["postprocessors"] = [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "avi",  # yt-dlp spells this key without the 'r'
            }]
    return opts


def human_size(num):
    """Bytes -> human string (progress speed readout)."""
    if not num:
        return "--"
    num = float(num)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if num < 1024:
            return "%.1f %s" % (num, unit)
        num /= 1024
    return "%.1f TiB" % num


# --- GUI --------------------------------------------------------------------

class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("600x950")
        self.resizable(False, False)

        self.save_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.checked_url = None      # URL whose info is loaded (set by Check)
        self.ui_queue = queue.Queue()
        self._last_progress_push = 0.0

        # Workers never touch Tk: they push event tuples onto ui_queue and
        # this poller applies them on the main loop every ~100 ms.
        self.after(100, self._poll_ui_queue)

        self.create_widgets()

    # --- UI event pump -----------------------------------------------------

    def _poll_ui_queue(self):
        try:
            while True:
                self._apply_ui_event(self.ui_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll_ui_queue)

    def _apply_ui_event(self, event):
        kind = event[0]
        if kind == "checked":
            _, title, resolutions = event
            self.label_video_title.configure(text=title)
            self.combo_video_res.configure(values=resolutions)
            if resolutions:
                self.combo_video_res.set(resolutions[0])
            self.lbl_status.configure(text="Formats loaded - pick options and press DOWNLOAD.")
        elif kind == "check_error":
            messagebox.showerror("Error", event[1])
        elif kind == "check_done":
            self.btn_check.configure(state="normal", text="Check")
        elif kind == "progress":
            _, fraction, percent, speed = event
            self.progress_bar.set(fraction)
            self.lbl_status.configure(text="Downloading: %s | Speed: %s" % (percent, speed))
        elif kind == "postprocess":
            self.progress_bar.set(1)
            self.lbl_status.configure(text="Processing (merge / conversion)...")
        elif kind == "download_success":
            messagebox.showinfo("Success", "Download completed!")
            self.lbl_status.configure(text="Ready")
        elif kind == "download_error":
            messagebox.showerror("Error", event[1])
        elif kind == "download_done":
            self.btn_download.configure(state="normal", text="DOWNLOAD")

    # --- Widgets ------------------------------------------------------------

    def create_widgets(self):
        # Title and logo (logo.png next to the script; text fallback)
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            img = Image.open(os.path.join(script_dir, "logo.png"))
            ratio = 250 / img.width
            logo_img = ctk.CTkImage(light_image=img, dark_image=img,
                                    size=(250, int(img.height * ratio)))
            self.label_title = ctk.CTkLabel(self, image=logo_img, text="")
        except Exception:
            self.label_title = ctk.CTkLabel(self, text=APP_NAME, font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=15)
        # Brand site opens on logo click
        self.label_title.bind("<Button-1>", lambda e: webbrowser.open(BRAND_URL))
        self.label_title.configure(cursor="hand2")

        # --- URL Section ---
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.pack(pady=10, padx=20, fill="x")

        self.entry_url = ctk.CTkEntry(self.url_frame, placeholder_text="Paste YouTube link here...")
        self.entry_url.pack(side="left", padx=10, pady=10, fill="x", expand=True)

        self.btn_check = ctk.CTkButton(self.url_frame, text="Check", command=self.start_check_thread, width=100)
        self.btn_check.pack(side="right", padx=10, pady=10)

        # Video information
        self.label_video_title = ctk.CTkLabel(self, text="", font=("Roboto", 14), text_color="#4ade80")
        self.label_video_title.pack(pady=5)

        # --- Selection Tabs (Tabview) ---
        self.tabview = ctk.CTkTabview(self, width=500, height=200)
        self.tabview.pack(pady=10)

        self.tab_audio = self.tabview.add(AUDIO_TAB)
        self.tab_video = self.tabview.add(VIDEO_TAB)

        # === AUDIO Options ===
        self.lbl_audio_fmt = ctk.CTkLabel(self.tab_audio, text="Format:")
        self.lbl_audio_fmt.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        self.combo_audio_fmt = ctk.CTkComboBox(self.tab_audio, values=["mp3", "flac"])
        self.combo_audio_fmt.grid(row=0, column=1, padx=20, pady=10)

        self.lbl_audio_bit = ctk.CTkLabel(self.tab_audio, text="Quality (Bitrate):")
        self.lbl_audio_bit.grid(row=1, column=0, padx=20, pady=10, sticky="w")
        self.combo_audio_bit = ctk.CTkComboBox(self.tab_audio, values=["192", "256", "320"])
        self.combo_audio_bit.set("320")  # Default
        self.combo_audio_bit.grid(row=1, column=1, padx=20, pady=10)

        # === VIDEO Options ===
        self.lbl_video_fmt = ctk.CTkLabel(self.tab_video, text="Format:")
        self.lbl_video_fmt.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        self.combo_video_fmt = ctk.CTkComboBox(self.tab_video, values=["mp4", "avi"])
        self.combo_video_fmt.grid(row=0, column=1, padx=20, pady=10)

        self.lbl_video_res = ctk.CTkLabel(self.tab_video, text="Resolution:")
        self.lbl_video_res.grid(row=1, column=0, padx=20, pady=10, sticky="w")
        self.combo_video_res = ctk.CTkComboBox(self.tab_video, values=["Check link first"])
        self.combo_video_res.grid(row=1, column=1, padx=20, pady=10)

        # --- Folder Selection ---
        self.frame_path = ctk.CTkFrame(self)
        self.frame_path.pack(pady=20, padx=20, fill="x")

        self.btn_path = ctk.CTkButton(self.frame_path, text="Select Save Folder", command=self.select_folder, fg_color="gray")
        self.btn_path.pack(side="left", padx=10, pady=10)

        self.lbl_path = ctk.CTkLabel(self.frame_path, text="Save to: %s" % self.save_path, font=("Arial", 10))
        self.lbl_path.pack(side="left", padx=10)

        # --- Progress Bar and Download Button ---
        self.progress_bar = ctk.CTkProgressBar(self, width=400)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)

        self.lbl_status = ctk.CTkLabel(self, text="Ready")
        self.lbl_status.pack(pady=5)

        self.btn_download = ctk.CTkButton(self, text="DOWNLOAD", command=self.start_download_thread,
                                          width=200, height=50, font=("Roboto", 16, "bold"), fg_color="#dc2626", hover_color="#b91c1c")
        self.btn_download.pack(pady=20)

    # --- Application logic ----------------------------------------------------

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_path = folder
            self.lbl_path.configure(text="Save to: %s" % self.save_path)

    def start_check_thread(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Error", "Paste a link first!")
            return
        self.btn_check.configure(state="disabled", text="Searching...")
        threading.Thread(target=self._check_worker, args=(url,), daemon=True).start()

    def _check_worker(self, url):
        """Worker thread: extract info, push results through ui_queue."""
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            resolutions = pick_resolutions(info.get("formats", []))
            self.checked_url = url
            self.ui_queue.put(("checked", display_title(info.get("title")), resolutions))
        except Exception as e:
            self.ui_queue.put(("check_error", "Failed to fetch information:\n%s" % e))
        finally:
            self.ui_queue.put(("check_done",))

    def start_download_thread(self):
        if not self.checked_url:
            messagebox.showwarning("Warning", "Click 'Check' first to load video info.")
            return

        # Read all widget state on the main thread BEFORE spawning the worker.
        mode = self.tabview.get()
        audio_fmt = bitrate = video_fmt = resolution = None
        if mode == AUDIO_TAB:
            audio_fmt = self.combo_audio_fmt.get()
            bitrate = self.combo_audio_bit.get()
        else:
            video_fmt = self.combo_video_fmt.get()
            resolution = self.combo_video_res.get()
            if not resolution.endswith("p"):
                messagebox.showwarning("Warning", "No video formats for this link - use the Audio tab.")
                return

        self.btn_download.configure(state="disabled", text="Downloading...")
        self.progress_bar.set(0)
        threading.Thread(
            target=self._download_worker,
            args=(self.checked_url, mode, audio_fmt, bitrate, video_fmt, resolution, self.save_path),
            daemon=True,
        ).start()

    def _progress_hook(self, d):
        """Runs on the worker thread: byte-based progress, throttled to ~250 ms."""
        if d["status"] == "downloading":
            now = time.monotonic()
            if now - self._last_progress_push < 0.25:
                return
            self._last_progress_push = now
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            fraction = min(1.0, done / total) if total else 0.0
            speed = d.get("speed")
            self.ui_queue.put(("progress", fraction, "%.1f%%" % (fraction * 100),
                               human_size(speed) + "/s" if speed else "--"))
        elif d["status"] == "finished":
            self.ui_queue.put(("postprocess",))

    def _download_worker(self, url, mode, audio_fmt, bitrate, video_fmt, resolution, save_path):
        """Worker thread: download, push result through ui_queue."""
        try:
            opts = build_ydl_opts(save_path, mode, audio_fmt=audio_fmt, bitrate=bitrate,
                                  video_fmt=video_fmt, resolution=resolution,
                                  progress_hook=self._progress_hook)
            self._last_progress_push = 0.0
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.ui_queue.put(("download_success",))
        except Exception as e:
            self.ui_queue.put(("download_error", "An error occurred:\n%s" % e))
        finally:
            self.ui_queue.put(("download_done",))


if __name__ == "__main__":
    app = YouTubeDownloaderApp()
    app.mainloop()