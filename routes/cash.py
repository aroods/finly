from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import get_db
from datetime import datetime

cash_bp = Blueprint("cash", __name__)

@cash_bp.route('/add', methods=['GET', 'POST'])
def add_cash():
    if request.method == 'POST':
        db = get_db()
        cur = db.cursor()
        new_amount = float(request.form['amount'])
        note = request.form.get('note', '')

        # Get the latest previous amount
        cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        prev_amount = row[0] if row else 0.0
        delta = new_amount - prev_amount

        cur.execute(
            "INSERT INTO cash_deposits (amount, delta, note, created_at) VALUES (?, ?, ?, ?)",
            (new_amount, delta, note, datetime.now().isoformat())
        )
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
        original_created_at = deposit[1]
        if original_created_at and len(original_created_at) > 10:
            created_at = f"{form_date}{original_created_at[10:]}"
        else:
            created_at = form_date

        cur.execute(
            """
            SELECT amount FROM cash_deposits
            WHERE id != ? AND created_at <= ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (deposit_id, created_at)
        )
        prev_row = cur.fetchone()
        if not prev_row:
            cur.execute(
                "SELECT amount FROM cash_deposits WHERE id != ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (deposit_id,)
            )
            prev_row = cur.fetchone()
        prev_amount = prev_row[0] if prev_row else 0.0
        delta = amount - prev_amount

        cur.execute(
            "UPDATE cash_deposits SET created_at=?, amount=?, delta=?, note=? WHERE id=?",
            (created_at, amount, delta, note, deposit_id)
        )
        db.commit()
        flash("Cash entry updated!", "success")
        return redirect(url_for('cash.cash_history'))

    return render_template('edit_cash.html', deposit=deposit)

@cash_bp.route('/history')
def cash_history():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM cash_deposits ORDER BY created_at DESC")
    deposits = cur.fetchall()
    cur.execute("SELECT amount FROM cash_deposits ORDER BY created_at DESC LIMIT 1")
    current_row = cur.fetchone()
    current_balance = current_row[0] if current_row else 0.0
    return render_template(
        'cash_history.html',
        deposits=deposits,
        current_balance=current_balance
    )
