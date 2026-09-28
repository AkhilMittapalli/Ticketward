"""Generator API keys kept in the operating system's credential store.

The repository is OneDrive-synced, so keys never live in a file inside it, in a committed
config, or on a shell command line (where history could capture them).
``python -m tw_ml.datagen keys set --family A`` reads the key at a hidden prompt and stores it via
``keyring``: Windows Credential Manager on Windows, Keychain on macOS, Secret Service on Linux.
A ``TW_DATAGEN_<family>_API_KEY`` environment variable, when set, still takes precedence.

One vendor account can serve several families (D-07: DeepInfra serves Family A and Family B), so a
family with no key of its own reuses another family's key **on the same host** (``B:deepinfra``
falls back to ``A:deepinfra``). Keys never cross hosts.

Backends that would store the key unencrypted, or not at all, are refused.
"""

from typing import Final

SERVICE: Final = "ticketward-datagen"
FAMILIES: Final[tuple[str, ...]] = ("A", "B")
MIN_KEY_LENGTH: Final = 16
MAX_KEY_LENGTH: Final = 512
_REFUSED_BACKEND_MARKERS: Final = (
    "keyring.backends.fail.",  # no store at all
    "keyring.backends.null.",  # silently discards
    "keyrings.alt.",  # file-based stores (plaintext or password-file)
)


class KeyStoreError(RuntimeError):
    """The key is malformed or no secure credential store is available."""


def credential_name(family: str, host: str) -> str:
    """Name of the stored credential for one family and host.

    Args:
        family: ``A`` or ``B``.
        host: Host profile label from ``ml/configs/datagen.yaml`` (e.g. ``deepinfra``).

    Returns:
        The credential user name, e.g. ``A:deepinfra``.
    """
    return f"{family}:{host}"


def backend_names() -> list[str]:
    """Describe the active credential store(s).

    A chained backend (Linux/macOS with several stores) is expanded into its members.

    Returns:
        Qualified class names, e.g. ``["keyring.backends.Windows.WinVaultKeyring"]``.
    """
    import keyring  # noqa: PLC0415 - loaded on use, keeps module import cheap

    backend = keyring.get_keyring()
    members = getattr(backend, "backends", None)
    targets = list(members) if members else [backend]
    return [f"{type(b).__module__}.{type(b).__qualname__}" for b in targets]


def _require_secure_backend() -> None:
    names = backend_names()
    insecure = [n for n in names if any(n.startswith(m) for m in _REFUSED_BACKEND_MARKERS)]
    if insecure or not names:
        msg = (
            f"no secure credential store is available (keyring backends: {', '.join(names)}); "
            "set TW_DATAGEN_<family>_API_KEY in the environment instead"
        )
        raise KeyStoreError(msg)


def validate_key(key: str) -> str:
    """Normalize and sanity-check a pasted API key.

    Args:
        key: The pasted key.

    Returns:
        The key without surrounding whitespace.

    Raises:
        KeyStoreError: If it is empty, contains whitespace, or has an implausible length. The
            message never includes the key.
    """
    cleaned = key.strip()
    if not cleaned:
        msg = "the key is empty"
        raise KeyStoreError(msg)
    if any(ch.isspace() for ch in cleaned):
        msg = "the key contains whitespace; paste only the key itself"
        raise KeyStoreError(msg)
    if not MIN_KEY_LENGTH <= len(cleaned) <= MAX_KEY_LENGTH:
        msg = f"the key has an implausible length ({len(cleaned)} characters)"
        raise KeyStoreError(msg)
    return cleaned


def store_key(family: str, host: str, key: str) -> None:
    """Validate and store a key in the credential store.

    Args:
        family: ``A`` or ``B``.
        host: Host profile label.
        key: The pasted key.

    Raises:
        KeyStoreError: If the key is malformed or no secure store is available.
    """
    cleaned = validate_key(key)
    _require_secure_backend()
    import keyring  # noqa: PLC0415

    keyring.set_password(SERVICE, credential_name(family, host), cleaned)


def find_key(family: str, host: str) -> tuple[str, str] | None:
    """Find the key a family uses on a host: its own, else another family's on the same host.

    Args:
        family: ``A`` or ``B``.
        host: Host profile label.

    Returns:
        ``(key, credential name it was read from)``, or ``None`` when nothing usable is stored or
        no secure store is available.
    """
    try:
        _require_secure_backend()
    except KeyStoreError:
        return None
    import keyring  # noqa: PLC0415
    from keyring.errors import KeyringError  # noqa: PLC0415

    for owner in (family, *(f for f in FAMILIES if f != family)):
        name = credential_name(owner, host)
        try:
            key = keyring.get_password(SERVICE, name)
        except KeyringError:
            continue
        if key:
            return key, name
    return None


def load_key(family: str, host: str) -> str | None:
    """Read the key a family uses on a host (see :func:`find_key`).

    Args:
        family: ``A`` or ``B``.
        host: Host profile label.

    Returns:
        The key, or ``None`` when nothing is stored or no secure store is available.
    """
    found = find_key(family, host)
    return found[0] if found else None


def key_status(family: str, host: str) -> str:
    """Describe where a family's key on a host comes from, never the key itself.

    Args:
        family: ``A`` or ``B``.
        host: Host profile label.

    Returns:
        ``stored``, ``stored (shared with A:deepinfra)`` or ``not stored``.
    """
    found = find_key(family, host)
    if found is None:
        return "not stored"
    source = found[1]
    return "stored" if source == credential_name(family, host) else f"stored (shared with {source})"


def delete_key(family: str, host: str) -> bool:
    """Remove a stored key.

    Args:
        family: ``A`` or ``B``.
        host: Host profile label.

    Returns:
        ``True`` if a key was removed, ``False`` if none was stored.

    Raises:
        KeyStoreError: If no secure store is available.
    """
    _require_secure_backend()
    import keyring  # noqa: PLC0415
    from keyring.errors import PasswordDeleteError  # noqa: PLC0415

    try:
        keyring.delete_password(SERVICE, credential_name(family, host))
    except PasswordDeleteError:
        return False
    return True
