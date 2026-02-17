import pytest

from archivematica.storage_service.common.templatetags.lang import standardize_lang_code


@pytest.mark.parametrize(
    "language_code,expected",
    [
        ("en-us", "en_US"),
        ("pt-br", "pt_BR"),
        ("es", "es"),
    ],
)
def test_standardize_lang_code(language_code, expected):
    assert standardize_lang_code(language_code) == expected
