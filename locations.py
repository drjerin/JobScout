"""Curated country + city catalog for the setup wizard.

Each country entry defines:
- ``emoji``          — flag shown in the email digest and dashboard
- ``adzuna_country`` — Adzuna's ISO code (``None`` if unsupported)
- ``indeed_country`` — the label JobSpy expects for Indeed / LinkedIn routing
- ``cities``         — a short list of common metros; users can add more via
                        the setup wizard's free-text field

The catalog is intentionally hand-curated and small. It exists so the wizard
can offer a friendly picker for the most common cases; users are always free
to type any city they want or edit ``config.yaml`` directly afterwards.
"""
from __future__ import annotations


COUNTRIES: dict[str, dict] = {
    "India": {
        "emoji": "🇮🇳",
        "adzuna_country": "in",
        "indeed_country": "India",
        "cities": [
            "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai",
            "Pune", "Kolkata", "Gurugram", "Noida", "Ahmedabad", "Kochi",
        ],
    },
    "United States": {
        "emoji": "🇺🇸",
        "adzuna_country": "us",
        "indeed_country": "USA",
        "cities": [
            "New York", "San Francisco", "Los Angeles", "Chicago", "Boston",
            "Seattle", "Austin", "Denver", "Washington", "Atlanta",
            "Dallas", "Houston", "Remote",
        ],
    },
    "United Kingdom": {
        "emoji": "🇬🇧",
        "adzuna_country": "gb",
        "indeed_country": "UK",
        "cities": ["London", "Manchester", "Birmingham", "Leeds", "Edinburgh",
                   "Glasgow", "Bristol", "Cambridge", "Remote"],
    },
    "Canada": {
        "emoji": "🇨🇦",
        "adzuna_country": "ca",
        "indeed_country": "Canada",
        "cities": ["Toronto", "Vancouver", "Montreal", "Calgary", "Ottawa", "Remote"],
    },
    "Germany": {
        "emoji": "🇩🇪",
        "adzuna_country": "de",
        "indeed_country": "Germany",
        "cities": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Stuttgart",
                   "Düsseldorf", "Cologne", "Remote"],
    },
    "France": {
        "emoji": "🇫🇷",
        "adzuna_country": "fr",
        "indeed_country": "France",
        "cities": ["Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Remote"],
    },
    "Netherlands": {
        "emoji": "🇳🇱",
        "adzuna_country": "nl",
        "indeed_country": "Netherlands",
        "cities": ["Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven"],
    },
    "Ireland": {
        "emoji": "🇮🇪",
        "adzuna_country": None,
        "indeed_country": "Ireland",
        "cities": ["Dublin", "Cork", "Galway", "Limerick"],
    },
    "Spain": {
        "emoji": "🇪🇸",
        "adzuna_country": "es",
        "indeed_country": "Spain",
        "cities": ["Madrid", "Barcelona", "Valencia", "Seville"],
    },
    "Italy": {
        "emoji": "🇮🇹",
        "adzuna_country": "it",
        "indeed_country": "Italy",
        "cities": ["Milan", "Rome", "Turin", "Bologna"],
    },
    "Poland": {
        "emoji": "🇵🇱",
        "adzuna_country": "pl",
        "indeed_country": "Poland",
        "cities": ["Warsaw", "Krakow", "Wroclaw", "Gdansk"],
    },
    "Switzerland": {
        "emoji": "🇨🇭",
        "adzuna_country": "ch",
        "indeed_country": "Switzerland",
        "cities": ["Zurich", "Geneva", "Basel", "Bern"],
    },
    "Sweden": {
        "emoji": "🇸🇪",
        "adzuna_country": None,
        "indeed_country": "Sweden",
        "cities": ["Stockholm", "Gothenburg", "Malmö"],
    },
    "Austria": {
        "emoji": "🇦🇹",
        "adzuna_country": "at",
        "indeed_country": "Austria",
        "cities": ["Vienna", "Graz", "Linz", "Salzburg"],
    },
    "Belgium": {
        "emoji": "🇧🇪",
        "adzuna_country": "be",
        "indeed_country": "Belgium",
        "cities": ["Brussels", "Antwerp", "Ghent"],
    },
    "Australia": {
        "emoji": "🇦🇺",
        "adzuna_country": "au",
        "indeed_country": "Australia",
        "cities": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Remote"],
    },
    "New Zealand": {
        "emoji": "🇳🇿",
        "adzuna_country": "nz",
        "indeed_country": "New Zealand",
        "cities": ["Auckland", "Wellington", "Christchurch"],
    },
    "Singapore": {
        "emoji": "🇸🇬",
        "adzuna_country": "sg",
        "indeed_country": "Singapore",
        "cities": ["Singapore"],
    },
    "United Arab Emirates": {
        "emoji": "🇦🇪",
        "adzuna_country": "ae",
        "indeed_country": "UAE",
        "cities": ["Dubai", "Abu Dhabi", "Sharjah"],
    },
    "Qatar": {
        "emoji": "🇶🇦",
        "adzuna_country": None,
        "indeed_country": "Qatar",
        "cities": ["Doha"],
    },
    "Saudi Arabia": {
        "emoji": "🇸🇦",
        "adzuna_country": None,
        "indeed_country": "Saudi Arabia",
        "cities": ["Riyadh", "Jeddah", "Dammam"],
    },
    "South Africa": {
        "emoji": "🇿🇦",
        "adzuna_country": "za",
        "indeed_country": "South Africa",
        "cities": ["Johannesburg", "Cape Town", "Pretoria", "Durban"],
    },
    "Brazil": {
        "emoji": "🇧🇷",
        "adzuna_country": "br",
        "indeed_country": "Brazil",
        "cities": ["São Paulo", "Rio de Janeiro", "Brasília"],
    },
    "Mexico": {
        "emoji": "🇲🇽",
        "adzuna_country": "mx",
        "indeed_country": "Mexico",
        "cities": ["Mexico City", "Guadalajara", "Monterrey"],
    },
    "Japan": {
        "emoji": "🇯🇵",
        "adzuna_country": None,
        "indeed_country": "Japan",
        "cities": ["Tokyo", "Osaka", "Yokohama"],
    },
}


def country_names() -> list[str]:
    """Alphabetized list of supported country names."""
    return sorted(COUNTRIES.keys())


def country_meta(name: str) -> dict:
    """Return the metadata for a country, or an empty dict if unknown."""
    return COUNTRIES.get(name, {})


def build_country_block(name: str, cities: list[str]) -> dict:
    """Build a ``config.yaml`` country entry from wizard input.

    ``cities`` is a list of bare city names (e.g. ["Bengaluru", "Mumbai"]);
    they're joined with the country name to match the format the sources expect.
    """
    meta = country_meta(name)
    return {
        "enabled": bool(cities),
        "emoji": meta.get("emoji", ""),
        "locations": [f"{c}, {name}" for c in cities if c.strip()],
        "adzuna_country": meta.get("adzuna_country"),
        "indeed_country": meta.get("indeed_country", name),
    }
