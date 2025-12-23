"""Job queue module with Redis support and in-memory fallback."""

from src.queue.job_queue import (
    JobQueue,
    get_job_queue,
    enqueue_job,
    enqueue_resume,
    get_next_job,
    start_worker,
    get_worker_count,
    QueueBackend,
    WORKER_COUNT,
)

__all__ = [
    "JobQueue",
    "get_job_queue",
    "enqueue_job",
    "enqueue_resume",
    "get_next_job",
    "start_worker",
    "get_worker_count",
    "QueueBackend",
    "WORKER_COUNT",
]
