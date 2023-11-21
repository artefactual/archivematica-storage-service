import pytest
import requests
from locations.models import Duracloud
from locations.models import Space
from locations.models import StorageException


@pytest.fixture
def space():
    return Space.objects.create()


@pytest.mark.django_db
def test_duraspace_url(space):
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    assert d.duraspace_url == "https://duracloud.org/durastore/myspace/"


@pytest.mark.django_db
def test_browse(space, mocker):
    page1 = """
    <space id="self.durastore">
        <item>/foo/</item>
        <item>/foo/bar/bar-a.zip</item>
        <item>/foo/bar/bar-b.zip</item>
        <item>/foo/foo-a.zip</item>
        <item>/baz/</item>
    </space>
    """
    page2 = """
    <space id="self.durastore">
    </space>
    """
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(status_code=200, content=page1, spec=requests.Response),
            mocker.Mock(status_code=200, content=page2, spec=requests.Response),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    result = d.browse("/foo")

    assert result == {
        "directories": ["bar"],
        "entries": ["bar", "foo-a.zip"],
        "properties": {"bar": {"object count": 2}},
    }


@pytest.mark.django_db
def test_browse_strips_manifest_and_chunk_suffixes(space, mocker):
    page1 = """
    <space id="self.durastore">
        <item>/foo/</item>
        <item>/foo/bar/bar-a.zip</item>
        <item>/foo/bar/bar-b.zip.dura-manifest</item>
        <item>/foo/bar/bar-b.zip.dura-chunk-0000</item>
        <item>/foo/foo-a.zip</item>
        <item>/foo/foo-b.zip.dura-manifest</item>
        <item>/foo/foo-b.zip.dura-chunk-0000</item>
        <item>/baz/</item>
    </space>
    """
    page2 = """
    <space id="self.durastore">
    </space>
    """
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(status_code=200, content=page1, spec=requests.Response),
            mocker.Mock(status_code=200, content=page2, spec=requests.Response),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    result = d.browse("/foo")

    assert result == {
        "directories": ["bar"],
        "entries": ["bar", "foo-a.zip", "foo-b.zip"],
        "properties": {"bar": {"object count": 2}},
    }


@pytest.mark.django_db
def test_browse_fails_if_it_cannot_retrieve_files_initially(space, mocker):
    mocker.patch(
        "requests.Session.get",
        side_effect=[mocker.Mock(status_code=503, spec=requests.Response)],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    with pytest.raises(StorageException, match="Unable to get list of files in /foo/"):
        d.browse("/foo")


@pytest.mark.django_db
def test_browse_fails_if_it_cannot_retrieve_additional_files(space, mocker):
    page1 = """
    <space id="self.durastore">
        <item>/foo/</item>
        <item>/foo/bar/bar-a.zip</item>
        <item>/foo/bar/bar-b.zip</item>
        <item>/foo/foo-a.zip</item>
        <item>/baz/</item>
    </space>
    """
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(status_code=200, content=page1, spec=requests.Response),
            mocker.Mock(status_code=503, spec=requests.Response),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    with pytest.raises(
        StorageException, match="Unable to get list of files in /foo/bar/"
    ):
        d.browse("/foo/bar/")


@pytest.mark.django_db
def test_delete_path_deletes_file(space, mocker):
    delete = mocker.patch(
        "requests.Session.delete",
        side_effect=[mocker.Mock(status_code=200, spec=requests.Response)],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    d.delete_path("some/file.zip")

    assert delete.mock_calls == [
        mocker.call("https://duracloud.org/durastore/myspace/some/file.zip")
    ]


@pytest.mark.django_db
def test_delete_path_deletes_chunked_file(space, mocker):
    delete = mocker.patch(
        "requests.Session.delete",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, spec=requests.Response),
        ],
    )
    get = mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(
                status_code=200,
                content=b"""\
                    <chunks>
                        <chunk chunkId="some/file.zip.dura-chunk-0001">
                            <byteSize>8084</byteSize>
                            <md5>dcbfdd6ff7f78194e1084f900514a194</md5>
                        </chunk>
                    </chunks>
                """,
                spec=requests.Response,
            )
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    d.delete_path("some/file.zip")

    assert delete.mock_calls == [
        mocker.call("https://duracloud.org/durastore/myspace/some/file.zip"),
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.zip.dura-manifest"
        ),
    ]
    assert get.mock_calls == [
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.zip.dura-manifest"
        )
    ]


@pytest.mark.django_db
def test_delete_path_deletes_folder(space, mocker):
    delete = mocker.patch(
        "requests.Session.delete",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, spec=requests.Response),
            mocker.Mock(status_code=200, spec=requests.Response),
        ],
    )
    get = mocker.patch(
        "requests.Session.get",
        side_effect=[mocker.Mock(status_code=404, ok=False, spec=requests.Response)],
    )
    mocker.patch(
        "locations.models.duracloud.Duracloud._get_files_list",
        side_effect=[["some/folder/a.zip", "some/folder/b.zip"]],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")

    d.delete_path("some/folder")

    assert delete.mock_calls == [
        mocker.call("https://duracloud.org/durastore/myspace/some/folder"),
        mocker.call("https://duracloud.org/durastore/myspace/some/folder/a.zip"),
        mocker.call("https://duracloud.org/durastore/myspace/some/folder/b.zip"),
    ]
    assert get.mock_calls == [
        mocker.call("https://duracloud.org/durastore/myspace/some/folder.dura-manifest")
    ]


@pytest.mark.django_db
def test_move_to_storage_service_downloads_file(space, mocker, tmp_path):
    mocker.patch(
        "requests.Session.send",
        side_effect=[
            mocker.Mock(status_code=200, content=b"a file", spec=requests.Response)
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst" / "file.txt"

    d.move_to_storage_service("some/file.txt", dst.as_posix(), None)

    assert dst.read_text() == "a file"


@pytest.mark.django_db
def test_move_to_storage_service_downloads_chunked_file(space, mocker, tmp_path):
    mocker.patch(
        "requests.Session.send",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, content=b"a ch", spec=requests.Response),
            mocker.Mock(status_code=200, content=b"unked file", spec=requests.Response),
        ],
    )
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(
                status_code=200,
                content=b"""\
                    <dur>
                        <header>
                            <sourceContent>
                                <byteSize>14</byteSize>
                                <md5>1b8107d332e5d9f2a0b8e5924ca1ca3e</md5>
                            </sourceContent>
                        </header>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0001">
                                <byteSize>4</byteSize>
                                <md5>1781a616499ac88f78b56af57fcca974</md5>
                            </chunk>
                        </chunks>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0002">
                                <byteSize>10</byteSize>
                                <md5>29224657c84874b1c83a92fae2f2ea22</md5>
                            </chunk>
                        </chunks>
                    </dur>
                """,
                spec=requests.Response,
            ),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst" / "file.txt"

    d.move_to_storage_service("some/file.txt", dst.as_posix(), None)

    assert dst.read_text() == "a chunked file"


@pytest.mark.django_db
def test_move_to_storage_service_downloads_folder(space, mocker, tmp_path):
    mocker.patch(
        "requests.Session.send",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, content=b"file A", spec=requests.Response),
            mocker.Mock(status_code=200, content=b"file B", spec=requests.Response),
        ],
    )
    mocker.patch(
        "requests.Session.get",
        side_effect=[mocker.Mock(status_code=404, ok=False, spec=requests.Response)],
    )
    mocker.patch(
        "locations.models.duracloud.Duracloud._get_files_list",
        side_effect=[["some/folder/a.txt", "some/folder/b.txt"]],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst"

    d.move_to_storage_service("some/folder", dst.as_posix(), None)

    # The folder contents were downloaded to the destination folder.
    assert {e.name for e in dst.iterdir()} == {"a.txt", "b.txt"}
    assert (dst / "a.txt").read_text() == "file A"
    assert (dst / "b.txt").read_text() == "file B"


@pytest.mark.django_db
def test_move_to_storage_service_fails_if_it_cannot_download_file(
    space, mocker, tmp_path
):
    mocker.patch(
        "requests.Session.send",
        side_effect=[mocker.Mock(status_code=503, spec=requests.Response)],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst" / "file.txt"

    with pytest.raises(
        StorageException,
        match="Unable to fetch https://duracloud.org/durastore/myspace/some/file.txt",
    ):
        d.move_to_storage_service("some/file.txt", dst.as_posix(), None)


@pytest.mark.django_db
def test_move_to_storage_service_fails_if_chunk_size_does_not_match(
    space, mocker, tmp_path
):
    send = mocker.patch(
        "requests.Session.send",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, content=b"ERRORERROR", spec=requests.Response),
            mocker.Mock(status_code=200, content=b"unked file", spec=requests.Response),
        ],
    )
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(
                status_code=200,
                content=b"""\
                    <dur>
                        <header>
                            <sourceContent>
                                <byteSize>14</byteSize>
                                <md5>1b8107d332e5d9f2a0b8e5924ca1ca3e</md5>
                            </sourceContent>
                        </header>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0001">
                                <byteSize>4</byteSize>
                                <md5>1781a616499ac88f78b56af57fcca974</md5>
                            </chunk>
                        </chunks>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0002">
                                <byteSize>10</byteSize>
                                <md5>29224657c84874b1c83a92fae2f2ea22</md5>
                            </chunk>
                        </chunks>
                    </dur>
                """,
                spec=requests.Response,
            ),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst" / "file.txt"

    # Look for a partial match since the exception receives multiple parameters.
    with pytest.raises(
        StorageException, match="does not match expected size of"
    ) as exc_info:
        d.move_to_storage_service("some/file.txt", dst.as_posix(), None)

    assert exc_info.value.args == (
        "File %(path)s does not match expected size of %(expected_size)s bytes, but was actually %(actual_size)s bytes",
        {"actual_size": 10, "expected_size": 4, "path": f"{dst}.dura-chunk-0001"},
    )

    # The destination file was created but no chunks were written to it.
    assert dst.read_text() == ""

    # The session.send mock was not called after the first chunk failed validation.
    assert len(send.mock_calls) == 2


@pytest.mark.django_db
def test_move_to_storage_service_fails_if_chunk_checksum_does_not_match(
    space, mocker, tmp_path
):
    send = mocker.patch(
        "requests.Session.send",
        side_effect=[
            mocker.Mock(status_code=404, spec=requests.Response),
            mocker.Mock(status_code=200, content=b"a ch", spec=requests.Response),
            mocker.Mock(status_code=200, content=b"unked file", spec=requests.Response),
        ],
    )
    mocker.patch(
        "requests.Session.get",
        side_effect=[
            mocker.Mock(
                status_code=200,
                content=b"""\
                    <dur>
                        <header>
                            <sourceContent>
                                <byteSize>14</byteSize>
                                <md5>1b8107d332e5d9f2a0b8e5924ca1ca3e</md5>
                            </sourceContent>
                        </header>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0001">
                                <byteSize>4</byteSize>
                                <md5>bogus</md5>
                            </chunk>
                        </chunks>
                        <chunks>
                            <chunk chunkId="some/file.txt.dura-chunk-0002">
                                <byteSize>10</byteSize>
                                <md5>29224657c84874b1c83a92fae2f2ea22</md5>
                            </chunk>
                        </chunks>
                    </dur>
                """,
                spec=requests.Response,
            ),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    dst = tmp_path / "dst" / "file.txt"

    # Look for a partial match since the exception receives multiple parameters.
    with pytest.raises(
        StorageException, match="does not match expected checksum of"
    ) as exc_info:
        d.move_to_storage_service("some/file.txt", dst.as_posix(), None)

    assert exc_info.value.args == (
        "File %s does not match expected checksum of %s, but was actually %s",
        f"{dst}.dura-chunk-0001",
        "bogus",
        "1781a616499ac88f78b56af57fcca974",
    )

    # The destination file was created but no chunks were written to it.
    assert dst.read_text() == ""

    # The session.send mock was not called after the first chunk failed validation.
    assert len(send.mock_calls) == 2


@pytest.mark.django_db
def test_move_from_storage_service_uploads_file(space, mocker, tmp_path):
    put = mocker.patch(
        "requests.Session.put",
        side_effect=[mocker.Mock(status_code=201, spec=requests.Response)],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"
    f.write_text("a file")

    d.move_from_storage_service(f.as_posix(), "some/file.txt")

    assert put.mock_calls == [
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.txt",
            data=mocker.ANY,
            headers={
                "Content-MD5": "d6d0c756fb8abfb33e652a20e85b70bc",
                "Content-Type": "text/plain",
            },
        )
    ]


@pytest.mark.django_db
def test_move_from_storage_service_uploads_chunked_file(space, mocker, tmp_path):
    put = mocker.patch(
        "requests.Session.put",
        side_effect=[
            mocker.Mock(status_code=201, spec=requests.Response),
            mocker.Mock(status_code=201, spec=requests.Response),
            mocker.Mock(status_code=201, spec=requests.Response),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    d.CHUNK_SIZE = 4
    d.BUFFER_SIZE = 2
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"
    f.write_text("a file")

    d.move_from_storage_service(f.as_posix(), "some/file.txt")

    assert put.mock_calls == [
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.txt.dura-chunk-0000",
            data=mocker.ANY,
            headers={"Content-MD5": "417a095d4148cb184601f536fb626765"},
        ),
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.txt.dura-chunk-0001",
            data=mocker.ANY,
            headers={"Content-MD5": "d9180594744f870aeefb086982e980bb"},
        ),
        mocker.call(
            "https://duracloud.org/durastore/myspace/some/file.txt.dura-manifest",
            data=mocker.ANY,
            headers={"Content-MD5": "59e5f62e5ed85ba339e73db5756e57c7"},
        ),
    ]


@pytest.mark.django_db
def test_move_from_storage_service_uploads_folder_contents(space, mocker, tmp_path):
    put = mocker.patch(
        "requests.Session.put",
        side_effect=[
            mocker.Mock(status_code=201, spec=requests.Response),
            mocker.Mock(status_code=201, spec=requests.Response),
        ],
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("file A")
    (src / "b.txt").write_text("file B")

    d.move_from_storage_service(src.as_posix(), "some/folder")

    put.assert_has_calls(
        [
            mocker.call(
                "https://duracloud.org/durastore/myspace/some/folder//a.txt",
                data=mocker.ANY,
                headers={
                    "Content-MD5": "31d97c4d04593b21b399ace73b061c34",
                    "Content-Type": "text/plain",
                },
            ),
            mocker.call(
                "https://duracloud.org/durastore/myspace/some/folder//b.txt",
                data=mocker.ANY,
                headers={
                    "Content-MD5": "1651d570b74339e94cace90cde7d3147",
                    "Content-Type": "text/plain",
                },
            ),
        ],
        any_order=True,
    )


@pytest.mark.django_db
def test_move_from_storage_service_fails_uploading_after_exceeding_retries(
    space, mocker, tmp_path
):
    put = mocker.patch(
        "requests.Session.put",
        side_effect=mocker.Mock(status_code=503, spec=requests.Response),
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"
    f.write_text("a file")

    with pytest.raises(StorageException, match=f"Unable to store {f}"):
        d.move_from_storage_service(f.as_posix(), "some/file.txt")

    # Check session's put method was called with initial attempt plus 3 retries.
    assert len(put.mock_calls) == 4


@pytest.mark.django_db
def test_move_from_storage_service_reraises_requests_exception(space, mocker, tmp_path):
    put = mocker.patch(
        "requests.Session.put",
        side_effect=requests.exceptions.ConnectionError(),
    )
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"
    f.write_text("a file")

    with pytest.raises(requests.exceptions.ConnectionError):
        d.move_from_storage_service(f.as_posix(), "some/file.txt")

    # Check session's put method was called with initial attempt plus 3 retries.
    assert len(put.mock_calls) == 4


@pytest.mark.django_db
def test_move_from_storage_service_fails_if_source_file_does_not_exist(space, tmp_path):
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"

    with pytest.raises(StorageException, match=f"{f} does not exist."):
        d.move_from_storage_service(f.as_posix(), "some/file.txt")


@pytest.mark.django_db
def test_move_from_storage_service_fails_if_source_file_cannot_be_determined(
    space, mocker, tmp_path
):
    # Mocking exists like this forces all move_from_storage_service conditions to fail.
    mocker.patch("os.path.exists", return_value=True)
    d = Duracloud.objects.create(space=space, host="duracloud.org", duraspace="myspace")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "file.txt"

    with pytest.raises(StorageException, match=f"{f} is not a file or directory."):
        d.move_from_storage_service(f.as_posix(), "some/file.txt")
