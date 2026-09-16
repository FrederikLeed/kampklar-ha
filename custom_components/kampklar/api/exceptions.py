"""Exceptions for the KampKlar API client."""


class KampKlarApiError(Exception):
    """Base exception for KampKlar API errors."""


class KampKlarAuthError(KampKlarApiError):
    """Authentication failed."""


class KampKlarConnectionError(KampKlarApiError):
    """Connection to the API failed."""
