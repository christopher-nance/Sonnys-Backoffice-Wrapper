"""Exception hierarchy for the Sonny's Backoffice Wrapper."""


class SonnysBackofficeError(Exception):
    """Base class for all errors raised by this library."""


class AuthenticationError(SonnysBackofficeError):
    """Login failed, or session expired and re-authentication failed."""


class NotFoundError(SonnysBackofficeError):
    """Lookup (by POS User ID or email) did not match any record."""


class ValidationError(SonnysBackofficeError):
    """Caller input violated a constraint, or Backoffice rejected the payload."""


class PermissionDeniedError(SonnysBackofficeError):
    """The bot user lacks sufficient rights for the requested operation."""


class DuplicateError(SonnysBackofficeError):
    """A record with the given email or POS User ID already exists on this tenant."""


class BackofficeServerError(SonnysBackofficeError):
    """Unexpected server response — HTTP 5xx or unparseable HTML."""
