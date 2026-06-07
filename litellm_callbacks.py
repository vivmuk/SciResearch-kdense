"""LiteLLM proxy callbacks for K-Dense / Venice AI routing.

LiteLLM imports this module because it is declared in
`litellm_settings.callbacks` in `litellm_config.yaml`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from litellm.integrations.custom_logger import CustomLogger

# Ensure ``kady_agent`` is importable when the LiteLLM proxy is launched from
# a working directory that isn't the repo root (e.g. via ``uv run`` in CI).
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from kady_agent.runtime import record_cost  # noqa: E402
from kady_agent.runtime import extract_tags_from_headers  # noqa: E402

logger = logging.getLogger(__name__)


def _merge_header_sources(kwargs: dict[str, Any]) -> dict[str, str]:
    """Collect the full set of headers accompanying a proxy completion.

    We check three places in priority order:

    1. ``proxy_server_request.headers`` — the raw HTTP request the proxy
       received. This is where the Gemini CLI subprocess' custom headers
       land.
    2. ``optional_params.extra_headers`` — set when the proxy forwards
       extra_headers from the inbound request onto the outbound call.
    3. ``litellm_params.extra_headers`` — fallback for older LiteLLM
       versions that route headers through litellm_params.
    """
    merged: dict[str, str] = {}
    psr = kwargs.get("proxy_server_request")
    if isinstance(psr, dict):
        headers = psr.get("headers") or {}
        if isinstance(headers, dict):
            for k, v in headers.items():
                if v is not None:
                    merged[str(k)] = str(v)
    for key in ("optional_params", "litellm_params"):
        bucket = kwargs.get(key)
        if isinstance(bucket, dict):
            extra = bucket.get("extra_headers") or {}
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if v is not None:
                        merged[str(k)] = str(v)
    return merged


class VeniceProxyCallback(CustomLogger):
    """LiteLLM proxy callback — expert cost tracking for Venice AI routing.

    Records one ledger entry per expert completion by pulling the ``X-Kady-*``
    correlation headers off the inbound HTTP request.
    """

    def _record(self, kwargs: dict[str, Any], response_obj: Any) -> None:
        try:
            headers = _merge_header_sources(kwargs)
            tags = extract_tags_from_headers(headers)
            if not tags or tags.get("role") != "expert":
                return

            model = kwargs.get("model")
            if not isinstance(model, str):
                return
            if model.startswith("ollama/"):
                return

            cost = kwargs.get("response_cost")
            usage = None
            if response_obj is not None:
                usage = getattr(response_obj, "usage", None)
                if usage is None and isinstance(response_obj, dict):
                    usage = response_obj.get("usage")

            record_cost(
                session_id=tags["session_id"],
                turn_id=tags["turn_id"],
                role="expert",
                model=model,
                usage_dict=usage,
                cost_usd=cost,
                delegation_id=tags.get("delegation_id"),
                project_id=tags.get("project_id"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Expert cost callback failed: %s", exc)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._record(kwargs, response_obj)

    async def async_log_success_event(
        self, kwargs, response_obj, start_time, end_time
    ):
        self._record(kwargs, response_obj)


proxy_handler_instance = VeniceProxyCallback()
