import secrets
import time

from starknet_py.net.client_models import ResourceBounds, ResourceBoundsMapping

l1_gas_max_amount = 10000000
l1_gas_max_price_per_unit = 10000000000
l1_data_gas_max_amount = 10000000
l1_data_gas_max_price_per_unit = 10000000000
l2_gas_max_amount = 100000000
l2_gas_max_price_per_unit = 10000000000


def random_resource_bounds(randomized_factor: int = 100000) -> ResourceBoundsMapping:
    randomized = secrets.randbelow(randomized_factor)
    return ResourceBoundsMapping(
        l1_gas=ResourceBounds(
            max_amount=l1_gas_max_amount + randomized,
            max_price_per_unit=l1_gas_max_price_per_unit,
        ),
        l1_data_gas=ResourceBounds(
            max_amount=l1_data_gas_max_amount + randomized,
            max_price_per_unit=l1_data_gas_max_price_per_unit,
        ),
        l2_gas=ResourceBounds(
            max_amount=l2_gas_max_amount + randomized,
            max_price_per_unit=l2_gas_max_price_per_unit,
        ),
    )


def time_now_milli_secs() -> int:
    return int(time.time() * 1_000)


def time_now_micro_secs() -> int:
    return int(time.time() * 1_000_000)


def raise_value_error(message: str):
    raise ValueError(message)
