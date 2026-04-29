"""infra/crawl/pagination_helpers 翻页发现工具。"""

from __future__ import annotations

from infra.crawl.pagination_helpers import (
    detect_path_paginator,
    detect_url_param_paginator,
    expand_create_page_html_pages,
    parse_create_page_html,
)


def test_parse_create_page_html_ndrc() -> None:
    html = """<html>...
    createPageHTML(9, 0, "index", "html");
    </html>"""
    result = parse_create_page_html(html)
    assert result == (9, "index", "html")


def test_parse_create_page_html_single_quoted_total_first() -> None:
    html = """<script>createPageHTML(3, 1, 'index', 'shtml');</script>"""
    result = parse_create_page_html(html)
    assert result == (3, "index", "shtml")


def test_parse_create_page_html_container_id_first() -> None:
    html = """<script>createPageHTML('page_div',5, 1,'fg','shtml',89);</script>"""
    result = parse_create_page_html(html)
    assert result == (5, "fg", "shtml")


def test_parse_create_page_html_no_match() -> None:
    assert parse_create_page_html("<html>plain</html>") is None


def test_expand_create_page_html_pages() -> None:
    pages = expand_create_page_html_pages(
        "https://x.com/list/", total=4, prefix="index", suffix="html")
    # 包含 index.html, index_1.html, index_2.html, index_3.html
    # 但不含与 list_url == https://x.com/list/ 相等的项
    assert "https://x.com/list/index.html" in pages
    assert "https://x.com/list/index_1.html" in pages
    assert "https://x.com/list/index_2.html" in pages
    assert "https://x.com/list/index_3.html" in pages


def test_detect_url_param_paginator() -> None:
    html = """<html>
    <a href="?page=2">Next</a>
    <a href="?page=3">3</a>
    <a href="https://x.com/?p=4">4</a>
    <a href="?other=x">Not pagination</a>
    </html>"""
    pages = detect_url_param_paginator(html, "https://x.com/list/")
    assert "https://x.com/list/?page=2" in pages
    assert "https://x.com/list/?page=3" in pages
    assert "https://x.com/?p=4" in pages
    assert all("other=x" not in p for p in pages)


def test_detect_path_paginator() -> None:
    html = """<html>
    <a href="index_2.html">2</a>
    <a href="list_3.html">3</a>
    <a href="/page/4/">4</a>
    <a href="p5.html">5</a>
    <a href="other.html">Not pagination</a>
    </html>"""
    pages = detect_path_paginator(html, "https://x.com/articles/")
    assert any("index_2.html" in p for p in pages)
    assert any("list_3.html" in p for p in pages)
    assert any("/page/4/" in p for p in pages)
    assert any("p5.html" in p for p in pages)
    assert all("other.html" not in p for p in pages)
