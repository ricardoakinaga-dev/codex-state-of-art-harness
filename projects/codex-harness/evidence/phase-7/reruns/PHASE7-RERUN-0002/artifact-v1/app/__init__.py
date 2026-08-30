"""Disposable standard-library veterinary appointment API pilot."""

from .api import AppointmentApplication, create_app
from .db import Database
from .service import (
    AppointmentService,
    ServiceResult,
    create_appointment,
    get_appointment,
    seed_demo_data,
)

__all__ = [
    "AppointmentApplication",
    "AppointmentService",
    "Database",
    "ServiceResult",
    "create_app",
    "create_appointment",
    "get_appointment",
    "seed_demo_data",
]
