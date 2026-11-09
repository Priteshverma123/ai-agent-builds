"""A simulated travel-booking world and the tools the agent can call on it.

The world is deterministic: the cheapest Lisbon hotel is always sold out, so the
first plan always fails at the same step and the agent has to re-plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ToolError(Exception):
    """A tool failed in a way the planner should hear about (sold out, bad input...)."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params: dict[str, str]
    fn: Callable[..., Any]

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "params": self.params}


FLIGHTS = {
    ("London", "Lisbon"): [
        {"id": "FL-TP1351", "airline": "TAP", "departs": "07:05", "price": 142},
        {"id": "FL-BA500", "airline": "British Airways", "departs": "09:40", "price": 189},
    ],
}
HOTELS = {
    "Lisbon": [
        {"id": "H-ALFAMA", "name": "Alfama Patio Hotel", "price_per_night": 95},
        {"id": "H-BAIXA", "name": "Baixa House", "price_per_night": 118},
        {"id": "H-AVENIDA", "name": "Avenida Palace", "price_per_night": 210},
    ],
}
SOLD_OUT = {"H-ALFAMA"}


@dataclass
class TravelWorld:
    """Holds bookings and spend so tests can inspect side effects."""

    bookings: list[dict] = field(default_factory=list)
    sent: list[dict] = field(default_factory=list)

    @property
    def spend(self) -> int:
        return sum(b["price"] for b in self.bookings)

    def search_flights(self, origin: str, destination: str, date: str) -> list[dict]:
        flights = FLIGHTS.get((origin, destination), [])
        if not flights:
            raise ToolError(f"no flights from {origin} to {destination}")
        return sorted(flights, key=lambda f: f["price"])

    def book_flight(self, flight_id: str) -> dict:
        flight = next((f for fs in FLIGHTS.values() for f in fs if f["id"] == flight_id), None)
        if flight is None:
            raise ToolError(f"unknown flight {flight_id}")
        booking = {"confirmation": f"CONF-{flight_id}", "what": f"{flight['airline']} {flight['departs']}", "price": flight["price"]}
        self.bookings.append(booking)
        return booking

    def search_hotels(self, city: str, check_in: str, nights: int, exclude: list[str] | None = None) -> list[dict]:
        hotels = [h for h in HOTELS.get(city, []) if h["id"] not in (exclude or [])]
        return sorted(hotels, key=lambda h: h["price_per_night"])

    def book_hotel(self, hotel_id: str, nights: int) -> dict:
        hotel = next((h for hs in HOTELS.values() for h in hs if h["id"] == hotel_id), None)
        if hotel is None:
            raise ToolError(f"unknown hotel {hotel_id}")
        if hotel_id in SOLD_OUT:
            raise ToolError(f"{hotel['name']} is sold out for those dates")
        booking = {"confirmation": f"CONF-{hotel_id}", "what": f"{hotel['name']} x{nights} nights",
                   "price": hotel["price_per_night"] * nights}
        self.bookings.append(booking)
        return booking

    def send_itinerary(self, to: str, confirmations: list[str]) -> dict:
        if "@" not in to:
            raise ToolError(f"invalid email {to!r}")
        self.sent.append({"to": to, "confirmations": confirmations})
        return {"sent_to": to, "items": len(confirmations), "total_eur": self.spend}

    def tools(self) -> dict[str, ToolSpec]:
        specs = [
            ToolSpec("search_flights", "List flights, cheapest first.", {"origin": "str", "destination": "str", "date": "YYYY-MM-DD"}, self.search_flights),
            ToolSpec("book_flight", "Book a flight by id.", {"flight_id": "str"}, self.book_flight),
            ToolSpec("search_hotels", "List hotels, cheapest first; skip ids in exclude.",
                     {"city": "str", "check_in": "YYYY-MM-DD", "nights": "int", "exclude": "list[str] (optional)"}, self.search_hotels),
            ToolSpec("book_hotel", "Book a hotel by id. Fails if sold out.", {"hotel_id": "str", "nights": "int"}, self.book_hotel),
            ToolSpec("send_itinerary", "Email booking confirmations.", {"to": "email", "confirmations": "list[str]"}, self.send_itinerary),
        ]
        return {s.name: s for s in specs}
