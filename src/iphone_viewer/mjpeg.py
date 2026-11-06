"""Reader for multipart MJPEG streams such as WebDriverAgent's MJPEG server."""
from collections.abc import Iterator
from typing import BinaryIO


def iter_frames(stream: BinaryIO) -> Iterator[bytes]:
    """Yield the JPEG frames of a multipart/x-mixed-replace stream until it ends.

    Each part has to carry a Content-Length header (WebDriverAgent always sends one); boundary lines and other
    headers are skipped. A frame cut off by the end of the stream is dropped.
    """
    length = None
    while line := stream.readline():
        line = line.strip()
        if line:
            name, sep, value = line.partition(b":")
            if sep and name.strip().lower() == b"content-length":
                length = int(value)
            continue
        # a blank line ends the headers of a part; without a length it is just the gap before the next boundary
        if length is None:
            continue
        frame = stream.read(length)
        if len(frame) < length:
            return
        yield frame
        length = None
