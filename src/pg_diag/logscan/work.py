"""Killable log work, preserving validation and filesystem errors."""

from __future__ import annotations

from typing import Any
from functools import partial


def _work_result(function: Any, args: tuple) -> tuple[Any, Exception | None]:
    try:
        return function(*args), None
    except Exception as exc:
        return None, exc


async def run_log_work(function: Any, *args: Any, **kwargs: Any) -> Any:
    # Reuse the trusted-source worker: cancellation terminates and reaps it,
    # including a read blocked on slow storage. Cancelling a thread cannot.
    from ..executors.python import run_blocking

    if kwargs:
        function = partial(function, **kwargs)
    value, error = await run_blocking(_work_result, function, args)
    if error is not None:
        raise error
    return value
