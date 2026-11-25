from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from project import format_timestamp, extract_attachment_urls, format_sender_header

def test_format_timestamp():
    dt_utc = datetime(2026, 11, 23, 12, 14, 5, tzinfo=timezone.utc)
    assert format_timestamp(dt_utc, "%d/%b/%Y %H:%M:%S", "Europe/Rome") == ("23/Nov/2026 13:14:05")
    assert format_timestamp(dt_utc, "%d %b %Y - %H:%M", "Europe/Rome") == ("23 Nov 2026 - 13:14")

def test_extract_attachment_urls():
    assert extract_attachment_urls([]) == []
    assert extract_attachment_urls(None) == []

    attachments = [SimpleNamespace(url="https://example.com/image1.png"), SimpleNamespace(url="https://example.com/image2.jpg")]
    assert extract_attachment_urls(attachments) == ["https://example.com/image1.png", "https://example.com/image2.jpg"]

def test_format_sender_header():
    assert (format_sender_header(author_name="Alice", is_bot=False, mode="-1", channel_id=12345, bot_name="SugarBOT") == "Alice] --> [SugarBOT <BOT>")
    assert (format_sender_header(author_name="SugarBOT", is_bot=True, mode="-2", channel_id=12345, bot_name="SugarBOT") == "SugarBOT <BOT>] --> [DM User (ChannelID: 12345)")
    with pytest.raises(ValueError):
        format_sender_header("Alice", False, "invalid")