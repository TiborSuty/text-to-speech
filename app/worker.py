import logging

import os

from queue import Queue

from threading import Event, Lock, Thread

from collections.abc import Callable

from dataclasses import dataclass


from app.models import AudioRequest


DEFAULT_AUDIO_WORKER_COUNT = 1

MAX_AUDIO_WORKER_COUNT = 8

logger = logging.getLogger(__name__)


def get_audio_worker_count() -> int:

    try:
        worker_count = int(
            os.getenv("AUDIO_WORKER_COUNT", str(DEFAULT_AUDIO_WORKER_COUNT))
        )

    except ValueError:
        return DEFAULT_AUDIO_WORKER_COUNT

    return min(max(worker_count, 1), MAX_AUDIO_WORKER_COUNT)


@dataclass(frozen=True)
class AudioJobTask:
    job_id: str

    request: AudioRequest

    voice: str


class AudioWorkerPool:
    def __init__(
        self,
        processor: Callable[[str, AudioRequest, str], None],
        worker_count: int,
        error_handler: Callable[[str], None] | None = None,
    ):

        self._processor = processor

        self.worker_count = worker_count

        self._error_handler = error_handler

        self._queue: Queue[AudioJobTask | None] = Queue()

        self._lock = Lock()

        self._stop_event = Event()

        self._threads: list[Thread] = []

        self._pending_job_ids: list[str] = []

        self._active_job_ids: set[str] = set()

        self._started = False

    def start(self) -> None:

        with self._lock:
            if self._started:
                return

            self._stop_event.clear()

            work_queue = self._queue

            self._threads = [
                Thread(
                    target=self._worker_loop,
                    args=(work_queue,),
                    name=f"audio-worker-{index + 1}",
                    daemon=True,
                )
                for index in range(self.worker_count)
            ]

            self._started = True

            for thread in self._threads:
                thread.start()

    def submit(self, task: AudioJobTask) -> int:

        self.start()

        with self._lock:
            self._pending_job_ids.append(task.job_id)

            queue_position = len(self._pending_job_ids)

            self._queue.put(task)

        return queue_position

    def cancel_pending(self, job_id: str) -> None:

        with self._lock:
            self._pending_job_ids = [
                pending_job_id
                for pending_job_id in self._pending_job_ids
                if pending_job_id != job_id
            ]

    def queue_position(self, job_id: str) -> int | None:

        with self._lock:
            try:
                return self._pending_job_ids.index(job_id) + 1

            except ValueError:
                return None

    def _worker_loop(self, work_queue: Queue[AudioJobTask | None]) -> None:

        while True:
            task = work_queue.get()

            if task is None:
                work_queue.task_done()

                return

            if self._stop_event.is_set():
                work_queue.task_done()

                return

            with self._lock:
                if task.job_id in self._pending_job_ids:
                    self._pending_job_ids.remove(task.job_id)

                self._active_job_ids.add(task.job_id)

            try:
                self._processor(task.job_id, task.request, task.voice)

            except Exception:
                logger.exception(
                    "Unhandled audio worker failure for job %s", task.job_id
                )

                if self._error_handler is not None:
                    try:
                        self._error_handler(task.job_id)

                    except Exception:
                        logger.exception(
                            "Could not persist worker failure for job %s",
                            task.job_id,
                        )

            finally:
                with self._lock:
                    self._active_job_ids.discard(task.job_id)

                work_queue.task_done()

    def shutdown(self) -> None:

        with self._lock:
            if not self._started:
                return

            self._stop_event.set()

            threads = list(self._threads)

            work_queue = self._queue

            for _thread in threads:
                work_queue.put(None)

        for thread in threads:
            thread.join(timeout=5)

        with self._lock:
            self._queue = Queue()

            self._pending_job_ids = []
            self._active_job_ids = set()

            self._threads = []

            self._started = False
