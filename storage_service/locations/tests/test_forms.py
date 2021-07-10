import os

from django.test import TestCase
import pytest

from locations import forms, models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))


class TestCallbackForm(TestCase):
    fixtures = ["callback.json"]

    def test_headers_added(self):
        callback = models.Callback.objects.get(
            uuid="ef0672a2-d0ed-474b-95f6-ff8f9ea1fc15"
        )
        form = forms.CallbackForm(None, instance=callback)
        # Existing headers should be added in order
        assert form.fields["header_0"].initial == (
            "Authorization",
            "Token token_string",
        )
        assert form.fields["header_1"].initial == ("Origin", "http://ss.com")
        # An extra field should be added
        assert form.fields["header_2"]

    def test_headers_processed(self):
        callback = models.Callback.objects.get(
            uuid="ef0672a2-d0ed-474b-95f6-ff8f9ea1fc15"
        )
        post_data = {
            "event": "post_store_dip",
            "uri": "https://consumer.com/api/v1/dip/<package_uuid>/stored",
            "method": "post",
            "header_0_0": "Authorization",
            "header_0_1": "Token token_string",
            "header_1_0": "Origin",
            "header_1_1": "http://ss.com",
            "header_2_0": "Existing-header-fields-key",
            "header_2_1": "Existing header fields value",
            "header_3_0": "",
            "header_3_1": "",
            "header_4_0": "New-header-fields-key",
            "header_4_1": "New header fields value",
            "body": "",
            "expected_status": 202,
            "enabled": True,
        }
        form = forms.CallbackForm(post_data, instance=callback)
        callback = form.save()
        # Headers should be processed in order, ignoring empty values
        processed_headers = (
            '{"Authorization": "Token token_string", '
            '"Origin": "http://ss.com", '
            '"Existing-header-fields-key": "Existing header fields value", '
            '"New-header-fields-key": "New header fields value"}'
        )
        assert callback.headers == processed_headers


@pytest.mark.parametrize(
    "test_case",
    [
        {
            "choices": [("v1", "Value 1"), ("v2", "Value 2"), ("v3", "Value 3")],
            "selected_choice": "",
            "disabled_choices": [],
            "expected": [
                {"value": "v1", "label": "Value 1", "attrs": {}},
                {"value": "v2", "label": "Value 2", "attrs": {}},
                {"value": "v3", "label": "Value 3", "attrs": {}},
            ],
        },
        {
            "choices": [("o1", "First"), ("o2", "Second"), ("o3", "Third")],
            "disabled_choices": ["o1"],
            "selected_choice": "o2",
            "expected": [
                {"value": "o1", "label": "First", "attrs": {"disabled": "disabled"}},
                {"value": "o2", "label": "Second", "attrs": {"selected": True}},
                {"value": "o3", "label": "Third", "attrs": {}},
            ],
        },
        {
            "choices": [("A", "A"), ("B", "B"), ("C", "C")],
            "selected_choice": "B",
            "disabled_choices": ["A", "C"],
            "expected": [
                {"value": "A", "label": "A", "attrs": {"disabled": "disabled"}},
                {"value": "B", "label": "B", "attrs": {"selected": True}},
                {"value": "C", "label": "C", "attrs": {"disabled": "disabled"}},
            ],
        },
    ],
    ids=["all_enabled", "one_disabled", "multiple_disabled"],
)
def test_disableable_select_widget_disables_options(test_case):
    widget = forms.DisableableSelectWidget(
        choices=test_case["choices"], disabled_choices=test_case["disabled_choices"]
    )
    result = [
        {"value": option["value"], "label": option["label"], "attrs": option["attrs"]}
        for option in widget.options("field-name", test_case["selected_choice"])
    ]
    assert result == test_case["expected"]
