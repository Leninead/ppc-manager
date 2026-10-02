"""How many turns run at once, and in which order waiting threads get theirs.

The provider queues without limit and the app's own chat shares it, so the bot brakes itself: a few turns at
a time, threads served in arrival order, and a thread that asks again goes to the back of the line.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from services.slack_bot.conversations import Key

log = logging.getLogger(__name__)


class TurnScheduler:
    def __init__(self, workers: int, handle: Callable[[Key], None], clock: Callable[[], float] = time.monotonic):
        self._workers = workers
        self._handle = handle
        self._clock = clock
        self._queue: list[tuple[Key, float]] = []
        self._running: set[Key] = set()
        self._cond = threading.Condition()
        self._threads: list[threading.Thread] = []
        self._stopped = False

    def submit(self, key: Key, delay: float = 0.0) -> None:
        """Queues the thread, or keeps its place and the earlier start if it is already waiting."""
        with self._cond:
            at = self._clock() + delay
            for index, (queued, when) in enumerate(self._queue):
                if queued == key:
                    self._queue[index] = (key, min(when, at))
                    break
            else:
                self._queue.append((key, at))
            self._cond.notify_all()

    def ahead_of(self, key: Key) -> int:
        """Threads waiting before this one."""
        with self._cond:
            return next((index for index, (queued, _) in enumerate(self._queue) if queued == key), len(self._queue))

    def waiting_behind(self, key: Key) -> tuple[int, int] | None:
        """(threads queued ahead, turns running) when this thread will not get a worker right away, else None."""
        with self._cond:
            ahead = next((index for index, (queued, _) in enumerate(self._queue) if queued == key), len(self._queue))
            running = len(self._running)
            return (ahead, running) if ahead + running >= self._workers else None

    def start(self) -> None:
        for index in range(self._workers):
            thread = threading.Thread(target=self._work, name=f"slack-turn-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify_all()

    def _work(self) -> None:
        while True:
            with self._cond:
                key = self._take()
                while key is None and not self._stopped:
                    self._cond.wait(timeout=self._until_next())
                    key = self._take()
                if self._stopped:
                    return
                self._running.add(key)
            try:
                self._handle(key)
            except Exception:  # a worker that dies stops answering every thread
                log.exception("turn for %s failed outside its own handling", key)
            finally:
                with self._cond:
                    self._running.discard(key)
                    self._cond.notify_all()

    def _take(self) -> Key | None:
        now = self._clock()
        for index, (key, at) in enumerate(self._queue):
            if at <= now and key not in self._running:
                self._queue.pop(index)
                return key
        return None

    def _until_next(self) -> float | None:
        waiting = [at for key, at in self._queue if key not in self._running]
        if not waiting:
            return None if not self._queue else 0.5
        return max(min(waiting) - self._clock(), 0.05)
