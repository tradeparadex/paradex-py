import random
import time


def random_max_fee(start: int = 10**18, end: int = 10**19) -> int:
    return random.randint(start, end)


def time_now_milli_secs() -> int:
    return int(time.time() * 1_000)


def time_now_micro_secs() -> int:
    return int(time.time() * 1_000_000)
