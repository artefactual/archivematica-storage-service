import os

from django.test import TestCase

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
