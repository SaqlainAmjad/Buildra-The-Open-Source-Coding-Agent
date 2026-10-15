from buildra.tools.output import truncate


def test_small_output_is_unchanged() -> None:
    assert truncate("a\nb\n", max_lines=10, max_bytes=1000) == "a\nb\n"


def test_long_output_keeps_head_and_tail() -> None:
    text = "".join(f"line {i}\n" for i in range(100))

    result = truncate(text, max_lines=10, max_bytes=10_000)

    assert result.startswith("line 0\n")
    assert result.rstrip().endswith("line 99")
    assert "90 lines omitted" in result
    assert "line 50" not in result


def test_byte_limit_applies_to_few_long_lines() -> None:
    text = ("x" * 5000 + "\n") * 4

    result = truncate(text, max_lines=100, max_bytes=4096)

    assert len(result.encode()) < 4096 + 200  # budget plus the marker line
    assert "omitted" in result


def test_single_huge_line_is_clipped_not_dropped() -> None:
    result = truncate("y" * 20_000, max_lines=100, max_bytes=2048)

    assert result.startswith("y")
    assert "omitted" in result
