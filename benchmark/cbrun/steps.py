"""Step abstraction for cbrun (architecture stub for multi-step cases).

cbrun currently treats each case as a single final acceptance suite. It
normalizes that shape into exactly one :class:`Step` and exposes
:func:`discover_steps` so multi-step support can be added later without
touching the run/judge/results code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assets import CaseSpec

__all__ = ["Step", "discover_steps"]


@dataclass(frozen=True)
class Step:
    """One development+gate unit.

    For the single-final case there is exactly one step (``index == 1``) whose
    spec is the case PRD + Interface Contract and whose hidden gate is the final
    acceptance milestone.
    """

    index: int
    prd_text: str
    contract_text: str
    # Hidden acceptance assets for this step's gate.
    acceptance_dir: Path
    test_manifest: dict
    is_final: bool


def discover_steps(case: CaseSpec) -> list[Step]:
    """Return the ordered steps for a case.

    Current behaviour: always a single final step. The multi-step branch is a
    deliberate, documented extension point; wiring it must keep the contract
    that each returned step carries its own spec + hidden gate and that the
    runner advances only after a step's gate passes.
    """
    acceptance = case.assets.acceptance
    final_step = Step(
        index=1,
        prd_text=case.prd_text,
        contract_text=case.contract_text,
        acceptance_dir=Path(acceptance.acceptance_dir),
        test_manifest=dict(acceptance.test_manifest),
        is_final=True,
    )
    # NOTE(extension point): a future multi-step loader would inspect
    # ``case.assets`` milestones for ``step_<N>`` directories with step-local
    # PRD/Contract/test_manifest and return them here in order, marking only the
    # last one ``is_final=True``. Until that asset shape exists,
    # returning the single final step keeps single-final and multi-step callers
    # on one code path.
    return [final_step]
