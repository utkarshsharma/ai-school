"""Job queue implementation with Redis and in-memory fallback.

This module provides a unified queue interface that:
- Uses Redis when available (production)
- Falls back to in-memory queue when Redis is unavailable (development)
- Supports job messages for both new jobs and resume requests
"""

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from queue import Queue
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class QueueBackend(str, Enum):
    """Queue backend type."""
    REDIS = "redis"
    MEMORY = "memory"


@dataclass
class JobMessage:
    """Message representing a job to process.

    Attributes:
        job_id: The job ID to process
        action: 'process' for new jobs, 'resume' for resuming failed jobs
        from_stage: For resume actions, the stage to resume from
    """
    job_id: str
    action: str = "process"  # 'process' or 'resume'
    from_stage: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "job_id": self.job_id,
            "action": self.action,
            "from_stage": self.from_stage,
        })

    @classmethod
    def from_json(cls, data: str) -> "JobMessage":
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(
            job_id=parsed["job_id"],
            action=parsed.get("action", "process"),
            from_stage=parsed.get("from_stage"),
        )


class JobQueue:
    """Unified job queue with Redis and in-memory fallback.

    The queue automatically detects Redis availability and falls back
    to in-memory when Redis is not available. This allows development
    without Redis while using Redis in production.
    """

    QUEUE_NAME = "ai_school:jobs"

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the job queue.

        Args:
            redis_url: Redis connection URL. If None, uses REDIS_URL env var.
                      Falls back to in-memory if Redis is unavailable.
        """
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client: Optional["redis.Redis"] = None
        self._memory_queue: Queue[JobMessage] = Queue()
        self._backend: QueueBackend = QueueBackend.MEMORY

        # Try to connect to Redis
        if self._redis_url:
            self._try_connect_redis()
        else:
            logger.info("No REDIS_URL configured, using in-memory queue")

    def _try_connect_redis(self) -> bool:
        """Attempt to connect to Redis.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            import redis

            self._redis_client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self._redis_client.ping()
            self._backend = QueueBackend.REDIS
            logger.info(f"Connected to Redis at {self._redis_url}")
            return True
        except ImportError:
            logger.warning("redis package not installed, using in-memory queue")
            return False
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory queue")
            self._redis_client = None
            self._backend = QueueBackend.MEMORY
            return False

    @property
    def backend(self) -> QueueBackend:
        """Get the current queue backend type."""
        return self._backend

    def enqueue(self, message: JobMessage) -> bool:
        """Add a job message to the queue.

        Args:
            message: Job message to enqueue

        Returns:
            True if enqueued successfully, False otherwise
        """
        if self._backend == QueueBackend.REDIS and self._redis_client:
            try:
                self._redis_client.lpush(self.QUEUE_NAME, message.to_json())
                logger.debug(f"Enqueued to Redis: {message.job_id} ({message.action})")
                return True
            except Exception as e:
                logger.error(f"Redis enqueue failed: {e}. Falling back to memory queue")
                # Fall back to memory queue
                self._backend = QueueBackend.MEMORY
                self._memory_queue.put(message)
                return True
        else:
            self._memory_queue.put(message)
            logger.debug(f"Enqueued to memory: {message.job_id} ({message.action})")
            return True

    def dequeue(self, timeout: int = 0) -> Optional[JobMessage]:
        """Get the next job message from the queue.

        Args:
            timeout: Seconds to wait for a message. 0 = block forever.

        Returns:
            JobMessage if available, None on timeout or error
        """
        if self._backend == QueueBackend.REDIS and self._redis_client:
            try:
                # BRPOP blocks until a message is available
                result = self._redis_client.brpop(self.QUEUE_NAME, timeout=timeout or 0)
                if result:
                    _, data = result
                    return JobMessage.from_json(data)
                return None
            except Exception as e:
                logger.error(f"Redis dequeue failed: {e}. Falling back to memory queue")
                self._backend = QueueBackend.MEMORY
                # Fall through to memory queue

        # Memory queue
        try:
            if timeout == 0:
                # Block forever
                return self._memory_queue.get()
            else:
                return self._memory_queue.get(timeout=timeout)
        except Exception:
            return None

    def size(self) -> int:
        """Get the number of messages in the queue.

        Returns:
            Queue size, or -1 if unavailable
        """
        if self._backend == QueueBackend.REDIS and self._redis_client:
            try:
                return self._redis_client.llen(self.QUEUE_NAME)
            except Exception:
                return -1
        else:
            return self._memory_queue.qsize()

    def clear(self) -> None:
        """Clear all messages from the queue."""
        if self._backend == QueueBackend.REDIS and self._redis_client:
            try:
                self._redis_client.delete(self.QUEUE_NAME)
            except Exception as e:
                logger.error(f"Redis clear failed: {e}")
        else:
            while not self._memory_queue.empty():
                try:
                    self._memory_queue.get_nowait()
                except Exception:
                    break

    def health_check(self) -> dict:
        """Check queue health status.

        Returns:
            Dict with backend type, connectivity status, and queue size
        """
        status = {
            "backend": self._backend.value,
            "connected": False,
            "size": -1,
        }

        if self._backend == QueueBackend.REDIS and self._redis_client:
            try:
                self._redis_client.ping()
                status["connected"] = True
                status["size"] = self._redis_client.llen(self.QUEUE_NAME)
            except Exception:
                status["connected"] = False
        else:
            status["connected"] = True  # Memory queue is always available
            status["size"] = self._memory_queue.qsize()

        return status


# Global queue instance
_queue_instance: Optional[JobQueue] = None
_queue_lock = threading.Lock()


def get_job_queue() -> JobQueue:
    """Get the global job queue instance.

    Creates the instance on first call (singleton pattern).
    """
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = JobQueue()
    return _queue_instance


def enqueue_job(job_id: str) -> None:
    """Add a new job to the processing queue.

    Args:
        job_id: Job ID to process
    """
    queue = get_job_queue()
    message = JobMessage(job_id=job_id, action="process")
    queue.enqueue(message)
    logger.info(f"Enqueued job: {job_id}")


def enqueue_resume(job_id: str, from_stage: str) -> None:
    """Add a job resume request to the queue.

    Args:
        job_id: Job ID to resume
        from_stage: Stage to resume from ('images', 'tts', or 'render')
    """
    queue = get_job_queue()
    message = JobMessage(job_id=job_id, action="resume", from_stage=from_stage)
    queue.enqueue(message)
    logger.info(f"Enqueued resume: {job_id} from stage {from_stage}")


def get_next_job() -> Optional[JobMessage]:
    """Get the next job message from the queue.

    Blocks until a message is available.

    Returns:
        JobMessage to process
    """
    queue = get_job_queue()
    return queue.dequeue()


# Worker thread pool management
_worker_pool: Optional[ThreadPoolExecutor] = None
_worker_threads: list[threading.Thread] = []
_pool_lock = threading.Lock()

# Configurable worker count via environment variable
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "4"))


def start_worker(processor_func: Callable[[JobMessage], None], num_workers: int = None) -> None:
    """Start the background worker thread pool.

    Spawns multiple worker threads that process jobs concurrently.
    Each worker independently pulls jobs from the queue.

    Args:
        processor_func: Function to call for each job message.
                       Signature: (JobMessage) -> None
        num_workers: Number of worker threads. Defaults to WORKER_COUNT env var (4).
    """
    global _worker_pool, _worker_threads
    num_workers = num_workers or WORKER_COUNT

    with _pool_lock:
        # Check if workers are already running
        active_workers = sum(1 for t in _worker_threads if t.is_alive())
        if active_workers >= num_workers:
            return

        # Start new workers up to the desired count
        workers_to_start = num_workers - active_workers
        queue = get_job_queue()

        for i in range(workers_to_start):
            worker_id = len(_worker_threads) + 1
            thread = threading.Thread(
                target=_worker_loop,
                args=(processor_func, worker_id),
                daemon=True,
                name=f"worker-{worker_id}",
            )
            thread.start()
            _worker_threads.append(thread)

        logger.info(
            f"Started {workers_to_start} worker(s), "
            f"total active: {num_workers} (backend: {queue.backend.value})"
        )


def _worker_loop(processor_func: Callable[[JobMessage], None], worker_id: int = 1) -> None:
    """Main worker loop - processes jobs from queue.

    Each worker independently pulls jobs and processes them.
    Multiple workers enable concurrent job processing.

    Args:
        processor_func: Function to call for each job message
        worker_id: Identifier for this worker (for logging)
    """
    logger.info(f"[Worker-{worker_id}] Started and waiting for jobs")
    while True:
        try:
            message = get_next_job()
            if message:
                logger.info(f"[Worker-{worker_id}] Processing: {message.job_id} ({message.action})")
                processor_func(message)
                logger.info(f"[Worker-{worker_id}] Completed: {message.job_id}")
        except Exception as e:
            logger.error(f"[Worker-{worker_id}] Error: {e}", exc_info=True)


def get_worker_count() -> int:
    """Get the number of active worker threads."""
    return sum(1 for t in _worker_threads if t.is_alive())
