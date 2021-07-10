from collections import namedtuple

from common import premis
from storage_service import __version__ as ss_version


FakeGPGRet = namedtuple("FakeGPGRet", "ok status stderr")
GPG_VERSION = "1.4.16"
SUCCESS_STATUS = "good times"
SOME_FINGERPRINT = "B9C518917A958DD0B1F5E1B80C3D34DDA5958532"


def test_create_encryption_event():
    stderr = 'me contain " quote'
    encr_result = FakeGPGRet(ok=True, status=SUCCESS_STATUS, stderr=stderr)
    event = premis.create_encryption_event(
        encr_result, SOME_FINGERPRINT, GPG_VERSION
    ).data
    assert event[0] == "event"
    event = event[2:]
    assert [x for x in event if x[0] == "event_type"][0][1] == "encryption"
    assert [x for x in event if x[0] == "event_detail_information"][0][1][1] == (
        f"program=GPG; version={GPG_VERSION}; key={SOME_FINGERPRINT}"
    )
    eoi = [x for x in event if x[0] == "event_outcome_information"][0]
    assert [x for x in eoi if x[0] == "event_outcome"][0][1] == "success"
    assert [x for x in eoi if x[0] == "event_outcome_detail"][0][1][1] == (
        'Status="{}"; Standard Error="{}"'.format(
            SUCCESS_STATUS, stderr.replace('"', r"\"")
        )
    )
    lai = [x for x in event if x[0] == "linking_agent_identifier"][0]
    assert [x for x in lai if x[0] == "linking_agent_identifier_value"][0][1] == (
        f"Archivematica-Storage-Service-{ss_version}"
    )
