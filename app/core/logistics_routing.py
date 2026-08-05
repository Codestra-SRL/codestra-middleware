"""Provider-neutral routing contracts with a deterministic staging adapter."""

from typing import Protocol


class RoutingProvider(Protocol):
    def calculate_distance(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> float: ...
    def calculate_duration(self, distance_km: float) -> int: ...
    def optimize_stop_order(self, stops: list[tuple[float, float]]) -> list[int]: ...
    def health_check(self) -> bool: ...


class DeterministicMockRoutingProvider:
    """Synthetic-only estimator. Results must never be represented as production ETA."""

    def calculate_distance(
        self, origin: tuple[float, float], destination: tuple[float, float]
    ) -> float:
        return round(
            (abs(origin[0] - destination[0]) + abs(origin[1] - destination[1])) * 111.0,
            2,
        )

    def calculate_duration(self, distance_km: float) -> int:
        return round(distance_km / 50 * 3600)

    def optimize_stop_order(self, stops: list[tuple[float, float]]) -> list[int]:
        return sorted(range(len(stops)), key=lambda i: (stops[i][0], stops[i][1], i))

    def health_check(self) -> bool:
        return True
