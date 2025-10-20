from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash

from db import get_db
from services.twelvedata import search_symbols

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

SUPPORTED_PROVIDERS = ("twelvedata",)


@settings_bp.route("/")
def settings_index():
    return redirect(url_for("settings.mappings"))


@settings_bp.route("/mappings", methods=["GET", "POST"])
def mappings():
    db = get_db()
    cur = db.cursor()

    search_results: list[dict] = []
    search_context = {"internal_symbol": "", "query": ""}

    if request.method == "POST":
        action = request.form.get("action", "add")
        now = datetime.utcnow().isoformat(timespec="seconds")

        if action == "add":
            internal_symbol = (request.form.get("internal_symbol") or "").strip().upper()
            provider = (request.form.get("provider") or "").strip().lower()
            provider_symbol = (request.form.get("provider_symbol") or "").strip()
            notes = (request.form.get("notes") or "").strip() or None
            priority_raw = request.form.get("priority", "0").strip()

            try:
                priority = int(priority_raw)
            except (TypeError, ValueError):
                priority = 0

            if not internal_symbol or not provider_symbol or provider not in SUPPORTED_PROVIDERS:
                flash("Uzupełnij symbol, provider i alias (dozwolone: twelvedata).", "danger")
            else:
                try:
                    cur.execute(
                        """
                        INSERT INTO symbol_mappings (internal_symbol, provider, provider_symbol, priority, active, notes, updated_at)
                        VALUES (?, ?, ?, ?, 1, ?, ?)
                        ON CONFLICT(internal_symbol, provider, provider_symbol) DO UPDATE SET
                            priority=excluded.priority,
                            active=1,
                            notes=excluded.notes,
                            updated_at=excluded.updated_at
                        """,
                        (internal_symbol, provider, provider_symbol, priority, notes, now),
                    )
                    db.commit()
                    flash("Alias symbolu zapisany.", "success")
                except Exception as exc:  # pragma: no cover
                    db.rollback()
                    flash(f"Nie udało się zapisać aliasu: {exc}", "danger")
            return redirect(url_for("settings.mappings"))

        if action == "toggle":
            mapping_id = request.form.get("mapping_id")
            try:
                mapping_id_int = int(mapping_id)
            except (TypeError, ValueError):
                flash("Nieprawidłowe ID aliasu.", "danger")
            else:
                cur.execute("SELECT active FROM symbol_mappings WHERE id = ?", (mapping_id_int,))
                row = cur.fetchone()
                if not row:
                    flash("Alias nie istnieje.", "danger")
                else:
                    new_state = 0 if row[0] else 1
                    cur.execute(
                        "UPDATE symbol_mappings SET active = ?, updated_at = ? WHERE id = ?",
                        (new_state, now, mapping_id_int),
                    )
                    db.commit()
                    flash("Alias został {}.".format("wyłączony" if new_state == 0 else "włączony"), "info")
            return redirect(url_for("settings.mappings"))

        if action == "delete":
            mapping_id = request.form.get("mapping_id")
            try:
                mapping_id_int = int(mapping_id)
            except (TypeError, ValueError):
                flash("Nieprawidłowe ID aliasu.", "danger")
            else:
                cur.execute("DELETE FROM symbol_mappings WHERE id = ?", (mapping_id_int,))
                db.commit()
                flash("Alias został usunięty.", "info")
            return redirect(url_for("settings.mappings"))

        if action == "search":
            internal_symbol = (request.form.get("internal_symbol_search") or "").strip().upper()
            query = (request.form.get("query") or "").strip()
            search_context = {"internal_symbol": internal_symbol, "query": query}

            if not query:
                flash("Podaj zapytanie do wyszukania.", "warning")
            else:
                try:
                    search_results = search_symbols(query)
                except Exception as exc:
                    flash(f"Nie udało się wyszukać symbolu: {exc}", "danger")
                    search_results = []

    cur.execute(
        """
        SELECT id, internal_symbol, provider, provider_symbol, priority, active, notes, created_at, updated_at
        FROM symbol_mappings
        ORDER BY internal_symbol ASC, provider ASC, priority ASC, provider_symbol ASC
        """
    )
    mappings = cur.fetchall()

    return render_template(
        "settings/mappings.html",
        mappings=mappings,
        providers=SUPPORTED_PROVIDERS,
        search_results=search_results,
        search_context=search_context,
    )
