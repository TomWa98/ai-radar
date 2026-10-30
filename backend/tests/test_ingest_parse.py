from datetime import UTC, datetime

import pytest

from ai_radar.ingest.parse import MAX_TITLE_LENGTH, FeedParseError, parse_feed

COLLECTED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Example News</title>
    <link>https://news.example.com/</link>
    <item>
      <title>First   headline</title>
      <link>https://news.example.com/articles/1?utm_source=rss</link>
      <description>Short &lt;b&gt;summary&lt;/b&gt;.</description>
      <pubDate>Thu, 29 Oct 2026 08:15:00 +0100</pubDate>
    </item>
    <item>
      <title>Second headline</title>
      <link>/articles/2</link>
    </item>
  </channel>
</rss>
"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <id>urn:example:feed</id>
  <updated>2026-10-30T10:00:00Z</updated>
  <entry>
    <title>Atom entry</title>
    <link rel="alternate" href="https://atom.example.org/posts/7"/>
    <id>urn:example:7</id>
    <updated>2026-10-30T09:00:00Z</updated>
    <published>2026-10-28T07:30:00Z</published>
    <summary>Entry summary</summary>
  </entry>
</feed>
"""


def test_parse_rss() -> None:
    feed = parse_feed(RSS, "https://news.example.com/feed.xml", COLLECTED_AT)

    assert feed.source == "Example News"
    assert feed.skipped == 0
    first, second = feed.articles
    assert first.title == "First headline"
    assert first.url == "https://news.example.com/articles/1?utm_source=rss"
    assert first.source == "Example News"
    assert first.published_at == datetime(2026, 10, 29, 7, 15, tzinfo=UTC)
    assert first.collected_at == COLLECTED_AT
    assert first.content is not None and "summary" in first.content
    # Relative links are resolved against the feed URL.
    assert second.url == "https://news.example.com/articles/2"


def test_parse_atom() -> None:
    feed = parse_feed(ATOM, "https://atom.example.org/feed", COLLECTED_AT)

    assert feed.source == "Example Atom"
    (entry,) = feed.articles
    assert entry.title == "Atom entry"
    assert entry.url == "https://atom.example.org/posts/7"
    assert entry.published_at == datetime(2026, 10, 28, 7, 30, tzinfo=UTC)
    assert entry.content == "Entry summary"


def test_missing_optional_fields() -> None:
    content = b"""<rss version="2.0"><channel>
      <item><link>https://example.com/no-title</link></item>
    </channel></rss>"""
    feed = parse_feed(content, "https://example.com/feed", COLLECTED_AT)

    # Without a channel title the feed host is used as source.
    assert feed.source == "example.com"
    (article,) = feed.articles
    assert article.title == "https://example.com/no-title"
    assert article.published_at is None
    assert article.content is None


def test_updated_date_is_used_without_published_date() -> None:
    content = ATOM.replace(b"<published>2026-10-28T07:30:00Z</published>", b"")
    (entry,) = parse_feed(
        content, "https://atom.example.org/feed", COLLECTED_AT
    ).articles
    assert entry.published_at == datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def test_unparseable_date_is_none() -> None:
    content = RSS.replace(b"Thu, 29 Oct 2026 08:15:00 +0100", b"sometime soon")
    first = parse_feed(
        content, "https://news.example.com/feed.xml", COLLECTED_AT
    ).articles[0]
    assert first.published_at is None


@pytest.mark.parametrize(
    "link",
    [
        b"",
        b"javascript:alert(1)",
        b"ftp://example.com/file",
        b"https://u:p@example.com/x",
    ],
)
def test_entries_without_usable_link_are_skipped(link: bytes) -> None:
    content = (
        b"""<rss version="2.0"><channel><title>T</title>
      <item><title>Bad</title><link>%s</link></item>
      <item><title>Good</title><link>https://example.com/good</link></item>
    </channel></rss>"""
        % link
    )
    feed = parse_feed(content, "https://example.com/feed", COLLECTED_AT)

    assert [article.title for article in feed.articles] == ["Good"]
    assert feed.skipped == 1


def test_long_title_is_truncated() -> None:
    content = b"""<rss version="2.0"><channel><title>T</title>
      <item><title>%s</title><link>https://example.com/a</link></item>
    </channel></rss>""" % (b"x" * (MAX_TITLE_LENGTH + 50))
    (article,) = parse_feed(content, "https://example.com/feed", COLLECTED_AT).articles
    assert len(article.title) == MAX_TITLE_LENGTH


def test_script_in_summary_is_sanitized() -> None:
    content = b"""<rss version="2.0"><channel><title>T</title>
      <item><title>A</title><link>https://example.com/a</link>
      <description>&lt;p&gt;Hi&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;</description></item>
    </channel></rss>"""
    (article,) = parse_feed(content, "https://example.com/feed", COLLECTED_AT).articles
    assert article.content is not None
    assert "<script" not in article.content


def test_empty_feed_is_valid() -> None:
    content = b'<rss version="2.0"><channel><title>Empty</title></channel></rss>'
    feed = parse_feed(content, "https://example.com/feed", COLLECTED_AT)
    assert feed.articles == []


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"<html><body>Not a feed</body></html>",
        b"<rss version='2.0'><channel>",
        b"\x00\xff",
    ],
)
def test_invalid_documents_raise(content: bytes) -> None:
    with pytest.raises(FeedParseError):
        parse_feed(content, "https://example.com/feed", COLLECTED_AT)


def test_content_is_never_treated_as_file_name(tmp_path) -> None:
    local = tmp_path / "local.xml"
    local.write_bytes(RSS)
    with pytest.raises(FeedParseError):
        parse_feed(str(local).encode(), "https://example.com/feed", COLLECTED_AT)
