from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from typing import TYPE_CHECKING
from typing import Any

import boto3
import pytest
from boto3.resources.base import ServiceResource

if TYPE_CHECKING:
    from mypy_boto3_s3.service_resource import Bucket
    from mypy_boto3_s3.service_resource import BucketObjectsCollection
    from mypy_boto3_s3.service_resource import S3ServiceResource


class KeyRecordingIterable:
    """Proxy iterable that appends each yielded S3 key to the tracking list."""

    def __init__(self, collection: Any, seen_keys: list[str]) -> None:
        self._collection = collection
        self._seen_keys = seen_keys

    def __iter__(self) -> Iterator[Any]:
        for obj in self._collection:
            self._seen_keys.append(obj.key)
            yield obj

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)


class KeyRecordingCollection:
    """Proxy iterable that appends each yielded S3 key to the tracking list."""

    def __init__(
        self, collection: BucketObjectsCollection, seen_keys: list[str]
    ) -> None:
        self._collection = collection
        self._seen_keys = seen_keys

    def filter(self, *args: Any, **kwargs: Any) -> KeyRecordingIterable:
        filtered = self._collection.filter(*args, **kwargs)
        return KeyRecordingIterable(filtered, self._seen_keys)

    def all(self) -> KeyRecordingIterable:
        everything = self._collection.all()
        return KeyRecordingIterable(everything, self._seen_keys)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)


class KeyRecordingPaginator:
    """Wrap paginator so iterated pages append the keys they expose."""

    def __init__(self, paginator: Any, seen_keys: list[str]) -> None:
        self._paginator = paginator
        self._seen_keys = seen_keys

    def paginate(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        for page in self._paginator.paginate(*args, **kwargs):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if key:
                    self._seen_keys.append(key)
            yield page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._paginator, name)


class KeyRecordingClient:
    """Client wrapper that returns key-recording paginators."""

    def __init__(self, client: Any, seen_keys: list[str]) -> None:
        self._client = client
        self._seen_keys = seen_keys

    def get_paginator(self, name: str) -> KeyRecordingPaginator:
        paginator = self._client.get_paginator(name)
        return KeyRecordingPaginator(paginator, self._seen_keys)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class KeyRecordingMeta:
    """Meta wrapper ensuring the client records keys."""

    def __init__(self, meta: Any, seen_keys: list[str]) -> None:
        self._meta = meta
        self._seen_keys = seen_keys
        self._client_wrapper: KeyRecordingClient | None = None

    @property
    def client(self) -> KeyRecordingClient:
        if self._client_wrapper is None:
            self._client_wrapper = KeyRecordingClient(
                self._meta.client, self._seen_keys
            )
        return self._client_wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self._meta, name)


class KeyRecordingBucket:
    """Expose a bucket whose object collections add accessed keys to the log."""

    def __init__(self, bucket: Bucket, seen_keys: list[str]) -> None:
        self._bucket = bucket
        self._seen_keys = seen_keys

    @property
    def objects(self) -> KeyRecordingCollection:
        original_collection = self._bucket.objects
        return KeyRecordingCollection(original_collection, self._seen_keys)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bucket, name)


class KeyRecordingResource:
    """Resource wrapper that yields key-recording buckets."""

    def __init__(self, resource: S3ServiceResource, seen_keys: list[str]) -> None:
        self._resource = resource
        self._seen_keys = seen_keys
        self._meta_wrapper: KeyRecordingMeta | None = None

    def Bucket(self, name: str) -> KeyRecordingBucket:
        bucket = self._resource.Bucket(name)
        if not isinstance(bucket, ServiceResource):
            raise TypeError("Expected ServiceResource bucket")
        return KeyRecordingBucket(bucket, self._seen_keys)

    @property
    def meta(self) -> KeyRecordingMeta:
        if self._meta_wrapper is None:
            self._meta_wrapper = KeyRecordingMeta(self._resource.meta, self._seen_keys)
        return self._meta_wrapper

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resource, name)


def make_key_recording_resource_factory(
    recorded_keys: list[str], original_factory: Callable[..., S3ServiceResource]
) -> Callable[..., KeyRecordingResource]:
    def factory(*args: Any, **kwargs: Any) -> KeyRecordingResource:
        resource = original_factory(*args, **kwargs)
        return KeyRecordingResource(resource, recorded_keys)

    return factory


@pytest.fixture
def s3_recorded_keys(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Override boto3.resource so each key bubbled through the wrappers lands in this list."""
    recorded_keys: list[str] = []
    original_boto3_resource = boto3.resource
    tracking_factory = make_key_recording_resource_factory(
        recorded_keys, original_boto3_resource
    )
    monkeypatch.setattr(boto3, "resource", tracking_factory)
    return recorded_keys
