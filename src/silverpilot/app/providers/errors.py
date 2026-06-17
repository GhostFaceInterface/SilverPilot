"""Typed provider failures for observable collector behavior."""


class ProviderError(RuntimeError):
    """Base error for external provider failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when a public provider endpoint cannot be reached."""


class ProviderParseError(ProviderError):
    """Raised when a provider payload cannot be parsed safely."""


class DataQualityError(ProviderError):
    """Raised when parsed provider data fails quality checks."""


class StaleDataError(DataQualityError):
    """Raised when a quote is too old for downstream use."""
