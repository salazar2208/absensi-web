"""UNTUK APA: halaman web (bukan API).
- /  -> dashboard utama (kirim peran + NIK ke template agar menu menyesuaikan)"""
from flask import Blueprint, render_template, session
from auth import perlu_login

bp_halaman = Blueprint("halaman", __name__)


@bp_halaman.route("/")
@perlu_login
def index():
    return render_template("index.html",
                           username=session.get("username", ""),
                           role=session.get("role", "admin"),
                           nik=session.get("nik", ""))
