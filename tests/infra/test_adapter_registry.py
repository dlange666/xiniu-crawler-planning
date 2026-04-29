"""adapter_registry 单元测试。"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from infra import adapter_registry
from infra.adapter_registry import (
    AdapterNotFound,
    DuplicateAdapter,
    InvalidAdapterMeta,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    adapter_registry.reset()
    yield
    adapter_registry.reset()


def _write_adapter(
    domains_root: Path, *, ctx: str, host_stem: str,
    meta: str = "", body: str = "", with_hooks: bool = True,
) -> None:
    """在 tmp domains/<ctx>/<source>/<source>_adapter.py 写一个最小 adapter。"""
    source_dir = domains_root / ctx / host_stem
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "__init__.py").touch()
    (domains_root / ctx / "__init__.py").touch()

    default_meta = f"""
        ADAPTER_META = {{
            "host": "{host_stem}.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r"^https?://{host_stem}\\.example\\.com/list/.*",
            "detail_url_pattern": r"^https?://{host_stem}\\.example\\.com/detail/\\d+",
            "last_verified_at": "2026-04-28",
        }}
    """
    hooks = """
        def parse_list(html, url):
            return None
        def parse_detail(html, url):
            return None
    """ if with_hooks else ""
    (source_dir / f"{host_stem}_adapter.py").write_text(
        textwrap.dedent(meta or default_meta) + textwrap.dedent(hooks) + body
    )


def _write_legacy_adapter(domains_root: Path, *, ctx: str, host_stem: str) -> None:
    """在旧路径 domains/<ctx>/adapters/<host_stem>.py 写一个最小 adapter。"""
    adir = domains_root / ctx / "adapters"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "__init__.py").touch()
    (domains_root / ctx / "__init__.py").touch()
    default_meta = f"""
        ADAPTER_META = {{
            "host": "{host_stem}.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r"^https?://{host_stem}\\.example\\.com/list/.*",
            "detail_url_pattern": r"^https?://{host_stem}\\.example\\.com/detail/\\d+",
            "last_verified_at": "2026-04-28",
        }}
        def parse_list(html, url):
            return None
        def parse_detail(html, url):
            return None
    """
    (adir / f"{host_stem}.py").write_text(textwrap.dedent(default_meta))


@pytest.fixture
def fake_domains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """构造一个临时 domains/ 树，并把它加入 sys.path 以便 import_module 能找到。

    必须先清掉 sys.modules 中已缓存的真实 domains.* —— 否则 importlib 会
    返回真实仓库下的模块（找不到 fake 子模块）。
    """
    for mod_name in list(sys.modules):
        if mod_name == "domains" or mod_name.startswith("domains."):
            del sys.modules[mod_name]
    root = tmp_path / "fake_repo"
    domains = root / "domains"
    domains.mkdir(parents=True)
    (domains / "__init__.py").touch()
    monkeypatch.syspath_prepend(str(root))
    yield domains
    for mod_name in list(sys.modules):
        if mod_name == "domains" or mod_name.startswith("domains."):
            del sys.modules[mod_name]


def test_discover_picks_up_adapter(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="aaa")
    n = adapter_registry.discover(domains_root=fake_domains)
    assert n == 1
    entries = adapter_registry.list_all()
    assert len(entries) == 1
    e = entries[0]
    assert e.business_context == "gov_policy"
    assert e.host == "aaa.example.com"
    assert e.schema_version == 1
    assert e.data_kind == "policy"
    assert e.module_path == "domains.gov_policy.aaa.aaa_adapter"


def test_discover_still_supports_legacy_adapters_during_migration(fake_domains: Path) -> None:
    _write_legacy_adapter(fake_domains, ctx="gov_policy", host_stem="legacy")
    n = adapter_registry.discover(domains_root=fake_domains)

    assert n == 1
    e = adapter_registry.get("gov_policy", "legacy.example.com")
    assert e.module_path == "domains.gov_policy.adapters.legacy"


def test_get_returns_entry_and_raises_on_unknown(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="bbb")
    adapter_registry.discover(domains_root=fake_domains)
    e = adapter_registry.get("gov_policy", "bbb.example.com")
    assert callable(e.module.parse_list)

    with pytest.raises(AdapterNotFound, match="bbb.example.com"):
        adapter_registry.get("gov_policy", "nope.example.com")


def test_get_error_lists_candidates_in_same_context(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="ccc")
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="ddd")
    adapter_registry.discover(domains_root=fake_domains)
    with pytest.raises(AdapterNotFound) as exc_info:
        adapter_registry.get("gov_policy", "missing.example.com")
    assert "ccc.example.com" in str(exc_info.value)
    assert "ddd.example.com" in str(exc_info.value)


def test_discover_skips_underscore_files(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="real")
    # _helper.py 也被写出来，但应被跳过
    (fake_domains / "gov_policy" / "real" / "_helper.py").write_text(
        "ADAPTER_META = {}  # 应被跳过\n"
    )
    adapter_registry.discover(domains_root=fake_domains)
    assert {e.host for e in adapter_registry.list_all()} == {"real.example.com"}


def test_discover_skips_modules_without_meta(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="ok")
    no_meta_dir = fake_domains / "gov_policy" / "ok"
    (no_meta_dir / "shared.py").write_text("def helper(): return 1\n")
    adapter_registry.discover(domains_root=fake_domains)
    assert {e.host for e in adapter_registry.list_all()} == {"ok.example.com"}


def test_meta_missing_required_key_raises(fake_domains: Path) -> None:
    bad_meta = """
        ADAPTER_META = {
            "host": "bad.example.com",
            "schema_version": 1,
            # 缺 data_kind / patterns / last_verified_at
        }
    """
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="bad", meta=bad_meta)
    with pytest.raises(InvalidAdapterMeta, match="missing keys"):
        adapter_registry.discover(domains_root=fake_domains)


def test_meta_missing_hooks_raises(fake_domains: Path) -> None:
    _write_adapter(
        fake_domains, ctx="gov_policy", host_stem="nohook", with_hooks=False)
    with pytest.raises(InvalidAdapterMeta, match="parse_list"):
        adapter_registry.discover(domains_root=fake_domains)


def test_business_context_inferred_from_path(fake_domains: Path) -> None:
    """META 不带 owner_context 时，从目录路径 domains/<ctx>/ 推断。"""
    _write_adapter(fake_domains, ctx="exchange_policy", host_stem="xyz")
    adapter_registry.discover(domains_root=fake_domains)
    e = adapter_registry.get("exchange_policy", "xyz.example.com")
    assert e.business_context == "exchange_policy"


def test_business_context_meta_override_wins(fake_domains: Path) -> None:
    """META.owner_context 显式声明 → 覆盖目录推断。"""
    meta = """
        ADAPTER_META = {
            "host": "h.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r".*",
            "detail_url_pattern": r".*",
            "last_verified_at": "2026-04-28",
            "owner_context": "explicit_ctx",
        }
    """
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="ovr", meta=meta)
    adapter_registry.discover(domains_root=fake_domains)
    e = adapter_registry.list_all()[0]
    assert e.business_context == "explicit_ctx"


def test_duplicate_registration_raises(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="dup1")
    # 同 host，不同模块名
    meta = """
        ADAPTER_META = {
            "host": "dup1.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r".*",
            "detail_url_pattern": r".*",
            "last_verified_at": "2026-04-28",
        }
    """
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="dup2", meta=meta)
    with pytest.raises(DuplicateAdapter, match="dup1.example.com"):
        adapter_registry.discover(domains_root=fake_domains)


def test_discover_idempotent(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="iii")
    adapter_registry.discover(domains_root=fake_domains)
    # 再调一次不应报 DuplicateAdapter
    adapter_registry.discover(domains_root=fake_domains)
    assert len(adapter_registry.list_all()) == 1


def test_resolve_by_url_matches_list_pattern(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="qq")
    adapter_registry.discover(domains_root=fake_domains)
    hit = adapter_registry.resolve_by_url(
        "https://qq.example.com/list/page1", "gov_policy")
    assert hit is not None
    assert hit.host == "qq.example.com"
    miss = adapter_registry.resolve_by_url(
        "https://other.example.com/list/p1", "gov_policy")
    assert miss is None


def test_list_all_filters_by_context(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="g1")
    _write_adapter(fake_domains, ctx="exchange_policy", host_stem="e1")
    adapter_registry.discover(domains_root=fake_domains)
    assert {e.host for e in adapter_registry.list_all(business_context="gov_policy")} == {"g1.example.com"}
    assert {e.host for e in adapter_registry.list_all(business_context="exchange_policy")} == {"e1.example.com"}


def test_render_mode_defaults_to_direct(fake_domains: Path) -> None:
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="rd")
    adapter_registry.discover(domains_root=fake_domains)
    assert adapter_registry.list_all()[0].render_mode == "direct"


def test_render_mode_headless_accepted(fake_domains: Path) -> None:
    meta = """
        ADAPTER_META = {
            "host": "h.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r".*",
            "detail_url_pattern": r".*",
            "last_verified_at": "2026-04-28",
            "render_mode": "headless",
        }
    """
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="hl", meta=meta)
    adapter_registry.discover(domains_root=fake_domains)
    assert adapter_registry.list_all()[0].render_mode == "headless"


def test_render_mode_invalid_rejected(fake_domains: Path) -> None:
    meta = """
        ADAPTER_META = {
            "host": "h.example.com",
            "schema_version": 1,
            "data_kind": "policy",
            "list_url_pattern": r".*",
            "detail_url_pattern": r".*",
            "last_verified_at": "2026-04-28",
            "render_mode": "magic",
        }
    """
    _write_adapter(fake_domains, ctx="gov_policy", host_stem="bad", meta=meta)
    with pytest.raises(InvalidAdapterMeta, match="render_mode"):
        adapter_registry.discover(domains_root=fake_domains)


def test_real_ndrc_adapter_picked_up_by_default_discovery() -> None:
    """跑真实仓库的 discover()：ndrc adapter 应该自动注册。"""
    adapter_registry.discover()
    e = adapter_registry.get("gov_policy", "www.ndrc.gov.cn")
    assert e.module_path == "domains.gov_policy.ndrc.ndrc_adapter"
    assert e.data_kind == "policy"
