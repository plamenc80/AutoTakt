"""Регистрационни номера и VIN."""
import re
from dataclasses import dataclass

# Латинските букви, които приличат на кирилски - за номера, въведени на латиница.
LATIN_TO_CYRILLIC = str.maketrans("ABEKMHOPCTYX", "АВЕКМНОРСТУХ")
STANDARD = re.compile(r"^([А-Я]{1,2})\s*(\d{4})\s*([А-Я]{2})$")


def normalize_plate(plate):
    """„ch1234ab“ → „СН 1234 АВ“: главни букви, кирилица и стандартен формат с интервали."""
    cleaned = " ".join((plate or "").strip().upper().translate(LATIN_TO_CYRILLIC).split())
    match = STANDARD.match(cleaned)
    return f"{match[1]} {match[2]} {match[3]}" if match else cleaned


@dataclass
class VinCheck:
    is_valid_format: bool
    check_digit_valid: bool | None
    make: str | None


ALLOWED = set("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")  # без I, O и Q

# Производител по първите 3 символа (World Manufacturer Identifier) - най-честите в България.
WMI = {
    "WVW": "Volkswagen", "WV1": "Volkswagen", "WV2": "Volkswagen", "WAU": "Audi", "WUA": "Audi",
    "WBA": "BMW", "WBS": "BMW", "WDB": "Mercedes-Benz", "WDD": "Mercedes-Benz", "W1K": "Mercedes-Benz",
    "WDC": "Mercedes-Benz", "WME": "Smart", "VSS": "Seat", "TMB": "Skoda", "VF1": "Renault",
    "VF3": "Peugeot", "VR3": "Peugeot", "VF7": "Citroën", "UU1": "Dacia", "ZFA": "Fiat",
    "ZAR": "Alfa Romeo", "W0L": "Opel", "W0V": "Opel", "WF0": "Ford", "SAJ": "Jaguar",
    "SAL": "Land Rover", "YV1": "Volvo", "KMH": "Hyundai", "TMA": "Hyundai", "KNA": "Kia",
    "KNE": "Kia", "U5Y": "Kia", "JTD": "Toyota", "JTE": "Toyota", "SB1": "Toyota",
    "VNK": "Toyota", "JN1": "Nissan", "SJN": "Nissan", "VSK": "Nissan", "JMZ": "Mazda",
    "JHM": "Honda", "SHH": "Honda", "JS2": "Suzuki", "TSM": "Suzuki", "WP0": "Porsche",
    "WP1": "Porsche", "JF1": "Subaru", "JMB": "Mitsubishi", "XP7": "Tesla", "5YJ": "Tesla",
    "WMW": "Mini",
}

# Тегла на позициите за контролната цифра (позиция 9) по ISO 3779.
WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
TRANSLITERATION = {**{str(d): d for d in range(10)},
                   **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
                   **dict(zip("STUVWXYZ", range(2, 10)))}


def check_vin(vin):
    """
    Проверка на VIN без външна услуга: формат, контролна цифра (в Европа не е задължителна -
    само предупреждение) и марка по първите 3 символа. Безплатните декодери почти не работят за европейски коли.
    """
    value = (vin or "").strip().upper()
    if len(value) != 17 or any(c not in ALLOWED for c in value):
        return VinCheck(False, None, None)
    total = sum(TRANSLITERATION[c] * w for c, w in zip(value, WEIGHTS))
    expected = "X" if total % 11 == 10 else str(total % 11)
    return VinCheck(True, value[8] == expected, WMI.get(value[:3]))


def make_matches(wmi_make, entered_make):
    """Съвпада ли марката от VIN с въведената (VW = Volkswagen)."""
    if not wmi_make or not entered_make or not entered_make.strip():
        return True

    def norm(s):
        return s.strip().lower().replace("vw", "volkswagen").replace("-", " ")
    return norm(wmi_make) == norm(entered_make)
