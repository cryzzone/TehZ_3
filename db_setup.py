"""
Создание БД библиотеки с системой безопасности:
- 4 таблицы: authors, books, members, loans
- таблицы ролей и пользователей БД
- триггеры для журнала изменений
- резервное копирование
"""
import sqlite3, shutil, os
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "library.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # --- основные таблицы ---
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS authors (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                country TEXT
            );

            CREATE TABLE IF NOT EXISTS books (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                title     TEXT NOT NULL,
                author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE RESTRICT,
                year      INTEGER CHECK(year > 0 AND year <= 2100),
                copies    INTEGER NOT NULL DEFAULT 1 CHECK(copies >= 0)
            );

            CREATE TABLE IF NOT EXISTS members (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT
            );

            CREATE TABLE IF NOT EXISTS loans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE RESTRICT,
                member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE RESTRICT,
                loaned_at   TEXT NOT NULL DEFAULT (date('now')),
                returned_at TEXT
            );

            -- роли
            CREATE TABLE IF NOT EXISTS db_roles (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                can_select  INTEGER DEFAULT 1,
                can_insert  INTEGER DEFAULT 0,
                can_update  INTEGER DEFAULT 0,
                can_delete  INTEGER DEFAULT 0
            );

            -- пользователи БД
            CREATE TABLE IF NOT EXISTS db_users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                role_id  INTEGER NOT NULL REFERENCES db_roles(id)
            );

            -- журнал изменений (аудит)
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tbl        TEXT NOT NULL,
                action     TEXT NOT NULL,
                record_id  INTEGER,
                changed_at TEXT NOT NULL DEFAULT (datetime('now')),
                old_data   TEXT,
                new_data   TEXT
            );
        """)

        # триггеры аудита для books
        conn.executescript("""
            DROP TRIGGER IF EXISTS trg_books_insert;
            CREATE TRIGGER trg_books_insert AFTER INSERT ON books
            BEGIN
                INSERT INTO audit_log(tbl, action, record_id, new_data)
                VALUES('books', 'INSERT', NEW.id,
                    'title=' || NEW.title || ', copies=' || NEW.copies);
            END;

            DROP TRIGGER IF EXISTS trg_books_update;
            CREATE TRIGGER trg_books_update AFTER UPDATE ON books
            BEGIN
                INSERT INTO audit_log(tbl, action, record_id, old_data, new_data)
                VALUES('books', 'UPDATE', NEW.id,
                    'title=' || OLD.title || ', copies=' || OLD.copies,
                    'title=' || NEW.title || ', copies=' || NEW.copies);
            END;

            DROP TRIGGER IF EXISTS trg_books_delete;
            CREATE TRIGGER trg_books_delete AFTER DELETE ON books
            BEGIN
                INSERT INTO audit_log(tbl, action, record_id, old_data)
                VALUES('books', 'DELETE', OLD.id,
                    'title=' || OLD.title);
            END;

            DROP TRIGGER IF EXISTS trg_loans_insert;
            CREATE TRIGGER trg_loans_insert AFTER INSERT ON loans
            BEGIN
                INSERT INTO audit_log(tbl, action, record_id, new_data)
                VALUES('loans', 'INSERT', NEW.id,
                    'book_id=' || NEW.book_id || ', member_id=' || NEW.member_id);
            END;

            DROP TRIGGER IF EXISTS trg_loans_update;
            CREATE TRIGGER trg_loans_update AFTER UPDATE ON loans
            BEGIN
                INSERT INTO audit_log(tbl, action, record_id, old_data, new_data)
                VALUES('loans', 'UPDATE', NEW.id,
                    'returned_at=' || COALESCE(OLD.returned_at, 'NULL'),
                    'returned_at=' || COALESCE(NEW.returned_at, 'NULL'));
            END;
        """)

        # роли по умолчанию
        conn.executescript("""
            INSERT OR IGNORE INTO db_roles(name, can_select, can_insert, can_update, can_delete)
            VALUES
                ('admin',     1, 1, 1, 1),
                ('librarian', 1, 1, 1, 0),
                ('reader',    1, 0, 0, 0);

            INSERT OR IGNORE INTO db_users(username, role_id)
            VALUES
                ('admin',   (SELECT id FROM db_roles WHERE name='admin')),
                ('anna',    (SELECT id FROM db_roles WHERE name='librarian')),
                ('student', (SELECT id FROM db_roles WHERE name='reader'));
        """)

        # тестовые данные
        conn.executescript("""
            INSERT OR IGNORE INTO authors(id, name, country) VALUES
                (1, 'Лев Толстой',    'Россия'),
                (2, 'Фёдор Достоевский', 'Россия'),
                (3, 'Джордж Оруэлл', 'Великобритания');

            INSERT OR IGNORE INTO books(id, title, author_id, year, copies) VALUES
                (1, 'Война и мир',       1, 1869, 3),
                (2, 'Преступление и наказание', 2, 1866, 2),
                (3, '1984',              3, 1949, 4),
                (4, 'Анна Каренина',     1, 1878, 2);

            INSERT OR IGNORE INTO members(id, name, email, phone) VALUES
                (1, 'Иван Петров',   'ivan@mail.ru',  '+79001112233'),
                (2, 'Мария Сидорова','maria@mail.ru', '+79004445566');
        """)

    print("DB initialized:", DB)

def backup_db():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = DB.replace(".db", f"_backup_{ts}.db")
    shutil.copy2(DB, dst)
    print("Backup created:", dst)
    return dst

if __name__ == "__main__":
    init_db()
    backup_db()
