"""
Демонстрационни двигатели с изисквания за течности и течностите в склада.
Стойностите са типични, но служат само за демонстрация - в реален сервиз идват от каталог (напр. TecDoc).
"""
from decimal import Decimal as D

from data.models import FluidKind, FuelType, PartUnit, Transmission

VAG = "Volkswagen, VW, Skoda, Seat, Audi, Cupra"


def oil(viscosity, approvals, litres):
    return {"kind": FluidKind.ENGINE_OIL, "viscosity": viscosity, "approvals": approvals, "capacity_litres": D(litres)}


def dsg(litres):
    return {"kind": FluidKind.TRANSMISSION_FLUID, "transmission": Transmission.DUAL_CLUTCH,
            "approvals": "VW TL 052 182", "capacity_litres": D(litres)}


def automatic(approvals, litres):
    return {"kind": FluidKind.TRANSMISSION_FLUID, "transmission": Transmission.AUTOMATIC,
            "approvals": approvals, "capacity_litres": D(litres)}


# (марки, име, код, гориво, куб. см, kW, [течности])
ENGINES = [
    (VAG, "1.6 TDI", "CAYC", FuelType.DIESEL, 1598, 77, [oil("5W-30", "VW 507.00", "4.3"), dsg("5.2")]),
    (VAG, "2.0 TDI", "CFFB", FuelType.DIESEL, 1968, 103, [oil("5W-30", "VW 507.00", "4.6"), dsg("5.2")]),
    (VAG, "1.4 TSI", "CZCA", FuelType.PETROL, 1395, 92, [oil("5W-30", "VW 504.00, VW 502.00", "4.0"), dsg("1.7")]),
    (VAG, "1.0 TSI", "CHZD", FuelType.PETROL, 999, 70, [oil("5W-30", "VW 504.00, VW 502.00", "4.0")]),
    ("BMW", "2.0d", "B47D20", FuelType.DIESEL, 1995, 110, [oil("5W-30", "BMW LL-04", "5.2"), automatic("ZF LifeguardFluid 8", "9.0")]),
    ("Mercedes-Benz", "2.2 CDI", "OM651", FuelType.DIESEL, 2143, 125, [oil("5W-30", "MB 229.51", "6.5"), automatic("MB 236.15", "7.5")]),
    ("Opel", "1.6 CDTI", "B16DTH", FuelType.DIESEL, 1598, 100, [oil("5W-30", "dexos2", "4.8")]),
    ("Ford", "1.0 EcoBoost", "M1DA", FuelType.PETROL, 999, 74, [oil("5W-20", "Ford WSS-M2C948-B", "4.1")]),
    ("Renault, Dacia", "1.5 dCi", "K9K", FuelType.DIESEL, 1461, 66, [oil("5W-30", "RN0720", "4.5")]),
    ("Renault, Dacia", "1.3 TCe", "H5H", FuelType.PETROL, 1332, 96, [oil("5W-30", "RN17", "5.0")]),
    ("Toyota", "1.8 Hybrid", "2ZR-FXE", FuelType.HYBRID, 1798, 90,
     [oil("0W-20", "ILSAC GF-6", "4.2"),
      {"kind": FluidKind.TRANSMISSION_FLUID, "transmission": Transmission.CVT, "approvals": "Toyota ATF WS", "capacity_litres": D("3.8")}]),
    ("Toyota", "1.33 VVT-i", "1NR-FE", FuelType.PETROL, 1329, 73, [oil("0W-20", "ILSAC GF-6", "3.4")]),
    ("Kia, Hyundai", "1.6 CRDi", "D4FB", FuelType.DIESEL, 1582, 100, [oil("5W-30", "ACEA C3", "5.3")]),
    ("Kia, Hyundai", "1.4 MPI", "G4LC", FuelType.PETROL, 1368, 73, [oil("5W-30", "ACEA C3, API SN", "3.6")]),
    ("Peugeot, Citroën", "1.6 HDi", "DV6C", FuelType.DIESEL, 1560, 68, [oil("5W-30", "PSA B71 2290", "3.75")]),
    ("Peugeot, Citroën", "1.2 PureTech", "EB2DTS", FuelType.PETROL, 1199, 96, [oil("0W-30", "PSA B71 2312", "3.5")]),
]


def fluid(name, number, price_per_litre, litres, kind, viscosity, approvals):
    return {"name": name, "part_number": number, "unit_price": D(price_per_litre), "quantity_in_stock": D(litres),
            "min_stock_level": 10, "unit": PartUnit.LITRE, "fluid_kind": kind, "viscosity": viscosity, "approvals": approvals}


# Течности и филтри в склада. Имената са общи (без марки), за да не се твърдят одобрения за конкретни продукти.
FLUID_PARTS = [
    fluid("Масло 5W-30 C3 (BMW, MB, Opel, PSA)", "OIL-5W30-C3", "10.5", 120, FluidKind.ENGINE_OIL, "5W-30",
          "ACEA C3, BMW LL-04, MB 229.51, dexos2, PSA B71 2290, API SN"),
    fluid("Масло 5W-30 C4 (Renault)", "OIL-5W30-C4", "11", 60, FluidKind.ENGINE_OIL, "5W-30", "ACEA C4, RN0720, RN17"),
    fluid("Масло 0W-20 (хибрид, Toyota)", "OIL-0W20", "12", 40, FluidKind.ENGINE_OIL, "0W-20", "API SP, ILSAC GF-6, ACEA C5"),
    fluid("Масло 5W-20 (Ford EcoBoost)", "OIL-5W20-FORD", "11.5", 30, FluidKind.ENGINE_OIL, "5W-20", "Ford WSS-M2C948-B, ACEA A1/B1"),
    fluid("Масло 10W-40 полусинтетично", "OIL-10W40", "7", 60, FluidKind.ENGINE_OIL, "10W-40", "ACEA A3/B4, API SL"),
    fluid("Масло за DSG", "ATF-DSG", "16", 20, FluidKind.TRANSMISSION_FLUID, None, "VW TL 052 182"),
    fluid("Масло за автоматична кутия ZF 8HP", "ATF-ZF8", "18", 18, FluidKind.TRANSMISSION_FLUID, None, "ZF LifeguardFluid 8"),
    {"name": "Маслен филтър (VW TDI)", "part_number": "OF-VAG-TDI", "unit_price": D("11"), "quantity_in_stock": D(14), "min_stock_level": 4},
    {"name": "Маслен филтър (Kia/Hyundai)", "part_number": "OF-HK-16", "unit_price": D("9"), "quantity_in_stock": D(10), "min_stock_level": 3},
]
