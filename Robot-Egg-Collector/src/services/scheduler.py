"""Command scheduler emitting timer events."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict

from .event_bus import EventBus
from .events import TimerEvent, TimerId

logger = logging.getLogger("services.scheduler")


@dataclass
class _BaseTask:
    timer_id: TimerId
    callback: Callable[[], None]
    thread: threading.Thread
    stop_event: threading.Event

    def cancel(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1.0)


class CommandScheduler:
    """Manages recurring and one-shot timers publishing events on the bus."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._tasks: Dict[TimerId, _BaseTask] = {}
        self._lock = threading.Lock()

    def start_interval(self, timer_id: TimerId, interval_s: float) -> None:
        with self._lock:
            self.cancel(timer_id)
            stop_event = threading.Event()

            def _run() -> None:
                logger.info("Timer %s started (interval %.3fs)", timer_id.value, interval_s)
                while not stop_event.wait(interval_s):
                    self._bus.publish(TimerEvent(timer_id=timer_id))
                logger.info("Timer %s stopped.", timer_id.value)

            task = _BaseTask(
                timer_id=timer_id,
                callback=lambda: None,
                stop_event=stop_event,
                thread=threading.Thread(target=_run, name=f"Timer-{timer_id.value}", daemon=True),
            )
            self._tasks[timer_id] = task
            task.thread.start()

    def schedule_once(self, timer_id: TimerId, delay_s: float) -> None:
        with self._lock:
            self.cancel(timer_id)
            stop_event = threading.Event()

            def _run() -> None:
                logger.debug("Timeout %s scheduled in %.3fs", timer_id.value, delay_s)
                if not stop_event.wait(delay_s):
                    self._bus.publish(TimerEvent(timer_id=timer_id))
                logger.debug("Timeout %s completed.", timer_id.value)

            task = _BaseTask(
                timer_id=timer_id,
                callback=lambda: None,
                stop_event=stop_event,
                thread=threading.Thread(target=_run, name=f"Timeout-{timer_id.value}", daemon=True),
            )
            self._tasks[timer_id] = task
            task.thread.start()

    def cancel(self, timer_id: TimerId) -> None:
        with self._lock:
            task = self._tasks.pop(timer_id, None)
        if task:
            task.cancel()

    def shutdown(self) -> None:
        with self._lock:
            timer_ids = list(self._tasks.keys())
        for timer_id in timer_ids:
            self.cancel(timer_id)
