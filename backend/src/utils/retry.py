"""Retry utility with exponential backoff.

Provides retry logic for external API calls that may fail transiently.
Used by Gemini, TTS, and image generation services.
"""

import logging
import random
import time
from functools import wraps
from typing import Callable, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_EXPONENTIAL_BASE = 2


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (not counting initial attempt)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        retryable_exceptions: Tuple of exception types that should trigger retry
        on_retry: Optional callback called on each retry with (exception, attempt_number)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed, re-raise
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    # Calculate delay with jitter
                    delay = min(
                        base_delay * (exponential_base**attempt),
                        max_delay,
                    )
                    # Add jitter (±25%) to prevent thundering herd
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    delay = max(0.1, delay + jitter)

                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(delay)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def retry_call(
    func: Callable[..., T],
    *args,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    context: str = "",
    **kwargs,
) -> T:
    """Call a function with retry logic.

    This is a non-decorator version for use with methods or lambdas.

    Args:
        func: Function to call
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        retryable_exceptions: Exception types that trigger retry
        context: Context string for logging (e.g., job_id)
        **kwargs: Keyword arguments to pass to func

    Returns:
        Result of func(*args, **kwargs)
    """
    last_exception = None
    log_prefix = f"[{context}] " if context else ""

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"{log_prefix}Operation failed after {max_retries + 1} attempts: {e}"
                )
                raise

            # Calculate delay with jitter
            delay = min(
                base_delay * (exponential_base**attempt),
                max_delay,
            )
            jitter = delay * 0.25 * (2 * random.random() - 1)
            delay = max(0.1, delay + jitter)

            logger.warning(
                f"{log_prefix}Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                f"Retrying in {delay:.2f}s..."
            )

            time.sleep(delay)

    if last_exception:
        raise last_exception
