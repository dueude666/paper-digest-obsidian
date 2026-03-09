"""Project specific exceptions."""


class PaperDigestError(Exception):
    """Base exception for the project."""


class ConfigurationError(PaperDigestError):
    """Raised when project configuration is invalid."""


class NetworkError(PaperDigestError):
    """Raised when an HTTP request fails after retries."""


class SourceLookupError(PaperDigestError):
    """Raised when no source can resolve a paper request."""


class DownloadError(PaperDigestError):
    """Raised when a paper PDF cannot be downloaded."""


class ParseError(PaperDigestError):
    """Raised when a PDF cannot be parsed."""


class WriteConflictError(PaperDigestError):
    """Raised when a file collision cannot be resolved."""


class ResearchProfileError(PaperDigestError):
    """Raised when the research profile configuration is invalid."""


class NoteIndexError(PaperDigestError):
    """Raised when note indexing or searching fails."""
