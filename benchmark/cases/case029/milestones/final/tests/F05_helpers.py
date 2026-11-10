# feature: F05
"""Caller-owned model boundary for observing blocking approval."""
from F01_helpers import RecordingModel


class ApprovalBoundaryModel(RecordingModel):
    """Reject a real model request that crosses the caller's approval boundary."""

    def __init__(self, approval, *outputs):
        super().__init__(*outputs)
        self.approval = approval

    async def get_response(self, *args, **kwargs):
        assert self.approval(), "Model request occurred before blocking approval."
        return await super().get_response(*args, **kwargs)
