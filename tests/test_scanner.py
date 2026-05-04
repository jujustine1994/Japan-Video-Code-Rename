from scanner import extract_code, group_by_code


def test_standard_code():
    assert extract_code("DDT-435 吉田花.mp4") == "DDT-435"


def test_lowercase_code():
    assert extract_code("ddt435.mp4") == "DDT-435"


def test_spaced_code():
    assert extract_code("ddt 435 something.mp4") == "DDT-435"


def test_no_hyphen():
    assert extract_code("ddt428 MR.srt") == "DDT-428"


def test_no_code():
    assert extract_code("1002.mp4") is None


def test_gsc_no_digits():
    assert extract_code("GSC.mp4") is None


def test_multipart_grouping():
    files = ["DDT-153 -1.mp4", "DDT-153 2.mp4", "DDT-435.mp4"]
    groups = group_by_code(files)
    assert groups["DDT-153"] == ["DDT-153 -1.mp4", "DDT-153 2.mp4"]
    assert groups["DDT-435"] == ["DDT-435.mp4"]
