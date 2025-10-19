from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db


transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route('/')
def all_transactions():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC")
    transactions = cur.fetchall()
    return render_template('transactions.html', transactions=transactions)


@transactions_bp.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        db = get_db()
        cur = db.cursor()
        tx_date = request.form['date']
        asset = request.form['asset'].strip().upper()
        tx_type = request.form['type'].lower()
        category = request.form['category']

        try:
            quantity = float(request.form['quantity'])
            price = float(request.form['price'])
        except ValueError:
            flash("Quantity and price must be numeric values.", "danger")
            return redirect(url_for('transactions.add_transaction'))

        if tx_type not in {'buy', 'sell'}:
            flash("Transaction type must be buy or sell.", "danger")
            return redirect(url_for('transactions.add_transaction'))
        if quantity <= 0 or price <= 0:
            flash("Quantity and price must be greater than zero.", "danger")
            return redirect(url_for('transactions.add_transaction'))

        currency = request.form['currency'].strip().upper()
        if not currency:
            currency = 'PLN'
            flash("Currency not detected; defaulted to PLN. Please adjust if needed.", "warning")

        cur.execute(
            """
            INSERT INTO transactions (date, asset, type, quantity, price, currency, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tx_date, asset, tx_type, quantity, price, currency, category),
        )
        db.commit()
        flash("Transaction added!", "success")
        return redirect(url_for('transactions.all_transactions'))

    today_str = date.today().isoformat()
    return render_template('add.html', today=today_str)


@transactions_bp.route('/edit/<int:tx_id>', methods=['GET', 'POST'])
def edit_transaction(tx_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    tx = cur.fetchone()
    if not tx:
        flash("Transaction not found.", "danger")
        return redirect(url_for('transactions.all_transactions'))

    if request.method == 'POST':
        tx_date = request.form['date']
        asset = request.form['asset'].strip().upper()
        tx_type = request.form['type'].lower()
        category = request.form['category']

        try:
            quantity = float(request.form['quantity'])
            price = float(request.form['price'])
        except ValueError:
            flash("Quantity and price must be numeric values.", "danger")
            return redirect(url_for('transactions.edit_transaction', tx_id=tx_id))

        if tx_type not in {'buy', 'sell'}:
            flash("Transaction type must be buy or sell.", "danger")
            return redirect(url_for('transactions.edit_transaction', tx_id=tx_id))
        if quantity <= 0 or price <= 0:
            flash("Quantity and price must be greater than zero.", "danger")
            return redirect(url_for('transactions.edit_transaction', tx_id=tx_id))

        currency = request.form['currency'].strip().upper()
        if not currency:
            currency = 'PLN'
            flash("Currency not detected; defaulted to PLN. Please adjust if needed.", "warning")

        cur.execute(
            """
            UPDATE transactions
            SET date=?, asset=?, type=?, quantity=?, price=?, currency=?, category=?
            WHERE id=?
            """,
            (tx_date, asset, tx_type, quantity, price, currency, category, tx_id),
        )
        db.commit()
        flash("Transaction updated!", "success")
        return redirect(url_for('transactions.all_transactions'))

    return render_template('edit.html', tx=tx)
