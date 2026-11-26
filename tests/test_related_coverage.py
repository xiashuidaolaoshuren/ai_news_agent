"""Tests for related_display_ranks identity linking (B5)."""

from __future__ import annotations

from ai_news_agent.models import DigestEntry, FollowUpAction, NewsItem, SourceKind


def _entry(title: str, *, kind: SourceKind = SourceKind.GITHUB, source_id: str = "a") -> DigestEntry:
    return DigestEntry(
        source_kind=kind,
        source_id=source_id,
        title=title,
        source_name="Test",
        source_url="https://example.com",
        summary="s",
        why_it_matters="w",
        background_knowledge="b",
        follow_up_action=FollowUpAction.READ,
    )


def _pair(entry: DigestEntry) -> tuple[DigestEntry, NewsItem | None]:
    return (entry, None)


def test_confident_pair_lists_each_other_and_unrelated_lists_none() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("Qwen3.8-27B", source_id="1")
    b = _entry("Qwen3.8-27B", source_id="2")
    c = _entry("Llama 3.1 8B", source_id="3")
    result = related_display_ranks([_pair(a), _pair(b), _pair(c)])
    assert result[1] == [2]
    assert result[2] == [1]
    assert result[3] == []


def test_flash_and_pro_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    flash = _entry("M3.1 Flash")
    pro = _entry("M3.1 Pro")
    result = related_display_ranks([_pair(flash), _pair(pro)])
    assert result[1] == []
    assert result[2] == []


def test_different_sizes_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    small = _entry("M3.1 7B")
    large = _entry("M3.1 70B")
    result = related_display_ranks([_pair(small), _pair(large)])
    assert result[1] == []
    assert result[2] == []


def test_different_versions_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    m3 = _entry("M3")
    m31 = _entry("M3.1")
    result = related_display_ranks([_pair(m3), _pair(m31)])
    assert result[1] == []
    assert result[2] == []


def test_generic_topic_words_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("both are reasoning models")
    b = _entry("both are reasoning models")
    result = related_display_ranks([_pair(a), _pair(b)])
    assert result[1] == []
    assert result[2] == []


def test_one_sided_version_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    with_ver = _entry("M3.1 8B")
    without = _entry("8B")
    result = related_display_ranks([_pair(with_ver), _pair(without)])
    assert result[1] == []
    assert result[2] == []


def test_different_products_with_same_version_and_size_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    llama = _entry("Llama 3.1 8B", source_id="1")
    qwen = _entry("Qwen 3.1 8B", source_id="2")
    result = related_display_ranks([_pair(llama), _pair(qwen)])
    assert result[1] == []
    assert result[2] == []


def test_different_products_with_same_variant_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    claude = _entry("Claude Pro", source_id="1")
    gemini = _entry("Gemini Pro", source_id="2")
    result = related_display_ranks([_pair(claude), _pair(gemini)])
    assert result[1] == []
    assert result[2] == []


def test_bare_integer_versions_are_part_of_the_product_name() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    qwen2 = _entry("Qwen2 7B", source_id="1")
    qwen3 = _entry("Qwen3 7B", source_id="2")
    result = related_display_ranks([_pair(qwen2), _pair(qwen3)])
    assert result[1] == []
    assert result[2] == []


def test_bare_major_version_counts_as_a_version() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("Google: Gemini 4 Hydrogen", source_id="1")
    b = _entry("Google 推出 Gemini 4 Hydrogen", source_id="2")
    result = related_display_ranks([_pair(a), _pair(b)])
    assert result[1] == [2]
    assert result[2] == [1]


def test_bare_version_with_different_number_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    four = _entry("Gemini 4 Hydrogen", source_id="1")
    five = _entry("Gemini 5 Hydrogen", source_id="2")
    result = related_display_ranks([_pair(four), _pair(five)])
    assert result[1] == []
    assert result[2] == []


def test_bare_version_with_a_packaging_suffix_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    plain = _entry("Google: Gemini 4 Hydrogen", source_id="1")
    batch = _entry("Google: Gemini 4 Hydrogen (batch)", source_id="2")
    result = related_display_ranks([_pair(plain), _pair(batch)])
    assert result[1] == []
    assert result[2] == []


def test_bare_version_with_a_different_variant_name_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    scout = _entry("Llama 4 Scout", source_id="1")
    maverick = _entry("Llama 4 Maverick", source_id="2")
    result = related_display_ranks([_pair(scout), _pair(maverick)])
    assert result[1] == []
    assert result[2] == []


def test_counts_that_are_not_versions_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    top = _entry("Top 10 AI agents", source_id="1")
    models = _entry("10 reasoning models", source_id="2")
    result = related_display_ranks([_pair(top), _pair(models)])
    assert result[1] == []
    assert result[2] == []


def test_numeric_only_identity_residue_does_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    model = _entry("模型 3", source_id="1")
    product = _entry("产品 3", source_id="2")
    result = related_display_ranks([_pair(model), _pair(product)])
    assert result[1] == []
    assert result[2] == []


def test_marker_only_titles_do_not_link() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("3 Pro", source_id="1")
    b = _entry("3 Pro", source_id="2")
    result = related_display_ranks([_pair(a), _pair(b)])
    assert result[1] == []
    assert result[2] == []


def test_same_product_same_version_and_size_links() -> None:
    from ai_news_agent.related_coverage import related_display_ranks

    a = _entry("Llama 3.1 8B", source_id="1")
    b = _entry("Llama 3.1 8B", source_id="2")
    result = related_display_ranks([_pair(a), _pair(b)])
    assert result[1] == [2]
    assert result[2] == [1]

