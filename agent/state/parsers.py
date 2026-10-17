from typing import Any

from pydantic import ValidationError

from state.schema import DaemonSnapshot, SnapshotModel


def parse_daemon_snapshot(raw: dict[str, Any]) -> DaemonSnapshot:
    """Validate and unwrap a Guidecore RPC snapshot.

    This is the boundary between untrusted RPC data and agent state.
    """
    if not isinstance(raw, dict):
        raise TypeError("Guidecore snapshot response must be an object.")

    daemon_state = raw.get("daemon_state")
    if not isinstance(daemon_state, dict):
        raise ValueError("Guidecore snapshot response is missing daemon_state.")

    try:
        validated = SnapshotModel.model_validate(daemon_state)
    except ValidationError as exc:
        raise ValueError(f"Invalid Guidecore daemon snapshot: {exc}") from exc

    return validated.model_dump(by_alias=True)
