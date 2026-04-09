from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from typing import IO
from typing import Literal
from typing import TypedDict
from typing import overload

class _GPGKeyDictRequired(TypedDict):
    type: str
    trust: str
    length: str
    algo: str
    keyid: str
    date: str
    expires: str
    dummy: str
    ownertrust: str
    sig: str
    cap: str
    issuer: str
    flag: str
    token: str
    hash: str
    curve: str
    compliance: str
    updated: str
    origin: str
    keygrip: str
    uids: list[str]
    sigs: list[tuple[str, str, str]]
    subkeys: list[list[str | None]]
    fingerprint: str

class _GPGKeyDict(_GPGKeyDictRequired, total=False):
    subkey_info: dict[str, dict[str, str]]

class ListKeys(list[_GPGKeyDict]):
    key_map: dict[str, _GPGKeyDict]
    fingerprints: list[str]
    uids: list[str]

    def __init__(self, gpg: GPG) -> None: ...
    def __iter__(self) -> Iterator[_GPGKeyDict]: ...

class ImportResult:
    count: int
    no_user_id: int
    imported: int
    imported_rsa: int
    unchanged: int
    n_uids: int
    n_subk: int
    n_sigs: int
    n_revoc: int
    sec_read: int
    sec_imported: int
    sec_dups: int
    not_imported: int
    fingerprints: list[str]
    results: list[dict[str, str | None]]

    def __init__(self, gpg: GPG) -> None: ...

class Crypt:
    ok: bool
    status: str
    status_detail: str
    stderr: str
    data: bytes | str
    key_id: str | None

    def __init__(self, gpg: GPG) -> None: ...

class GenKey:
    type: str | None
    fingerprint: str
    status: str | None

    def __init__(self, gpg: GPG) -> None: ...

class DeleteResult:
    status: str

    def __init__(self, gpg: GPG) -> None: ...
    def __str__(self) -> str: ...

class GPG:
    gpgbinary: str
    version: tuple[int, int, int] | None

    def __init__(
        self,
        gpgbinary: str = ...,
        gnupghome: str | None = ...,
        verbose: bool = ...,
        use_agent: bool = ...,
        keyring: str | Sequence[str] | None = ...,
        options: str | Sequence[str] | None = ...,
        secret_keyring: str | Sequence[str] | None = ...,
        env: Mapping[str, str] | None = ...,
    ) -> None: ...
    def list_keys(
        self,
        secret: bool = ...,
        keys: str | Sequence[str] | None = ...,
        sigs: bool = ...,
    ) -> ListKeys: ...
    def gen_key_input(self, **kwargs: object) -> str: ...
    def gen_key(self, input: str) -> GenKey: ...
    def import_keys(
        self,
        key_data: str | bytes,
        extra_args: Sequence[str] | None = ...,
        passphrase: str | None = ...,
    ) -> ImportResult: ...
    def encrypt(
        self,
        data: str | bytes,
        recipients: str | Sequence[str],
        **kwargs: object,
    ) -> Crypt: ...
    def decrypt(self, message: str | bytes, **kwargs: object) -> Crypt: ...
    @overload
    def export_keys(
        self,
        keyids: str | Sequence[str],
        secret: bool = ...,
        armor: Literal[True] = ...,
        minimal: bool = ...,
        passphrase: str | None = ...,
        expect_passphrase: bool = ...,
        output: str | None = ...,
    ) -> str: ...
    @overload
    def export_keys(
        self,
        keyids: str | Sequence[str],
        secret: bool = ...,
        armor: Literal[False] = ...,
        minimal: bool = ...,
        passphrase: str | None = ...,
        expect_passphrase: bool = ...,
        output: str | None = ...,
    ) -> bytes: ...
    def delete_keys(
        self,
        fingerprints: str | Sequence[str],
        secret: bool = ...,
        passphrase: str | None = ...,
        expect_passphrase: bool = ...,
        exclamation_mode: bool = ...,
    ) -> DeleteResult: ...
    def decrypt_file(
        self,
        fileobj_or_path: str | IO[bytes],
        always_trust: bool = ...,
        passphrase: str | None = ...,
        output: str | None = ...,
        extra_args: list[str] | None = ...,
    ) -> Crypt: ...
    def encrypt_file(
        self,
        fileobj_or_path: str | IO[bytes],
        recipients: str | Sequence[str],
        sign: str | None = ...,
        always_trust: bool = ...,
        passphrase: str | None = ...,
        armor: bool = ...,
        output: str | None = ...,
        symmetric: bool | str = ...,
        extra_args: list[str] | None = ...,
    ) -> Crypt: ...
