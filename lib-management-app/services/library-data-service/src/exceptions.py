"""
Custom exceptions — mapped to HTTP status codes in main.py exception handlers.
"""


class LibraryNotFoundError(Exception):
    """Raised when a library id is not present in the primary catalog."""

    def __init__(self, library_id: int) -> None:
        self.library_id = library_id
        super().__init__(f"Library id={library_id} not found")


class PipelineAlreadyRunningError(Exception):
    """Raised when a new pipeline run is requested while another run is active."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Pipeline already running: run_id={run_id}")


class ValidationError(Exception):
    """Raised when business-level input validation fails in a service method."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class VersionNotFoundError(Exception):
    """Raised when a requested version does not exist in library version history."""

    def __init__(self, library_id: int, version: str) -> None:
        self.library_id = library_id
        self.version = version
        super().__init__(f"Version '{version}' not found for library id={library_id}")
