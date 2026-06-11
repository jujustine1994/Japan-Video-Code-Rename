import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from javlibrary_fetcher import JavlibraryFetcher


def _make_html(code: str, title_in_h3: str, actresses: list[str]) -> str:
    stars = "".join(
        f'<span class="star"><a href="/ja/vl_star.php?s={i}">{name}</a></span>'
        for i, name in enumerate(actresses, 1)
    )
    return (
        f"<html><body>"
        f'<div id="video_id"><span class="text">{code}</span></div>'
        f'<h3 class="post-title">{title_in_h3}</h3>'
        f"{stars}"
        f"</body></html>"
    )


def test_parse_single_actress():
    html = _make_html("SSIS-001", "SSIS-001 一ヶ月間の禁欲の果てに 葵つかさ", ["葵つかさ"])
    result = JavlibraryFetcher._parse_video(html, "SSIS-001")
    assert result is not None
    assert result["title"] == "一ヶ月間の禁欲の果てに"
    assert result["actresses"] == ["葵つかさ"]


def test_parse_multi_actress():
    html = _make_html(
        "ABW-001",
        "ABW-001 タイトル本文 葵つかさ 乙白さやか",
        ["葵つかさ", "乙白さやか"],
    )
    result = JavlibraryFetcher._parse_video(html, "ABW-001")
    assert result is not None
    assert result["title"] == "タイトル本文"
    assert result["actresses"] == ["葵つかさ", "乙白さやか"]


def test_parse_no_title():
    html = "<html><body><div id='video_id'><span class='text'>FAKE-999</span></div></body></html>"
    result = JavlibraryFetcher._parse_video(html, "FAKE-999")
    assert result is None


def test_parse_code_prefix_stripped():
    html = _make_html("MIDE-001", "MIDE-001 本編タイトル 天使もえ", ["天使もえ"])
    result = JavlibraryFetcher._parse_video(html, "MIDE-001")
    assert result is not None
    assert result["title"] == "本編タイトル"
    assert not result["title"].startswith("MIDE-001")
