from typing import Literal

Environment = Literal["prod", "testnet", "nightly"]

PROD: Environment = "prod"
TESTNET: Environment = "testnet"
NIGHTLY: Environment = "nightly"

_VALID_ENVS = frozenset({"prod", "testnet", "nightly"})


def _validate_env(env: object, classname: str) -> None:
    """Raise ``ValueError`` when *env* is not a valid :data:`Environment` string."""
    if not isinstance(env, str) or env not in _VALID_ENVS:
        raise ValueError(f"{classname}: Invalid environment {env!r}. Valid values: {sorted(_VALID_ENVS)!r}.")
