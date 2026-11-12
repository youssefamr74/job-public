"""Cities and countries that show up in job emails and are never an employer's name.

Names are compared lowercase and without diacritics, so "Kraków", "Krakow" and "krakow" are the same."""

import unicodedata

_PL_CITIES = {
    "warszawa", "warsaw", "krakow", "cracow", "wroclaw", "poznan", "gdansk", "gdynia", "sopot", "tricity",
    "trojmiasto", "lodz", "katowice", "szczecin", "lublin", "bialystok", "bydgoszcz", "torun", "rzeszow",
    "kielce", "olsztyn", "opole", "gliwice", "zabrze", "radom", "czestochowa", "plock", "gorzow", "zielona gora",
    "kalisz", "elblag", "tychy", "rybnik", "bielsko biala", "nowy sacz", "tarnow", "slupsk", "koszalin",
}
_WORLD_CITIES = {
    "london", "berlin", "paris", "madrid", "barcelona", "lisbon", "porto", "rome", "milan", "amsterdam",
    "rotterdam", "brussels", "dublin", "cork", "prague", "brno", "vienna", "munich", "hamburg", "frankfurt",
    "cologne", "stuttgart", "dusseldorf", "zurich", "geneva", "stockholm", "gothenburg", "oslo", "copenhagen",
    "helsinki", "budapest", "bucharest", "sofia", "belgrade", "zagreb", "athens", "istanbul", "kyiv", "kiev",
    "lviv", "vilnius", "riga", "tallinn", "bratislava", "cairo", "alexandria", "giza", "dubai", "abu dhabi",
    "riyadh", "tel aviv", "new york", "san francisco", "los angeles", "seattle", "boston", "chicago", "austin",
    "toronto", "vancouver", "montreal", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi",
    "singapore", "sydney", "melbourne", "tokyo", "manchester", "edinburgh", "glasgow", "birmingham", "bristol",
    "leeds", "remote", "hybrid", "worldwide", "emea", "europe",
}
_COUNTRIES = {
    "poland", "polska", "germany", "deutschland", "united kingdom", "uk", "great britain", "england", "scotland",
    "ireland", "france", "spain", "portugal", "italy", "netherlands", "belgium", "austria", "switzerland",
    "sweden", "norway", "denmark", "finland", "czechia", "czech republic", "slovakia", "hungary", "romania",
    "bulgaria", "serbia", "croatia", "greece", "turkey", "ukraine", "lithuania", "latvia", "estonia", "egypt",
    "united arab emirates", "uae", "saudi arabia", "israel", "usa", "us", "united states", "canada", "india",
    "australia", "japan", "mexico", "brazil",
}
PLACES = _PL_CITIES | _WORLD_CITIES | _COUNTRIES


def fold(text: str) -> str:
    """Lowercase, no diacritics, single spaces."""
    text = (text or "").lower().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace("-", " ").split())


def is_place(name: str) -> bool:
    """A city or country, or a list of them such as "Warsaw, Poland"."""
    parts = [fold(p) for p in (name or "").replace("/", ",").split(",")]
    parts = [p for p in parts if p]
    return bool(parts) and all(p in PLACES for p in parts)
