class ExagiumError(Exception):
    """Harness 可预期故障的基础异常。"""


class ManifestError(ExagiumError):
    """任务清单无效或无法解析。"""


class WorkspaceError(ExagiumError):
    """无法准备隔离运行工作区。"""


class AgentProcessError(ExagiumError):
    """外部 Agent 进程无法安全运行。"""


class InvalidStatusTransition(ExagiumError):
    """运行尝试了无效的状态迁移。"""
