from renamer import build_filename, strip_actress_suffix, sanitize


def test_build_single():
    r = build_filename("DDT-435", ["吉田花"], "解禁アナル・FUCK", ".mp4")
    assert r == "DDT-435 吉田花 - 解禁アナル・FUCK 吉田花.mp4"


def test_build_multi_actress():
    r = build_filename("DDT-406", ["美咲結衣", "結城みさ"], "義母・フィスト奴隷", ".mp4")
    assert r == "DDT-406 美咲結衣 結城みさ - 義母・フィスト奴隷 美咲結衣 結城みさ.mp4"


def test_build_with_part():
    r = build_filename("DDT-153", ["橘未稀"], "拘束椅子トランス", ".mp4", part=2)
    assert r == "DDT-153 橘未稀 - 拘束椅子トランス 橘未稀(2).mp4"


def test_build_unknown_actress():
    r = build_filename("DDT-518", [], "TOHJIRO全集", ".mp4")
    assert r == "DDT-518 未知女優 - TOHJIRO全集 未知女優.mp4"


def test_strip_suffix():
    assert strip_actress_suffix("解禁アナル・FUCK 吉田花", ["吉田花"]) == "解禁アナル・FUCK"


def test_strip_no_match():
    assert strip_actress_suffix("TOHJIRO全集 Vol.15", ["吉田花"]) == "TOHJIRO全集 Vol.15"


def test_sanitize():
    assert sanitize('test<>:"/\\|?*file') == "testfile"
