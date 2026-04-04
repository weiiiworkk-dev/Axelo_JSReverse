from __future__ import annotations

from axelo.utils.domain import extract_site_domain


def test_extract_site_domain_keeps_registrable_domain_for_multi_label_suffix():
    assert extract_site_domain("https://www.lazada.com.my/#?") == "lazada.com.my"
    assert extract_site_domain("member.lazada.com.my") == "lazada.com.my"


def test_extract_site_domain_keeps_standard_two_label_domain():
    assert extract_site_domain("https://sub.example.com/path") == "example.com"
