"""Tk window: shows the live stream and turns mouse and keyboard input into touches on the phone."""
import http.client
import io
import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable

from PIL import Image, ImageTk

from .geometry import LongPress, Swipe, Tap, Viewport, classify
from .mjpeg import iter_frames
from .wda import WDAClient, WDAError, open_direct

SCROLL_POINTS = 120
RECONNECT_SECONDS = 2
FRAME_POLL_MS = 15

HELP = ("Click: tap · hold: long press · drag: swipe · wheel: scroll · keys: type · Esc / right click: Home. "
        "iOS ignores the swipe up from the bottom edge when it does not come from a finger, use the buttons.")


class FrameReader(threading.Thread):
    """Reads the MJPEG stream and keeps only the newest frame (or the last connection error), reconnecting."""

    def __init__(self, url: str):
        super().__init__(daemon=True)
        self.url = url
        self.latest: queue.Queue[bytes | Exception] = queue.Queue(maxsize=1)
        self.stopped = threading.Event()

    def _publish(self, item: bytes | Exception) -> None:
        try:
            self.latest.get_nowait()
        except queue.Empty:
            pass
        self.latest.put_nowait(item)

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                with open_direct(self.url, timeout=10) as stream:
                    for frame in iter_frames(stream):
                        if self.stopped.is_set():
                            return
                        self._publish(frame)
            except (OSError, http.client.HTTPException, ValueError) as e:
                self._publish(e)
            self.stopped.wait(RECONNECT_SECONDS)


class ActionWorker(threading.Thread):
    """Runs phone actions one after another off the UI thread, so typed text keeps its order."""

    def __init__(self, on_error: Callable[[Exception], None]):
        super().__init__(daemon=True)
        self.jobs: queue.Queue[Callable[[], None]] = queue.Queue()
        self.on_error = on_error

    def submit(self, job: Callable[[], None]) -> None:
        self.jobs.put(job)

    def run(self) -> None:
        while True:
            job = self.jobs.get()
            try:
                job()
            except Exception as e:  # one failed action must not end the thread, or all further input is lost
                self.on_error(e)


class Viewer:
    def __init__(self, client: WDAClient, mjpeg_url: str):
        self.client = client
        self.screen_w, self.screen_h = client.screen_size()

        self.root = tk.Tk()
        self.root.title("iPhone")
        self.root.configure(bg="#111")
        self.root.minsize(180, 300)

        bar = tk.Frame(self.root, bg="#111")
        bar.pack(side="bottom", fill="x")
        button = {"bg": "#2a2a2a", "fg": "#eee", "activebackground": "#444", "activeforeground": "#fff",
                  "relief": "flat", "bd": 0, "highlightthickness": 0, "padx": 10, "pady": 4}
        tk.Button(bar, text="⌂ Home", command=self.home, **button).pack(side="left", padx=(6, 3), pady=6)
        tk.Button(bar, text="✕ Close app", command=self.close_app, **button).pack(side="left", padx=3, pady=6)
        # width=1 plus fill: a long message is clipped instead of widening the window, which would move the screen
        self.status = tk.Label(bar, text="connecting…", fg="#888", bg="#111", anchor="w", width=1)
        self.status.pack(side="left", fill="x", expand=True, padx=6)

        start_scale = min((self.root.winfo_screenheight() - 180) / self.screen_h, 1.6)
        self.canvas = tk.Canvas(self.root, width=round(self.screen_w * start_scale),
                                height=round(self.screen_h * start_scale), bg="#000", highlightthickness=0,
                                cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.viewport = Viewport.fit(self.screen_w, self.screen_h, int(self.canvas["width"]),
                                     int(self.canvas["height"]))
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo: ImageTk.PhotoImage | None = None
        self.last_frame: bytes | None = None
        self.press: tuple[tuple[float, float], float] | None = None
        self.frames_shown, self.fps_since = 0, time.monotonic()

        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", lambda e: self.home())
        self.canvas.bind("<Button-4>", lambda e: self.scroll(e, 1))  # X11 wheel up
        self.canvas.bind("<Button-5>", lambda e: self.scroll(e, -1))  # X11 wheel down
        self.canvas.bind("<MouseWheel>", lambda e: self.scroll(e, 1 if e.delta > 0 else -1))
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<Escape>", lambda e: self.home())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.worker = ActionWorker(lambda e: self.root.after(0, self.show_status, f"phone: {e}"))
        self.worker.start()
        self.reader = FrameReader(mjpeg_url)
        self.reader.start()
        self.root.after(FRAME_POLL_MS, self.poll_frames)

    # ---- drawing ----

    def on_resize(self, event: tk.Event) -> None:
        self.viewport = Viewport.fit(self.screen_w, self.screen_h, event.width, event.height)
        self.canvas.coords(self.image_item, self.viewport.x, self.viewport.y)
        if self.last_frame:
            self.draw(self.last_frame)

    def draw(self, jpeg: bytes) -> None:
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        image = image.resize((self.viewport.width, self.viewport.height), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.itemconfig(self.image_item, image=self.photo)

    def poll_frames(self) -> None:
        try:
            self.show_next_frame()
        except Exception as e:  # e.g. a corrupt JPEG: skip it, the next frame replaces it
            self.show_status(f"bad frame: {e}")
        finally:
            self.root.after(FRAME_POLL_MS, self.poll_frames)

    def show_next_frame(self) -> None:
        try:
            item = self.reader.latest.get_nowait()
        except queue.Empty:
            item = None
        if isinstance(item, Exception):
            self.show_status(f"no stream: {item}")
        elif item is not None:
            self.draw(item)
            self.last_frame = item
            self.frames_shown += 1
            elapsed = time.monotonic() - self.fps_since
            if elapsed >= 1:
                self.show_status(f"{self.frames_shown / elapsed:.0f} fps")
                self.frames_shown, self.fps_since = 0, time.monotonic()

    def show_status(self, text: str) -> None:
        self.status.config(text=text)

    # ---- input ----

    def on_press(self, event: tk.Event) -> None:
        self.press = (self.viewport.to_points(event.x, event.y), time.monotonic())

    def on_release(self, event: tk.Event) -> None:
        if self.press is None:
            return
        start, pressed_at = self.press
        self.press = None
        gesture = classify(start, self.viewport.to_points(event.x, event.y), time.monotonic() - pressed_at)
        match gesture:
            case Tap(x, y):
                self.worker.submit(lambda: self.client.tap(x, y))
            case LongPress(x, y, seconds):
                self.worker.submit(lambda: self.client.long_press(x, y, seconds))
            case Swipe(x0, y0, x1, y1, ms):
                self.worker.submit(lambda: self.client.swipe(x0, y0, x1, y1, ms))

    def scroll(self, event: tk.Event, direction: int) -> None:
        x, y = self.viewport.to_points(event.x, event.y)
        y1 = min(max(y + direction * SCROLL_POINTS, 1), self.screen_h - 1)
        self.worker.submit(lambda: self.client.swipe(x, y, x, y1, 150))

    def on_key(self, event: tk.Event) -> None:
        if event.keysym == "BackSpace":
            text = "\b"
        elif event.keysym in ("Return", "KP_Enter"):
            text = "\n"
        elif event.char and event.char.isprintable():
            text = event.char
        else:
            return
        self.worker.submit(lambda: self.client.type_text(text))

    def home(self) -> None:
        self.worker.submit(self.client.home)

    def close_app(self) -> None:
        self.worker.submit(self.client.close_foreground_app)

    def close(self) -> None:
        self.reader.stopped.set()
        self.root.destroy()


def run(wda_url: str, mjpeg_url: str, fps: int, scale_percent: int, quality: int) -> None:
    client = WDAClient(wda_url)
    try:
        client.configure_stream(fps, scale_percent, quality)
    except WDAError as e:
        print(f"warning: could not configure the stream ({e}), using WebDriverAgent's defaults")
    viewer = Viewer(client, mjpeg_url)
    print(HELP)
    viewer.root.mainloop()
