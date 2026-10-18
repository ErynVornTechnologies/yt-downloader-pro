"""Unit + end-to-end test for YT Downloader Pro v2.0.

Unit part: pure helpers (resolution picker, title truncation, yt-dlp option
builder, human speed format) - no network, no GUI.

E2E part: the real GUI inside the real mainloop(). Messageboxes are
monkeypatched to record instead of block. Steps are scheduled with
app.after() so everything runs on the genuine Tk loop, exercising the
production queue-based thread communication. Downloads a real YouTube
Short twice (video 720p ~12 MB, then MP3 ~3 MB).

Run with:  py -3.12 test_app_flow.py
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import downloader
from tkinter import messagebox

# Live E2E link: "Me at the zoo" (19 s, public, permanent). Swap freely for
# any stable link; the assertions below are size-agnostic. NOTE: hammering
# one video with repeated extractions makes YouTube throw
# "Sign in to confirm you're not a bot" for that video+IP (rate limit).
URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

failures = []


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


# --- 1) Unit tests: pure helpers -------------------------------------------

fmts_full = ([{"vcodec": "avc1", "width": w, "height": h}
              for (w, h) in ((2560, 1440), (1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240), (256, 144))]
             + [{"vcodec": "none"},                    # audio-only stream
                {"vcodec": "images", "width": 101, "height": 180},  # storyboard frame
                {"height": 360}])                      # no vcodec/width keys at all
check(downloader.pick_resolutions(fmts_full) == ["1440p", "1080p", "720p"],
      "unit: picker keeps top three >=720p from a full format list")
fmts_vertical = ([{"vcodec": "avc1", "width": w, "height": h}
                  for (w, h) in ((1080, 1920), (720, 1280), (480, 854), (360, 640), (240, 426), (144, 256))])
check(downloader.pick_resolutions(fmts_vertical) == ["1080p", "720p"],
      "unit: vertical Short labelled by short side (720x1280 -> 720p, not 1280p)")
check(downloader.pick_resolutions([{"vcodec": "avc1", "height": h} for h in (480, 360, 240)])
      == ["480p", "360p", "240p"],
      "unit: height-only formats fall back to height")
check(downloader.pick_resolutions([]) == [], "unit: picker handles empty format list")

check(downloader.display_title("short title") == "short title", "unit: short title untouched")
long_title = "x" * 65
check(downloader.display_title(long_title) == "x" * 60 + "...", "unit: long title truncated to 60 + ...")
check(downloader.display_title(None) == "", "unit: None title handled")

opts = downloader.build_ydl_opts(r"T:\out", downloader.AUDIO_TAB, audio_fmt="mp3", bitrate="320")
check(opts["format"] == "bestaudio/best", "unit: audio opts use bestaudio/best")
check(opts["postprocessors"][0]["preferredcodec"] == "mp3"
      and opts["postprocessors"][0]["preferredquality"] == "320",
      "unit: audio opts carry codec mp3 + bitrate 320")
opts = downloader.build_ydl_opts(r"T:\out", downloader.VIDEO_TAB, video_fmt="mp4", resolution="720p")
check(opts["format"] == "bestvideo+bestaudio/best", "unit: video selector orientation-proof")
check(opts["format_sort"] == ["res:720", "vcodec:h264"],
      "unit: video sorted by short side with h264 tie-break")
check(opts["merge_output_format"] == "mp4", "unit: video merge target mp4")
check("postprocessors" not in opts, "unit: no convertor for mp4")
opts = downloader.build_ydl_opts(r"T:\out", downloader.VIDEO_TAB, video_fmt="avi", resolution="1080p")
check(opts["format_sort"] == ["res:1080", "vcodec:h264"], "unit: 1080p carries the right sort cap")
check(opts["postprocessors"][0]["preferedformat"] == "avi",
      "unit: avi adds FFmpegVideoConvertor (yt-dlp 'preferedformat' spelling)")
ffmpeg_expected = downloader.FFMPEG_DIR if os.path.exists(
    os.path.join(downloader.FFMPEG_DIR, "ffmpeg.exe")) else None
check(opts.get("ffmpeg_location", None) == ffmpeg_expected,
      "unit: ffmpeg_location set iff C:\\ffmpeg\\bin\\ffmpeg.exe exists")
check(downloader.build_ydl_opts(r"T:\out", downloader.VIDEO_TAB, resolution="720p")
      .get("outtmpl", "").startswith(os.path.join("T:\\out", "%(title)s")),
      "unit: outtmpl lands in the save folder")

check(downloader.human_size(1536) == "1.5 KiB", "unit: human_size 1536 -> 1.5 KiB")
check(downloader.human_size(None) == "--", "unit: human_size None -> --")

# --- 2) E2E: real GUI in the real mainloop ---------------------------------

dialogs = []
for name in ("showinfo", "showerror", "showwarning"):
    def rec(title, msg, _n=name):
        dialogs.append((_n, title, str(msg)))
        print("    [dialog] %s: %s :: %s" % (_n, title, str(msg)[:80]))
    setattr(messagebox, name, staticmethod(rec))


def success_count():
    return sum(1 for d in dialogs if d[0] == "showinfo" and d[1] == "Success")


app = downloader.YouTubeDownloaderApp()
tmp = tempfile.mkdtemp(prefix="ytdlp_pro_test_")
state = {"t0": time.time(), "max_progress": 0.0}


def fail_stop(msg):
    print("FAIL " + msg)
    failures.append(msg)
    finish()


def finish():
    print("")
    print("TMP: %s" % tmp)
    if failures:
        print("RESULT: %d FAILURE(S): %s" % (len(failures), "; ".join(failures)))
    else:
        print("RESULT: ALL CHECKS PASSED")
        shutil.rmtree(tmp, ignore_errors=True)
    app.destroy()


def step_empty_url():
    # 1) empty entry must warn, not start a worker
    app.start_check_thread()
    app.after(300, step_real_url)


def step_real_url():
    check(any(d[0] == "showwarning" and d[1] == "Error" for d in dialogs),
          "e2e: empty link rejected with a warning")
    app.entry_url.insert(0, URL)
    app.start_check_thread()
    state["t0"] = time.time()
    app.after(250, wait_for_check)


def wait_for_check():
    # Button back to "Check" means the check_done event was applied, and the
    # queue is FIFO, so the "checked" event (combo values, title) is applied
    # too - no race between the worker's attribute write and the UI poller.
    if app.checked_url is not None and str(app.btn_check.cget("text")) == "Check":
        after_check()
        return
    if any(d[0] == "showerror" for d in dialogs):
        fail_stop("Check ended with an error dialog")
        return
    if time.time() - state["t0"] > 90:
        fail_stop("Check timed out after 90s")
        return
    app.after(250, wait_for_check)


def after_check():
    values = list(app.combo_video_res.cget("values"))
    heights = [int(v.rstrip("p")) for v in values if v.endswith("p")]
    check(len(values) >= 1 and len(values) <= 3 and heights == sorted(heights, reverse=True),
          "e2e: picker offers up to 3 resolutions, highest first (%s)" % values)
    title = app.label_video_title.cget("text")
    check(len(title) > 0, "e2e: video title shown (%r)" % title[:40])
    check(str(app.btn_check.cget("text")) == "Check", "e2e: Check button re-enabled")

    # 2) video download at the highest offered resolution, into the temp folder
    app.tabview.set(downloader.VIDEO_TAB)
    resolution = values[0]
    print("     selected quality: %s" % resolution)
    app.save_path = tmp
    app.start_download_thread()
    state["t0"] = time.time()
    app.after(250, wait_for_video)


def wait_for_video():
    state["max_progress"] = max(state["max_progress"], app.progress_bar.get())
    if success_count() >= 1:
        after_video()
        return
    if any(d[0] == "showerror" for d in dialogs):
        fail_stop("Video download failed with an error dialog")
        return
    if time.time() - state["t0"] > 300:
        fail_stop("Video download timed out after 300s")
        return
    app.after(250, wait_for_video)


def after_video():
    mp4s = [f for f in os.listdir(tmp) if f.endswith(".mp4")]
    check(len(mp4s) == 1, "e2e: one mp4 produced (%s)" % mp4s)
    if mp4s:
        size = os.path.getsize(os.path.join(tmp, mp4s[0]))
        check(size > 300 * 1024, "e2e: mp4 size plausible (%.1f MB)" % (size / 1e6))
        print("     mp4: %s (%.1f MB)" % (mp4s[0], size / 1e6))
    check(state["max_progress"] > 0.05,
          "e2e: progress bar moved during download (max %.2f)" % state["max_progress"])
    check(str(app.btn_download.cget("text")) == "DOWNLOAD", "e2e: DOWNLOAD button re-enabled")
    check(str(app.lbl_status.cget("text")) == "Ready", "e2e: status back to Ready")

    # 3) audio download (mp3 320) of the same checked link
    app.tabview.set(downloader.AUDIO_TAB)
    app.start_download_thread()
    state["t0"] = time.time()
    app.after(250, wait_for_audio)


def wait_for_audio():
    if success_count() >= 2:
        after_audio()
        return
    if any(d[0] == "showerror" for d in dialogs):
        fail_stop("Audio download failed with an error dialog")
        return
    if time.time() - state["t0"] > 300:
        fail_stop("Audio download timed out after 300s")
        return
    app.after(250, wait_for_audio)


def after_audio():
    mp3s = [f for f in os.listdir(tmp) if f.endswith(".mp3")]
    check(len(mp3s) == 1, "e2e: one mp3 produced (%s)" % mp3s)
    if mp3s:
        size = os.path.getsize(os.path.join(tmp, mp3s[0]))
        check(size > 100 * 1024, "e2e: mp3 size plausible (%.1f MB)" % (size / 1e6))
        print("     mp3: %s (%.1f MB)" % (mp3s[0], size / 1e6))
    check(str(app.btn_download.cget("text")) == "DOWNLOAD", "e2e: DOWNLOAD re-enabled after audio")
    finish()


app.after(400, step_empty_url)
try:
    app.mainloop()
except Exception as e:  # pragma: no cover - harness safety net
    print("FAIL mainloop crashed: %r" % e)
    failures.append("mainloop crashed: %r" % e)
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(1 if failures else 0)