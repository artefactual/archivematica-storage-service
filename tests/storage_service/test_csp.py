from csp.constants import NONCE
from csp.constants import NONE
from csp.constants import REPORT_SAMPLE
from csp.constants import SELF
from csp.constants import STRICT_DYNAMIC

from archivematica.storage_service.storage_service.settings.components.csp import (
    build_content_security_policy,
)


def test_build_content_security_policy_uses_nonce_enforced_defaults():
    assert build_content_security_policy() == {
        "DIRECTIVES": {
            "default-src": [NONE],
            "script-src": [NONCE, STRICT_DYNAMIC, REPORT_SAMPLE],
            "style-src": [SELF],
            "img-src": [SELF],
            "font-src": [SELF, "data:"],
            "connect-src": [SELF],
            "object-src": [NONE],
            "base-uri": [SELF],
            "form-action": [SELF],
            "frame-ancestors": [NONE],
            "require-trusted-types-for": ["'script'"],
            "trusted-types": ["am-storage-service", "dompurify", "vue"],
        }
    }


def test_build_content_security_policy_adds_report_uri():
    assert build_content_security_policy("https://example.com/csp-report/") == {
        "DIRECTIVES": {
            "default-src": [NONE],
            "script-src": [NONCE, STRICT_DYNAMIC, REPORT_SAMPLE],
            "style-src": [SELF],
            "img-src": [SELF],
            "font-src": [SELF, "data:"],
            "connect-src": [SELF],
            "object-src": [NONE],
            "base-uri": [SELF],
            "form-action": [SELF],
            "frame-ancestors": [NONE],
            "require-trusted-types-for": ["'script'"],
            "trusted-types": ["am-storage-service", "dompurify", "vue"],
            "report-uri": "https://example.com/csp-report/",
        }
    }
