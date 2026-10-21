"""Слой „Данни“ - всички модели (таблици)."""
from .catalog import Part, PartFitment, Service, ServicePackageItem
from .enums import *  # noqa: F401,F403
from .inspections import Inspection, InspectionPhoto, InspectionResult, InspectionTemplate, InspectionTemplateItem
from .people import Customer, Mechanic, User
from .repairs import (VAT_RATE, Appointment, Payment, Recommendation, RepairOrder, RepairOrderPartLine,
                      RepairOrderServiceLine, round_money)
from .vehicles import CarMake, CarModel, EngineVariant, FluidRequirement, Vehicle
