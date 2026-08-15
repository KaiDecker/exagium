class ExagiumError(Exception):
    """Base error for expected harness failures."""


class ManifestError(ExagiumError):
    """A task manifest is invalid or cannot be resolved."""


class WorkspaceError(ExagiumError):
    """An isolated run workspace could not be prepared."""


class AgentProcessError(ExagiumError):
    """The external agent process could not be run safely."""


class InvalidStatusTransition(ExagiumError):
    """A run attempted an invalid state transition."""
