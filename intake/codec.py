from dataclasses import dataclass
import json


@dataclass(frozen=True)
class DecodedPackage:
    value: object


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate package field: {key}')
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f'invalid JSON number: {token}')


def decode_package(wire: str | bytes) -> DecodedPackage:
    if not isinstance(wire, (str, bytes)):
        raise ValueError('a package must be JSON text or UTF-8 bytes')
    try:
        text = wire.decode('utf-8') if isinstance(wire, bytes) else wire
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_nonfinite)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid station package JSON') from exc
    return DecodedPackage(value)


def canonical_content(decoded: DecodedPackage) -> str:
    return json.dumps(decoded.value, sort_keys=True, separators=(',', ':'), allow_nan=False)
