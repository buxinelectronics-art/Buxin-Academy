"""Parse video links from community post text."""
import re

_YOUTUBE_PATTERNS = (
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([\w-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/live/([\w-]{11})",
    r"(?:https?://)?youtu\.be/([\w-]{11})",
)


def extract_youtube_id(text: str | None) -> str | None:
    if not text:
        return None
    for pattern in _YOUTUBE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
