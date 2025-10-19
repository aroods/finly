from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


TAX_RATE = 0.19


@dataclass
class BondPosition:
    id: int
    series: str
    bond_type: str
    purchase_date: date
    maturity_date: date
    quantity: int
    unit_price: float
    face_value: float
    annual_rate: float
    margin: float
    index_rate: float
    capitalization: bool
    notes: Optional[str]

    @property
    def principal(self) -> float:
        return self.quantity * self.face_value


def parse_bond_row(row) -> BondPosition:
    return BondPosition(
        id=row["id"],
        series=row["series"],
        bond_type=row["bond_type"],
        purchase_date=datetime.fromisoformat(row["purchase_date"]).date(),
        maturity_date=datetime.fromisoformat(row["maturity_date"]).date(),
        quantity=row["quantity"],
        unit_price=row["unit_price"],
        face_value=row["face_value"],
        annual_rate=row["annual_rate"],
        margin=row["margin"] or 0.0,
        index_rate=row["index_rate"] or 0.0,
        capitalization=bool(row["capitalization"]),
        notes=row["notes"],
    )


def current_effective_rate(bond: BondPosition) -> float:
    base_rate = bond.annual_rate
    if bond.bond_type.lower() == "indexed":
        base_rate += bond.index_rate + bond.margin
    return base_rate / 100.0


def calculate_accrual(bond: BondPosition, reference: Optional[date] = None) -> dict:
    reference = reference or date.today()
    start = bond.purchase_date
    end = bond.maturity_date
    if reference < start:
        return {
            "days_held": 0,
            "total_days": (end - start).days,
            "accrued_interest": 0.0,
            "current_value": bond.principal,
        }

    total_days = max((end - start).days, 1)
    days_held = min((reference - start).days, total_days)

    rate = current_effective_rate(bond)
    principal = bond.principal

    years_fraction = days_held / 365.0
    if bond.capitalization:
        gross_accrued = principal * ((1 + rate) ** years_fraction - 1)
    else:
        gross_accrued = principal * rate * (days_held / total_days)

    net_accrued = gross_accrued * (1 - TAX_RATE)
    current_value = principal + net_accrued
    return {
        "days_held": days_held,
        "total_days": total_days,
        "accrued_interest": round(net_accrued, 2),
        "accrued_interest_gross": round(gross_accrued, 2),
        "current_value": round(current_value, 2),
        "effective_rate": round(rate * 100, 2),
    }
