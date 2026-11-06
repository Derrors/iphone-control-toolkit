import argparse
import sys

from .wda import WDAError

MISSING_GUI = """The viewer needs Tk and Pillow's Tk support ({error}). Install them, for example:
  Debian / Ubuntu:  sudo apt install python3-tk python3-pil.imagetk
  Arch / Manjaro:   sudo pacman -S tk python-pillow
  Fedora:           sudo dnf install python3-tkinter python3-pillow-tk"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="iphonectl viewer",
                                     description="Live view of the iPhone screen, controlled with mouse and keyboard.")
    parser.add_argument("--wda", default="http://127.0.0.1:8100", help="WebDriverAgent URL")
    parser.add_argument("--mjpeg", default="http://127.0.0.1:9100", help="MJPEG stream URL")
    parser.add_argument("--fps", type=int, default=30, help="stream frame rate (default: 30)")
    parser.add_argument("--scale", type=int, default=50,
                        help="stream resolution in percent of the native screen (default: 50)")
    parser.add_argument("--quality", type=int, default=50, help="JPEG quality 1-100 (default: 50)")
    args = parser.parse_args(argv)

    try:
        from .app import run
    except ImportError as e:  # tkinter or PIL.ImageTk missing
        sys.exit(MISSING_GUI.format(error=e))
    try:
        run(args.wda, args.mjpeg, args.fps, args.scale, args.quality)
    except WDAError as e:
        sys.exit(f"{e}\nIs the container running and WebDriverAgent ready? Check with: iphonectl doctor")


if __name__ == "__main__":
    main()
