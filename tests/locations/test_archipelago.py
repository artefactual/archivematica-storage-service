import json
import logging  # Added import
from unittest.mock import ANY
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import mock_open
from unittest.mock import patch

import pytest
import requests
from locations.models import Archipelago
from locations.models import Space
from lxml import etree
from requests.exceptions import HTTPError

LOGGER = logging.getLogger(__name__)


@pytest.fixture
def archipelago_space():
    return Archipelago(
        space=Space(),
        archipelago_url="http://example.com",
        archipelago_user="username",
        archipelago_password="password",
    )


def test_move_from_storage_service(archipelago_space):
    source_path = "/path/to/source"
    destination_path = "/path/to/destination"
    package = Mock(uuid="package_uuid")

    with patch("os.path.basename") as mock_basename, patch(
        "os.path.exists"
    ) as mock_exists, patch(
        "locations.models.Archipelago._get_metadata"
    ) as mock_get_metadata, patch(
        "locations.models.Archipelago.extract_title_from_mets_xml"
    ) as mock_extract_title, patch(
        "locations.models.Archipelago._upload_file"
    ) as mock_upload_file, patch(
        "locations.models.Archipelago.get_dc_metadata"
    ) as mock_get_dc_metadata, patch(
        "locations.models.Archipelago._upload_metadata"
    ) as mock_upload_metadata:
        mock_basename.return_value = "filename"
        mock_exists.return_value = True
        mock_get_metadata.return_value = "mets_xml"
        mock_extract_title.return_value = "title"
        mock_upload_file.return_value = "fid"
        mock_get_dc_metadata.return_value = "strawberry"

        archipelago_space.move_from_storage_service(
            source_path, destination_path, package
        )

    mock_get_metadata.assert_called_once_with(
        source_path, package.uuid, package_type="AIP"
    )
    mock_extract_title.assert_called_once_with("mets_xml")
    mock_upload_file.assert_called_once_with("filename", source_path)
    mock_get_dc_metadata.assert_called_once_with("mets_xml")
    mock_upload_metadata.assert_called_once_with("fid", "strawberry", "title")


def test_move_from_storage_service_no_source(archipelago_space):
    source_path = "/path/to/source"
    destination_path = "/path/to/destination"
    package = Mock(uuid="package_uuid")
    expected_result = None

    with patch("os.path.basename") as mock_basename, patch(
        "os.path.exists"
    ) as mock_exists, patch(
        "locations.models.Archipelago._get_metadata"
    ) as mock_get_metadata, patch(
        "locations.models.Archipelago.extract_title_from_mets_xml"
    ) as mock_extract_title, patch(
        "locations.models.Archipelago._upload_file"
    ) as mock_upload_file, patch(
        "locations.models.Archipelago.get_dc_metadata"
    ) as mock_get_dc_metadata:
        mock_basename.return_value = "filename"
        mock_exists.return_value = False
        mock_get_metadata.return_value = "mets_xml"
        mock_extract_title.return_value = "title"
        mock_upload_file.return_value = "fid"
        mock_get_dc_metadata.return_value = "strawberry"

        result = archipelago_space.move_from_storage_service(
            source_path, destination_path, package
        )

    assert result == expected_result


def test_upload_file(archipelago_space):
    filename = "test.zip"
    source_path = "/path/to/test.zip"
    expected_fid = "12345"

    with patch("requests.post") as mock_post, patch(
        "builtins.open", mock_open(read_data="data")
    ):
        mock_response = mock_post.return_value
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {"attributes": {"drupal_internal__fid": expected_fid}}
        }
        mock_response.raise_for_status.return_value = None

        fid = archipelago_space._upload_file(filename, source_path)

        assert fid == expected_fid
        mock_post.assert_called_once_with(
            f"{archipelago_space.archipelago_url}/jsonapi/node/aip/field_file_drop",
            data=ANY,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'file; filename="{filename}"',
            },
            auth=(
                archipelago_space.archipelago_user,
                archipelago_space.archipelago_password,
            ),
        )


def test_upload_file_error(archipelago_space):
    filename = "test.zip"
    source_path = "/path/to/test.zip"

    with patch("requests.post") as mock_post, patch(
        "builtins.open", mock_open(read_data="data")
    ):
        mock_response = mock_post.return_value
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = HTTPError()

        fid = archipelago_space._upload_file(filename, source_path)

        assert fid is None
        mock_post.assert_called_once_with(
            f"{archipelago_space.archipelago_url}/jsonapi/node/aip/field_file_drop",
            data=ANY,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'file; filename="{filename}"',
            },
            auth=(
                archipelago_space.archipelago_user,
                archipelago_space.archipelago_password,
            ),
        )
        mock_response.raise_for_status.assert_called_once()


def test_get_metadata(archipelago_space):
    input_path = "/path/to/input/file"
    aip_uuid = "12345678-1234-5678-1234-567812345678"
    package_type = "example_package"
    expected_output = b"<mets/>"

    with patch.object(archipelago_space, "_get_mets_el") as mock_get_mets_el:
        mock_get_mets_el.return_value = etree.Element("mets")

        output = archipelago_space._get_metadata(input_path, aip_uuid, package_type)

        assert output == expected_output


def test_extract_title_from_mets_xml(archipelago_space):
    xml_string = '<mets:mets xmlns:mets="http://www.loc.gov/METS/"><mets:dmdSec><mets:mdWrap><mets:xmlData><dcterms:dublincore xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Title Example</dc:title></dcterms:dublincore></mets:xmlData></mets:mdWrap></mets:dmdSec></mets:mets>'

    result = archipelago_space.extract_title_from_mets_xml(xml_string)

    assert result == "Title Example"


def test_extract_title_from_mets_xml_no_title(archipelago_space):
    xml_string = """
        <mets:mets xmlns:mets="http://www.loc.gov/METS/">
            <mets:dmdSec>
                <mets:mdWrap>
                    <mets:xmlData>
                        <dcterms:dublincore xmlns:dcterms="http://purl.org/dc/terms/">
                            <dc:creator>Author Example</dc:creator>
                        </dcterms:dublincore>
                    </mets:xmlData>
                </mets:mdWrap>
            </mets:dmdSec>
        </mets:mets>
    """

    result = archipelago_space.extract_title_from_mets_xml(xml_string)

    assert result is None


def test_extract_title_from_mets_xml_invalid_xml(archipelago_space):
    xml_string = "<invalid_xml>"

    result = archipelago_space.extract_title_from_mets_xml(xml_string)

    assert result is None


def test_upload_metadata(archipelago_space):
    fid = "12345"
    strawberry = '{"key": "value"}'
    title = "Test Title"

    with patch("requests.post") as mock_post, patch(
        "locations.models.archipelago.LOGGER.info"
    ) as mock_logger_info:
        mock_response = mock_post.return_value
        mock_response.status_code = 201
        mock_response.raise_for_status.return_value = None

        archipelago_space._upload_metadata(fid, strawberry, title)

        json_metadata = json.dumps(
            {
                **json.loads(strawberry),
                "label": title,
                "archivematica_zip": fid,
                "ap:entitymapping": {
                    "entity:file": ["archivematica_zip"],
                    "entity:node": ["ispartof", "ismemberof"],
                },
            }
        )
        request_data = {
            "data": {
                "type": "AIP",
                "attributes": {
                    "title": title,
                    "field_descriptive_metadata": json_metadata,
                },
            }
        }
        json_data = json.dumps(request_data)

        mock_post.assert_called_once_with(
            f"{archipelago_space.archipelago_url}/jsonapi/node/aip",
            data=json_data,
            headers={
                "Content-Type": "application/vnd.api+json",
            },
            auth=(
                archipelago_space.archipelago_user,
                archipelago_space.archipelago_password,
            ),
        )
        assert mock_logger_info.call_args_list == [
            call("uploading metadata"),
            call("AIP entity created successfully!"),
        ]


def test_upload_metadata_error(archipelago_space):
    fid = "12345"
    strawberry = '{"key": "value"}'
    title = "Test Title"
    archipelago_url = "http://example.com"
    archipelago_user = "username"
    archipelago_password = "password"

    with patch("requests.post") as mock_post, patch(
        "locations.models.archipelago.LOGGER.error"
    ) as mock_logger_error:
        mock_response = mock_post.return_value
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError

        archipelago_space._upload_metadata(fid, strawberry, title)

        json_metadata = json.dumps(
            {
                **json.loads(strawberry),
                "label": title,
                "archivematica_zip": fid,
                "ap:entitymapping": {
                    "entity:file": ["archivematica_zip"],
                    "entity:node": ["ispartof", "ismemberof"],
                },
            }
        )
        request_data = {
            "data": {
                "type": "AIP",
                "attributes": {
                    "title": title,
                    "field_descriptive_metadata": json_metadata,
                },
            }
        }
        json_data = json.dumps(request_data)

        mock_post.assert_called_once_with(
            f"{archipelago_url}/jsonapi/node/aip",
            data=json_data,
            headers={
                "Content-Type": "application/vnd.api+json",
            },
            auth=(archipelago_user, archipelago_password),
        )
        mock_response.raise_for_status.assert_called_once()
        assert mock_logger_error.call_args_list == [
            call("Error during AIP upload to archipelago %s", ""),
        ]


def test_get_dc_metadata(archipelago_space):
    xml_string = """
        <mets:mets xmlns:mets="http://www.loc.gov/METS/">
            <mets:dmdSec>
                <mets:mdWrap>
                    <mets:xmlData>
                        <dcterms:dublincore xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dc="http://purl.org/dc/elements/1.1/">
                            <dc:title>Title Example</dc:title>
                            <dc:creator>Author Example</dc:creator>
                            <dc:subject>Subject Example</dc:subject>
                        </dcterms:dublincore>
                    </mets:xmlData>
                </mets:mdWrap>
            </mets:dmdSec>
        </mets:mets>
    """
    expected_output = (
        '{"field_creator": "Author Example", "field_subject": "Subject Example"}'
    )

    output = archipelago_space.get_dc_metadata(xml_string)

    assert output == expected_output


def test_get_dc_metadata_no_fields(archipelago_space):
    xml_string = """
        <mets:mets xmlns:mets="http://www.loc.gov/METS/">
            <mets:dmdSec>
                <mets:mdWrap>
                    <mets:xmlData>
                        <dcterms:dublincore xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dc="http://purl.org/dc/elements/1.1/">
                            <dc:title>Title Example</dc:title>
                        </dcterms:dublincore>
                    </mets:xmlData>
                </mets:mdWrap>
            </mets:dmdSec>
        </mets:mets>
    """
    expected_output = "{}"

    output = archipelago_space.get_dc_metadata(xml_string)

    assert output == expected_output
