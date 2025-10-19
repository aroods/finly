from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db

cash_bp = Blueprint("cash", __name__)


def recalculate_cash_deltas(db):
    cur = db.cursor()
    cur.execute(
        "SELECT id, amount FROM cash_deposits ORDER BY created_at ASC, id ASC"
    )
    rows = cur.fetchall()
    previous_amount = 0.0
    updates = []
    for row in rows:
        use_mapping = hasattr(row, "keys")
        deposit_id = row["id"] if use_mapping else row[0]
        amount = row["amount"] if use_mapping else row[1]
        amount = float(amount or 0.0)
        delta = amount - previous_amount
        updates.append((delta, deposit_id))
        previous_amount = amount

    if updates:
        cur.executemany("UPDATE cash_deposits SET delta=? WHERE id=?", updates)


def _format_deposit(deposit):
    if deposit is None:
        return None
    if hasattr(deposit, "keys"):
        return {
            "id": deposit["id"],
            "created_at": deposit["created_at"],
            "amount": deposit["amount"],
            "note": deposit.get("note"),
        }
    return {
        "id": deposit[0],
        "created_at": deposit[1],
        "amount": deposit[2],
        "note": deposit[4] if len(deposit) > 4 else None,
    }


@cash_bp.route('/add', methods=['GET', 'POST'])
def add_cash():
    if request.method == 'POST':
        db = get_db()
        cur = db.cursor()
        new_amount = float(request.form['amount'])
        note = request.form.get('note', '')
        created_at = datetime.now().isoformat(timespec='seconds')

        cur.execute(
            "INSERT INTO cash_deposits (amount, delta, note, created_at) VALUES (?, ?, ?, ?)",
            (new_amount, 0.0, note, created_at)
        )
        recalculate_cash_deltas(db)
        db.commit()
        flash("Cash state added!", "success")
        return redirect(url_for('cash.cash_history'))
    return render_template('add_cash.html')


@cash_bp.route('/edit/<int:deposit_id>', methods=['GET', 'POST'])
def edit_cash(deposit_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM cash_deposits WHERE id=?", (deposit_id,))
    deposit = cur.fetchone()
    if not deposit:
        flash("Cash deposit not found.", "danger")
        return redirect(url_for('cash.cash_history'))

    if request.method == 'POST':
        form_date = request.form['date']
        amount = float(request.form['amount'])
        note = request.form.get('note', '')
        use_mapping = hasattr(deposit, "keys")
        original_created_at = deposit["created_at"] if use_mapping else deposit[1]
        if original_created_at and len(original_created_at) > 10:
            created_at = f"{form_date}{original_created_at[10:]}"
        else:
            created_at = f"{form_date}T00:00:00"

        cur.execute(
            "UPDATE cash_deposits SET created_at=?, amount=?, note=? WHERE id=?",
            (created_at, amount, note, deposit["id"] if use_mapping else deposit[0])
        )
        recalculate_cash_deltas(db)
        db.commit()
        flash("Cash entry updated!", "success")
        return redirect(url_for('cash.cash_history'))

    return render_template('edit_cash.html', deposit=_format_deposit(deposit))


@cash_bp.route('/history')
def cash_history():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM cash_deposits ORDER BY created_at DESC")
    deposits = cur.fetchall()
    cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
    current_row = cur.fetchone()
    if current_row:
        current_balance = (
            current_row["amount"] if hasattr(current_row, "keys") else current_row[0]
        )
    else:
        current_balance = 0.0
    return render_template(
        'cash_history.html',
        deposits=deposits,
        current_balance=current_balance
    )
