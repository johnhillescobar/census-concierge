"""One Census GET: a wall-clock deadline and a single identical hedge.

`httpx`'s numeric timeout is four independent phase budgets, so a call given
`timeout=60` can run past a minute. This waits on the clock instead. A call
still in flight after `HEDGE_AFTER`, or one that fails to connect, is sent
once more. The first response back is the one that is used.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import NoReturn

import httpx

from src.census_url import redact_text

# Clean-window maximum in evidence/slice-6/latency/arms-clean.jsonl is 4.311s.
HEDGE_AFTER = 10.0
TOTAL_DEADLINE = 60.0

Getter = Callable[[str, httpx.Client], httpx.Response]


def census_get(
    url: str,
    *,
    hedge_after: float = HEDGE_AFTER,
    total: float = TOTAL_DEADLINE,
    get: Getter | None = None,
) -> httpx.Response:
    """GET `url`. `total` is the wall-clock budget for the original call and its one retry."""
    getter = _download if get is None else get
    deadline = time.monotonic() + total
    done: queue.Queue[_Attempt] = queue.Queue()
    attempts: list[_Attempt] = []
    try:
        return _hedged(url, deadline, hedge_after, done, attempts, getter)
    finally:
        for attempt in attempts:
            attempt.cancel()
            attempt.join()


def _download(url: str, client: httpx.Client) -> httpx.Response:
    response = client.get(url)
    response.read()
    return response


def _hedged(
    url: str,
    deadline: float,
    hedge_after: float,
    done: queue.Queue[_Attempt],
    attempts: list[_Attempt],
    getter: Getter,
) -> httpx.Response:
    primary = _Attempt(url, deadline, done, getter)
    attempts.append(primary)
    first = _wait(done, min(hedge_after, _remaining(deadline)))
    if first is not None:
        if isinstance(first.outcome, httpx.Response):
            return first.outcome
        if _connection_failure(first.outcome) and _remaining(deadline) > 0:
            backup = _Attempt(url, deadline, done, getter)
            attempts.append(backup)
            return _first_response(done, [backup], deadline)
        if isinstance(first.outcome, BaseException):
            _reraise(first.outcome)
        raise httpx.TimeoutException("census total deadline exceeded")
    if _remaining(deadline) <= 0:
        return _first_response(done, [primary], deadline)
    backup = _Attempt(url, deadline, done, getter)
    attempts.append(backup)
    return _first_response(done, [primary, backup], deadline)


def _first_response(
    done: queue.Queue[_Attempt], pending: list[_Attempt], deadline: float
) -> httpx.Response:
    waiting = set(pending)
    errors: list[BaseException] = []
    while waiting:
        item = _wait(done, _remaining(deadline))
        if item is None:
            break
        if item not in waiting:
            continue
        waiting.remove(item)
        if isinstance(item.outcome, httpx.Response):
            return item.outcome
        if isinstance(item.outcome, BaseException):
            errors.append(item.outcome)
    if errors:
        _reraise(errors[-1])
    raise httpx.TimeoutException("census total deadline exceeded")


def _connection_failure(outcome: object) -> bool:
    if isinstance(outcome, httpx.ConnectTimeout):
        return True
    if isinstance(outcome, httpx.TimeoutException):
        return False
    return isinstance(outcome, (httpx.NetworkError, httpx.ProtocolError))


def _reraise(exc: BaseException) -> NoReturn:
    if not isinstance(exc, httpx.HTTPError):
        raise exc
    cleaned = redact_text(str(exc))
    if cleaned == str(exc):
        raise exc
    try:
        raise type(exc)(cleaned) from None
    except TypeError:
        raise httpx.HTTPError(cleaned) from None


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _wait(done: queue.Queue[_Attempt], seconds: float) -> _Attempt | None:
    try:
        if seconds <= 0:
            return done.get_nowait()
        return done.get(timeout=seconds)
    except queue.Empty:
        return None


class _Attempt:
    def __init__(
        self, url: str, deadline: float, done: queue.Queue[_Attempt], getter: Getter
    ) -> None:
        self.outcome: httpx.Response | BaseException | None = None
        self._url = url
        self._getter = getter
        self._done = done
        # None disables every phase. The timer below is the only deadline.
        self.client = httpx.Client(timeout=None)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.timer = threading.Timer(max(0.0, deadline - time.monotonic()), self.client.close)
        self.timer.daemon = True
        self.thread.start()
        self.timer.start()

    def _run(self) -> None:
        try:
            self.outcome = self._getter(self._url, self.client)
        except BaseException as exc:
            self.outcome = exc
        finally:
            self.timer.cancel()
            self.client.close()
            self._done.put(self)

    def cancel(self) -> None:
        self.timer.cancel()
        self.client.close()

    def join(self) -> None:
        self.thread.join(timeout=1)
