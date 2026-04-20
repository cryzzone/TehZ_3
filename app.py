from flask import Flask, request, jsonify, send_from_directory, session
from db_setup import get_db, init_db, backup_db
import os

app = Flask(__name__)
app.secret_key = "tz3-secret"

CURRENT_USER = "admin"  # в реальной системе — через сессию/логин

def check_perm(action):
    """Проверяет право текущего пользователя на действие."""
    col = f"can_{action}"
    with get_db() as conn:
        row = conn.execute(f"""
            SELECT r.{col} FROM db_users u
            JOIN db_roles r ON r.id = u.role_id
            WHERE u.username = ?
        """, (CURRENT_USER,)).fetchone()
    if not row or not row[col]:
        return False
    return True

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# --- текущий пользователь и его роль ---
@app.route("/me")
def me():
    with get_db() as conn:
        row = conn.execute("""
            SELECT u.username, r.name as role,
                   r.can_select, r.can_insert, r.can_update, r.can_delete
            FROM db_users u JOIN db_roles r ON r.id=u.role_id
            WHERE u.username=?
        """, (CURRENT_USER,)).fetchone()
    return jsonify(dict(row) if row else {})

@app.route("/switch_user", methods=["POST"])
def switch_user():
    global CURRENT_USER
    username = request.get_json().get("username", "").strip()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM db_users WHERE username=?", (username,)).fetchone()
    if not row:
        return jsonify({"error": "User not found"}), 404
    CURRENT_USER = username
    return jsonify({"ok": True, "username": CURRENT_USER})

# --- авторы ---
@app.route("/authors")
def get_authors():
    if not check_perm("select"):
        return jsonify({"error": "Access denied"}), 403
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM authors ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

# --- книги ---
@app.route("/books")
def get_books():
    if not check_perm("select"):
        return jsonify({"error": "Access denied"}), 403
    with get_db() as conn:
        rows = conn.execute("""
            SELECT b.id, b.title, a.name as author, b.year, b.copies
            FROM books b JOIN authors a ON a.id=b.author_id
            ORDER BY b.title
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/books", methods=["POST"])
def add_book():
    if not check_perm("insert"):
        return jsonify({"error": "Access denied"}), 403
    d = request.get_json()
    title = (d.get("title") or "").strip()
    author_id = d.get("author_id")
    year = d.get("year")
    copies = d.get("copies", 1)
    if not title or not author_id:
        return jsonify({"error": "Title and author required"}), 400
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO books(title, author_id, year, copies) VALUES(?,?,?,?)",
                (title, author_id, year or None, copies)
            )
            row = conn.execute("""
                SELECT b.id, b.title, a.name as author, b.year, b.copies
                FROM books b JOIN authors a ON a.id=b.author_id WHERE b.id=?
            """, (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/books/<int:bid>", methods=["DELETE"])
def delete_book(bid):
    if not check_perm("delete"):
        return jsonify({"error": "Access denied"}), 403
    try:
        with get_db() as conn:
            cur = conn.execute("DELETE FROM books WHERE id=?", (bid,))
            if cur.rowcount == 0:
                return jsonify({"error": "Not found"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- выдача / возврат книг ---
@app.route("/loans")
def get_loans():
    if not check_perm("select"):
        return jsonify({"error": "Access denied"}), 403
    with get_db() as conn:
        rows = conn.execute("""
            SELECT l.id, b.title, m.name as member, l.loaned_at, l.returned_at
            FROM loans l
            JOIN books b ON b.id=l.book_id
            JOIN members m ON m.id=l.member_id
            ORDER BY l.loaned_at DESC
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/loans", methods=["POST"])
def add_loan():
    if not check_perm("insert"):
        return jsonify({"error": "Access denied"}), 403
    d = request.get_json()
    book_id = d.get("book_id")
    member_id = d.get("member_id")
    if not book_id or not member_id:
        return jsonify({"error": "book_id and member_id required"}), 400
    try:
        with get_db() as conn:
            copies = conn.execute("SELECT copies FROM books WHERE id=?", (book_id,)).fetchone()
            if not copies or copies["copies"] < 1:
                return jsonify({"error": "No copies available"}), 400
            conn.execute("UPDATE books SET copies=copies-1 WHERE id=?", (book_id,))
            cur = conn.execute(
                "INSERT INTO loans(book_id, member_id) VALUES(?,?)", (book_id, member_id)
            )
        return jsonify({"ok": True, "loan_id": cur.lastrowid}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/loans/<int:lid>/return", methods=["POST"])
def return_loan(lid):
    if not check_perm("update"):
        return jsonify({"error": "Access denied"}), 403
    try:
        with get_db() as conn:
            loan = conn.execute("SELECT * FROM loans WHERE id=?", (lid,)).fetchone()
            if not loan:
                return jsonify({"error": "Loan not found"}), 404
            if loan["returned_at"]:
                return jsonify({"error": "Already returned"}), 400
            conn.execute("UPDATE loans SET returned_at=date('now') WHERE id=?", (lid,))
            conn.execute("UPDATE books SET copies=copies+1 WHERE id=?", (loan["book_id"],))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- аудит ---
@app.route("/audit")
def get_audit():
    if not check_perm("select"):
        return jsonify({"error": "Access denied"}), 403
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT 50"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

# --- пользователи БД ---
@app.route("/db_users")
def get_db_users():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT u.id, u.username, r.name as role
            FROM db_users u JOIN db_roles r ON r.id=u.role_id
        """).fetchall()
    return jsonify([dict(r) for r in rows])

# --- члены библиотеки ---
@app.route("/members")
def get_members():
    if not check_perm("select"):
        return jsonify({"error": "Access denied"}), 403
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])

# --- резервное копирование ---
@app.route("/backup", methods=["POST"])
def do_backup():
    if CURRENT_USER != "admin":
        return jsonify({"error": "Only admin can backup"}), 403
    path = backup_db()
    return jsonify({"ok": True, "file": os.path.basename(path)})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5002)
