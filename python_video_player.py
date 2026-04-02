from __future__ import annotations

import argparse
import signal
import sys
import tkinter as tk
from pathlib import Path
from typing import Any

from ffpyplayer.player import MediaPlayer
from PIL import Image, ImageTk


class MiniPlayerApp:
    def __init__(
        self,
        video_path: Path,
        *,
        width: int,
        height: int,
        x: int,
        y: int,
        title: str,
    ) -> None:
        self.video_path = video_path
        self.width = width
        self.height = height
        self.video_width = width - 12
        self.video_height = height - 46
        self.media_player: Any | None = None
        self.photo_image: ImageTk.PhotoImage | None = None
        self.closed = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="#0b0f16")
        self.root.resizable(False, False)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        shell = tk.Frame(
            self.root,
            bg="#0f1624",
            highlightthickness=1,
            highlightbackground="#2f3a4c",
        )
        shell.pack(fill="both", expand=True, padx=6, pady=6)

        header = tk.Frame(shell, bg="#111c2d", height=34)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Keep Focus!",
            bg="#111c2d",
            fg="#f4f7fb",
            font=("Avenir Next", 11, "bold"),
            padx=10,
        ).pack(side="left")
        self.status_var = tk.StringVar(value="Playing")
        tk.Label(
            header,
            textvariable=self.status_var,
            bg="#111c2d",
            fg="#ffb59e",
            font=("Avenir Next", 10, "bold"),
            padx=10,
        ).pack(side="right")

        video_frame = tk.Frame(shell, bg="#000000")
        video_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            video_frame,
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

    def _open_media_player(self) -> None:
        self._close_media_player()
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
                self._open_media_player()
            elif frame is not None:
                frame_image, _pts = frame
                self._display_frame(frame_image)
        self.root.after(15, self._tick)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.status_var.set("Stopped")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = MiniPlayerApp(
        Path(args.video),
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
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
