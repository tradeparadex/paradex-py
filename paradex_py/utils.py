import secrets
import time


def random_max_fee(start: int = 10**18, end: int = 10**19) -> int:
    return secrets.randbelow(end - start + 1) + start


def time_now_milli_secs() -> int:
    return int(time.time() * 1_000)


def time_now_micro_secs() -> int:
    return int(time.time() * 1_000_000)


def raise_value_error(message: str):
    raise ValueError(message)
