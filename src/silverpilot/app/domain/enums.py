from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class BankStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class InstrumentType(StrEnum):
    REFERENCE = "reference"
    EXECUTION = "execution"
