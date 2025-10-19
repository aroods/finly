from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db
from bond_helpers import parse_bond_row, calculate_accrual

bonds_bp = Blueprint("bonds", __name__, url_prefix="/bonds")


def fetch_bonds():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM bonds ORDER BY purchase_date DESC, id DESC")
    rows = cur.fetchall()
    return [parse_bond_row(row) for row in rows]


@bonds_bp.route("/")
def list_bonds():
    bonds = fetch_bonds()
    summaries = []
    total_value = 0.0
    total_accrued = 0.0
    for bond in bonds:
        accrual = calculate_accrual(bond)
        summaries.append((bond, accrual))
        total_value += accrual["current_value"]
        total_accrued += accrual["accrued_interest"]
    return render_template(
        "bonds/list.html",
        bonds=summaries,
        total_value=round(total_value, 2),
        total_accrued=round(total_accrued, 2),
    )


@bonds_bp.route("/add", methods=["GET", "POST"])
def add_bond():
    if request.method == "POST":
        form = request.form
        series = form.get("series", "").strip().upper()
        bond_type = form.get("bond_type", "fixed").lower()
        purchase_date = form.get("purchase_date")
        maturity_date = form.get("maturity_date")
        quantity = int(float(form.get("quantity", 0) or 0))
        unit_price = float(form.get("unit_price", 0) or 0)
        face_value = float(form.get("face_value", 0) or 0)
        annual_rate = float(form.get("annual_rate", 0) or 0)
        margin = float(form.get("margin", 0) or 0)
        index_rate = float(form.get("index_rate", 0) or 0)
        capitalization = 1 if form.get("capitalization") == "on" else 0
        notes = form.get("notes") or None

        if not series or not purchase_date or not maturity_date:
            flash("Series, purchase date and maturity date are required.", "danger")
            return redirect(url_for("bonds.add_bond"))
        if quantity <= 0 or unit_price <= 0 or face_value <= 0:
            flash("Quantity, unit price and face value must be positive.", "danger")
            return redirect(url_for("bonds.add_bond"))

        db = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO bonds
                (series, bond_type, purchase_date, maturity_date, quantity, unit_price,
                 face_value, annual_rate, margin, index_rate, capitalization, notes)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                series,
                bond_type,
                purchase_date,
                maturity_date,
                quantity,
                unit_price,
                face_value,
                annual_rate,
                margin,
                index_rate,
                capitalization,
                notes,
            ),
        )
        db.commit()
        flash("Bond position added!", "success")
        return redirect(url_for("bonds.list_bonds"))

    today = date.today().isoformat()
    return render_template("bonds/add.html", today=today)
