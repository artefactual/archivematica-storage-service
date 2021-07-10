"""
PREMIS metadata generation.
"""

import uuid

import metsrw
from django.utils import timezone

from common import utils
from storage_service import __version__ as ss_version


PREMIS_META = metsrw.plugins.premisrw.PREMIS_3_0_META
SS_AGENT = metsrw.plugins.premisrw.PREMISAgent(
    data=(
        "agent",
        PREMIS_META,
        (
            "agent_identifier",
            ("agent_identifier_type", "preservation system"),
            (
                "agent_identifier_value",
                f"Archivematica-Storage-Service-{ss_version}",
            ),
        ),
        ("agent_name", "Archivematica Storage Service"),
        ("agent_type", "software"),
    )
)


def timestamp():
    return timezone.now().strftime("%Y-%m-%dT%H:%M:%S")


def add_agents_to_event_as_list(event, agents):
    """Add agents in ``agents`` to the list ``event`` which represents a
    PREMIS:EVENT.
    :param list event: a PREMIS:EVENT represented as a list
    :param iterable agents: an iterable of premisrw.PREMISAgent instances.
    """
    for agent in agents:
        event.append(
            (
                "linking_agent_identifier",
                ("linking_agent_identifier_type", agent.identifier_type),
                ("linking_agent_identifier_value", agent.identifier_value),
            )
        )
    return event


def create_replication_event(
    original_package_uuid, replica_package_uuid, event_uuid=None, agents=None
):
    """Return a PREMISEvent for replication of an AIP."""
    outcome_detail_note = (
        "Replicated Archival Information Package (AIP) {} by creating"
        " replica {}.".format(original_package_uuid, replica_package_uuid)
    )
    if not agents:
        agents = [SS_AGENT]
    if not event_uuid:
        event_uuid = str(uuid.uuid4())
    event = [
        "event",
        PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", event_uuid),
        ),
        ("event_type", "replication"),
        ("event_date_time", timestamp()),
        (
            "event_detail_information",
            ("event_detail", "Replication of an Archival Information Package"),
        ),
        (
            "event_outcome_information",
            ("event_outcome", "success"),
            (
                "event_outcome_detail",
                ("event_outcome_detail_note", outcome_detail_note),
            ),
        ),
    ]
    event = tuple(add_agents_to_event_as_list(event, agents))

    return metsrw.plugins.premisrw.PREMISEvent(data=event)


def create_premis_aip_creation_event(
    package_uuid, master_aip_uuid=None, agents=None, inst=True
):
    """Return a PREMISEvent for creation of an AIP."""
    if master_aip_uuid:
        outcome_detail_note = (
            "Created Archival Information Package (AIP) {} by replicating"
            " previously created AIP {}".format(package_uuid, master_aip_uuid)
        )
    else:
        outcome_detail_note = "Created Archival Information Package (AIP) {}".format(
            package_uuid
        )
    if not agents:
        agents = [SS_AGENT]
    event = [
        "event",
        PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", str(uuid.uuid4())),
        ),
        # Question: use the more specific 'information package creation'
        # PREMIS event?
        ("event_type", "creation"),
        ("event_date_time", timestamp()),
        (
            "event_detail_information",
            ("event_detail", "Creation of an Archival Information Package"),
        ),
        (
            "event_outcome_information",
            ("event_outcome", "success"),
            (
                "event_outcome_detail",
                ("event_outcome_detail_note", outcome_detail_note),
            ),
        ),
    ]
    event = tuple(add_agents_to_event_as_list(event, agents))

    return metsrw.plugins.premisrw.PREMISEvent(data=event)


def create_premis_aip_compression_event(
    event_detail, event_outcome_detail_note, agents=None
):
    """Return a PREMISEvent describing the compression of an AIP."""
    if not agents:
        agents = [SS_AGENT]
    event = [
        "event",
        PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", str(uuid.uuid4())),
        ),
        ("event_type", "compression"),
        ("event_date_time", timestamp()),
        ("event_detail_information", ("event_detail", event_detail)),
        (
            "event_outcome_information",
            ("event_outcome", "success"),
            (
                "event_outcome_detail",
                ("event_outcome_detail_note", event_outcome_detail_note),
            ),
        ),
    ]
    event = tuple(add_agents_to_event_as_list(event, agents))

    return metsrw.plugins.premisrw.PREMISEvent(data=event)


def create_replication_validation_event(
    replica_package_uuid,
    checksum_report,
    master_aip_uuid,
    fixity_report=None,
    agents=None,
):
    """Return a PREMISEvent for validation of AIP replication."""
    success = checksum_report["success"]
    if fixity_report:
        success = fixity_report["success"] and success
    outcome = success and "success" or "failure"
    detail = (
        "Validated the replication of Archival Information Package (AIP)"
        " {master_aip_uuid} to replica AIP {replica_aip_uuid}".format(
            master_aip_uuid=master_aip_uuid, replica_aip_uuid=replica_package_uuid
        )
    )
    if fixity_report:
        detail += " by performing a BagIt fixity check and by comparing" " checksums"
        outcome_detail_note = "{}\n{}".format(
            fixity_report["message"], checksum_report["message"]
        )
    else:
        detail += " by comparing checksums"
        outcome_detail_note = checksum_report["message"]
    if not agents:
        agents = [SS_AGENT]
    event = [
        "event",
        PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", str(uuid.uuid4())),
        ),
        ("event_type", "validation"),
        ("event_date_time", timestamp()),
        ("event_detail_information", ("event_detail", detail)),
        (
            "event_outcome_information",
            ("event_outcome", outcome),
            (
                "event_outcome_detail",
                ("event_outcome_detail_note", outcome_detail_note),
            ),
        ),
    ]
    event = tuple(add_agents_to_event_as_list(event, agents))

    return metsrw.plugins.premisrw.PREMISEvent(data=event)


def create_replication_derivation_relationship(
    related_aip_uuid, replication_event_uuid, premis_version=None
):
    """Return a PREMIS relationship of type derivation relating an implicit
    PREMIS object (an AIP) to some to related AIP (with UUID
    ``related_aip_uuid``) via a replication event with UUID
    ``replication_event_uuid``. Note the complication wherein PREMIS v. 2.2
    uses 'Identification' where PREMIS v. 3.0 uses 'Identifier'.
    """
    if not premis_version:
        premis_version = PREMIS_META["version"]
    related_object_identifier = {"2.2": "related_object_identification"}.get(
        premis_version, "related_object_identifier"
    )
    related_event_identifier = {"2.2": "related_event_identification"}.get(
        premis_version, "related_event_identifier"
    )
    return (
        "relationship",
        ("relationship_type", "derivation"),
        ("relationship_sub_type", ""),
        (
            related_object_identifier,
            ("related_object_identifier_type", "UUID"),
            ("related_object_identifier_value", related_aip_uuid),
        ),
        (
            related_event_identifier,
            ("related_event_identifier_type", "UUID"),
            ("related_event_identifier_value", replication_event_uuid),
        ),
    )


def create_aip_premis_object(
    package_uuid,
    package_size,
    package_extension,
    message_digest_algorithm,
    message_digest,
    archive_tool,
    compression_program_version,
    composition_level=1,
    premis_relationships=None,
):
    """Return a <premis:object> element for this package's (AIP's) pointer
    file.
    :param str package_uuid: unique identifier for the PREMIS object
    :param str package_size: size of object in bytes
    :param str package_extension: object file extension, e.g. .7z
    :param str message_digest_algorithm: name of the algorithm used to generate
        ``message_digest``.
    :param str message_digest: hex string checksum for the
        packaged/compressed AIP.
    :param str archive_tool: name of the tool (program) used to compress
        the AIP, e.g., '7-Zip'.
    :param str compression_program_version: version of ``archive_tool``
        used.
    :keyword int composition_level: PREMIS composition level (e.g. 2)
    :returns: <premis:object> as a tuple.
    """
    # PRONOM ID and PRONOM name for each file extension
    pronom_conversion = {
        ".7z": {"puid": utils.PRONOM_7Z, "name": "7Zip format"},
        ".bz2": {"puid": utils.PRONOM_BZIP2, "name": "BZIP2 Compressed Archive"},
        ".gz": {"puid": utils.PRONOM_GZIP, "name": "GZIP Compressed Archive"},
    }
    premis_relationships = premis_relationships or []
    kwargs = dict(
        xsi_type="premis:file",
        identifier_value=package_uuid,
        message_digest_algorithm=message_digest_algorithm,
        message_digest=message_digest,
        size=str(package_size),
        creating_application_name=archive_tool,
        creating_application_version=compression_program_version,
        date_created_by_application=timestamp(),
        relationship=premis_relationships,
        premis_version=PREMIS_META["version"],
        composition_level=str(composition_level),
    )
    try:
        kwargs.update(
            {
                "format_name": pronom_conversion[package_extension]["name"],
                "format_registry_name": "PRONOM",
                "format_registry_key": pronom_conversion[package_extension]["puid"],
            }
        )
    except KeyError:
        pass

    return metsrw.plugins.premisrw.PREMISObject(**kwargs)


def create_encryption_event(encr_result, key_fingerprint, gpg_version):
    """Return a PREMIS:EVENT for the encryption event."""
    detail = f"program=GPG; version={gpg_version}; key={key_fingerprint}"
    outcome_detail_note = 'Status="{}"; Standard Error="{}"'.format(
        encr_result.status.replace('"', r"\""),
        encr_result.stderr.replace('"', r"\"").strip(),
    )
    agents = [SS_AGENT]
    event = [
        "event",
        PREMIS_META,
        (
            "event_identifier",
            ("event_identifier_type", "UUID"),
            ("event_identifier_value", str(uuid.uuid4())),
        ),
        ("event_type", "encryption"),
        ("event_date_time", timestamp()),
        ("event_detail_information", ("event_detail", detail)),
        (
            "event_outcome_information",
            ("event_outcome", "success"),
            (
                "event_outcome_detail",
                ("event_outcome_detail_note", outcome_detail_note),
            ),
        ),
    ]
    event = tuple(add_agents_to_event_as_list(event, agents))

    return metsrw.plugins.premisrw.PREMISEvent(data=event)
