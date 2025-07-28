from flask import Blueprint, render_template, redirect, url_for, flash

about_bp = Blueprint("about", __name__)

@about_bp.route('/')

def about():
    return render_template('about.html')