from __future__ import annotations

import argparse
import signal
import tkinter as tk
import time
from pathlib import Path
from typing import Any

from ffpyplayer.player import MediaPlayer
from PIL import Image, ImageTk


class MiniPlayerApp:
    def __init__(
        self,
        video_path: Path,
        log_path: Path,
        *,
        width: int,
        height: int,
        x: int,
        y: int,
        title: str,
    ) -> None:
        self.video_path = video_path
        self.log_path = log_path
        self.width = width
        self.height = height
        self.video_width = width
        self.video_height = height
        self.media_player: Any | None = None
        self.photo_image: ImageTk.PhotoImage | None = None
        self.closed = False
        self.first_frame_seen = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="#000000")
        self.root.resizable(False, False)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.canvas = tk.Canvas(
            self.root,
            width=self.video_width,
            height=self.video_height,
            bg="#000000",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas_image_id = self.canvas.create_image(
            self.video_width // 2,
            self.video_height // 2,
            anchor="center",
        )
        self.log("player-subprocess:init")

    def log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self.log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"[{timestamp}] {message}\n")
        except OSError:
            pass

    def _open_media_player(self) -> None:
        self._close_media_player()
        self.log(f"player-subprocess:open media path={self.video_path.name}")
        self.media_player = MediaPlayer(
            str(self.video_path),
            ff_opts={
                "paused": False,
                "sync": "audio",
                "out_fmt": "rgb24",
                "volume": 1.0,
            },
            loglevel="quiet",
        )

    def _close_media_player(self) -> None:
        if self.media_player is None:
            return
        try:
            self.media_player.close_player()
        except Exception:
            pass
        self.media_player = None
        self.log("player-subprocess:media closed")

    def _display_frame(self, frame_image: Any) -> None:
        width, height = frame_image.get_size()
        buffer = frame_image.to_bytearray()[0]
        image = Image.frombytes("RGB", (width, height), buffer)
        scale = min(self.video_width / width, self.video_height / height)
        target_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        if target_size != (width, height):
            image = image.resize(target_size, Image.Resampling.LANCZOS)

        composed = Image.new("RGB", (self.video_width, self.video_height), "#000000")
        offset_x = (self.video_width - image.size[0]) // 2
        offset_y = (self.video_height - image.size[1]) // 2
        composed.paste(image, (offset_x, offset_y))
        self.photo_image = ImageTk.PhotoImage(composed)
        self.canvas.itemconfig(self.canvas_image_id, image=self.photo_image)

    def _tick(self) -> None:
        if self.closed:
            return
        if self.media_player is not None:
            frame, value = self.media_player.get_frame()
            if value == "eof":
                self.log("player-subprocess:eof")
                self.close()
                return
            elif frame is not None:
                frame_image, _pts = frame
                if not self.first_frame_seen:
                    self.first_frame_seen = True
                    self.log("player-subprocess:first frame displayed")
                self._display_frame(frame_image)
        self.root.after(15, self._tick)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.log("player-subprocess:close")
        self._close_media_player()
        self.root.after(0, self.root.destroy)

    def run(self) -> int:
        self._open_media_player()
        self.root.after(15, self._tick)
        self.root.mainloop()
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--title", default="Keep Focus!")
    parser.add_argument("--log", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = MiniPlayerApp(
        Path(args.video),
        Path(args.log),
        width=args.width,
        height=args.height,
        x=args.x,
        y=args.y,
        title=args.title,
    )

    def handle_signal(_signum: int, _frame: Any) -> None:
        app.close()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        return app.run()
    except Exception as exc:
        app.log(f"player-subprocess:error {exc!r}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
