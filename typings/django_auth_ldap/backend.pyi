from django.dispatch import Signal

populate_user: Signal

class LDAPBackend: ...

class _LDAPUser:
    @property
    def group_names(self) -> set[str]: ...
