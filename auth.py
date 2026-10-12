"""UNTUK APA: login/logout + penjaga halaman.
- perlu_login: wajib sudah login
- wajib_admin: wajib login DAN peran admin (user biasa ditolak 403)
- bp_auth: route /login, /logout"""
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
from werkzeug.security import check_password_hash
from database import db

bp_auth = Blueprint("auth", __name__)


def perlu_login(fn):
    @wraps(fn)
    def w(*a, **k):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "pesan": "Belum login"}), 401
            return redirect(url_for("auth.login"))
        return fn(*a, **k)
    return w


def wajib_admin(fn):
    @wraps(fn)
    def w(*a, **k):
        if not session.get("uid"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "pesan": "Belum login"}), 401
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "pesan": "Hanya admin yang boleh."}), 403
            return redirect(url_for("halaman.index"))
        return fn(*a, **k)
    return w


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    j = request.get_json(force=True, silent=True) or request.form
    c = db()
    r = c.execute("SELECT * FROM users WHERE username=?",
                  ((j.get("username") or "").strip(),)).fetchone()
    c.close()
    if r and check_password_hash(r["password_hash"], j.get("password") or ""):
        session.permanent = True
        session["uid"] = r["id"]
        session["username"] = r["username"]
        try:
            session["role"] = r["role"] or "admin"
        except Exception:
            session["role"] = "admin"
        try:
            session["nik"] = r["nik"] or ""
        except Exception:
            session["nik"] = ""
        if request.is_json:
            return jsonify({"ok": True, "role": session["role"], "nik": session["nik"]})
        return redirect(url_for("halaman.index"))
    if request.is_json:
        return jsonify({"ok": False, "pesan": "Salah"}), 401
    return render_template("login.html", error="Username / password salah")


@bp_auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
