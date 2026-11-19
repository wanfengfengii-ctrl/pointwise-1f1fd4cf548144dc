from dataclasses import dataclass
import re

_IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}')
MAX_PUBLIC_TERMINALS = 6
MAX_LOCAL_CONTACTS = 6


@dataclass(frozen=True)
class PublicCatalog:
    trial_id: str
    stations: tuple[str, str]
    terminals: tuple[str, ...]


@dataclass(frozen=True)
class EndpointRef:
    scope: str
    name: str
    station_id: str | None = None


def require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f'invalid {field}')
    return value


def build_catalog(trial_id: str, stations: list[str] | tuple[str, ...],
                  terminals: list[str] | tuple[str, ...]) -> PublicCatalog:
    trial = require_identifier(trial_id, 'trial identifier')
    if not isinstance(stations, (tuple, list)) or len(stations) != 2:
        raise ValueError('a trial requires exactly two stations')
    first, second = (require_identifier(item, 'station identifier') for item in stations)
    if first == second:
        raise ValueError('station identifiers must differ')
    if not isinstance(terminals, (tuple, list)) or not (1 <= len(terminals) <= MAX_PUBLIC_TERMINALS):
        raise ValueError('a trial requires one to six public terminals')
    names = tuple(require_identifier(item, 'public terminal') for item in terminals)
    if len(set(names)) != len(names):
        raise ValueError('public terminal identifiers must be unique')
    return PublicCatalog(trial, (first, second), names)


def resolve_endpoint(catalog: PublicCatalog, station_id: str, endpoint: EndpointRef) -> EndpointRef:
    if station_id not in catalog.stations:
        raise ValueError('station is outside the trial')
    if not isinstance(endpoint, EndpointRef):
        raise ValueError('an endpoint reference is required')
    require_identifier(endpoint.name, 'endpoint identifier')
    if endpoint.scope == 'public' and endpoint.station_id is None and endpoint.name in catalog.terminals:
        return endpoint
    if endpoint.scope == 'local' and endpoint.station_id == station_id:
        return endpoint
    raise ValueError('endpoint is outside the public catalog or the station')


def public_state_index(bits: tuple[int, ...] | list[int]) -> int:
    index = 0
    for bit in bits:
        if type(bit) is not int or bit not in (0, 1):
            raise ValueError('public state must contain integer bits')
        index = (index << 1) | bit
    return index
