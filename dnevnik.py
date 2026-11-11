import os
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (Flask, render_template_string, request, redirect,
                   url_for, g, session, flash)
from jinja2 import DictLoader

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'diary.db')

app = Flask(__name__)
app.config['DATABASE'] = DATABASE
app.config['SECRET_KEY'] = 'secret-key-for-coursework-2024'

# ============================================================
# СХЕМА БД И ТЕСТОВЫЕ ДАННЫЕ
# ============================================================
SCHEMA_SQL = """
DROP TABLE IF EXISTS records;
DROP TABLE IF EXISTS schedule;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS users;

CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    class_name TEXT NOT NULL
);

CREATE TABLE subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'student')),
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    record_type TEXT NOT NULL CHECK(record_type IN ('grade', 'homework', 'remark')),
    content TEXT NOT NULL,
    date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 1 AND 6),
    lesson_number INTEGER NOT NULL,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    room TEXT,
    note TEXT
);

INSERT INTO students (full_name, class_name) VALUES
    ('Иванов Иван', '9А'),
    ('Петрова Анна', '9А'),
    ('Сидоров Максим', '9Б');

INSERT INTO subjects (name) VALUES
    ('Математика'),
    ('Русский язык'),
    ('Физика'),
    ('История'),
    ('Информатика'),
    ('Английский язык');

INSERT INTO schedule (class_name, day_of_week, lesson_number, subject_id, room) VALUES
    ('9А', 1, 1, 1, 'каб. 201'),
    ('9А', 1, 2, 2, 'каб. 105'),
    ('9А', 1, 3, 3, 'каб. 304'),
    ('9А', 2, 1, 4, 'каб. 108'),
    ('9А', 2, 2, 1, 'каб. 201'),
    ('9А', 3, 1, 5, 'каб. 402'),
    ('9А', 3, 2, 6, 'каб. 302'),
    ('9А', 4, 1, 2, 'каб. 105'),
    ('9А', 4, 2, 3, 'каб. 304'),
    ('9А', 5, 1, 1, 'каб. 201');

INSERT INTO records (student_id, subject_id, record_type, content) VALUES
    (1, 1, 'grade', '5'), (1, 2, 'grade', '4'), (1, 3, 'grade', '3'),
    (1, 4, 'grade', '5'), (1, 5, 'grade', '5'), (1, 1, 'grade', '4'),
    (1, 3, 'grade', '5'),
    (1, 1, 'homework', 'Решить № 405, 406 стр. 82'),
    (1, 2, 'homework', 'Упражнение 154, выучить правило'),
    (1, 3, 'homework', 'Параграф 12, задачи 1-5'),
    (1, 4, 'homework', 'Прочитать параграф 10, ответить на вопросы'),
    (1, 5, 'homework', 'Написать программу на Python (циклы)'),
    (1, 1, 'remark', 'Разговаривал на уроке'),
    (1, 3, 'remark', 'Забыл тетрадь дома'),
    (2, 1, 'grade', '4'), (2, 2, 'grade', '5'), (2, 4, 'grade', '4');
"""


# ============================================================
# РАБОТА С БД
# ============================================================
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
        ('admin', generate_password_hash('admin123'), 'admin')
    )
    conn.execute(
        'INSERT INTO users (username, password_hash, role, student_id) VALUES (?, ?, ?, ?)',
        ('ivanov', generate_password_hash('123456'), 'student', 1)
    )
    conn.execute(
        'INSERT INTO users (username, password_hash, role, student_id) VALUES (?, ?, ?, ?)',
        ('petrova', generate_password_hash('123456'), 'student', 2)
    )
    conn.commit()
    conn.close()


def check_and_fix_db():
    if not os.path.exists(app.config['DATABASE']):
        init_db()
        return
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cur = conn.execute("PRAGMA table_info(schedule)")
        columns = [row[1] for row in cur.fetchall()]
        conn.close()
        if not columns:
            os.remove(app.config['DATABASE'])
            init_db()
    except Exception:
        if os.path.exists(app.config['DATABASE']):
            os.remove(app.config['DATABASE'])
        init_db()


# ============================================================
# ДЕКОРАТОРЫ
# ============================================================
def student_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get('role') != 'student':
            flash('Войдите как ученик.', 'error')
            return redirect(url_for('student_login'))
        return f(*a, **kw)

    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get('role') != 'admin':
            flash('Доступ только для администратора.', 'error')
            return redirect(url_for('admin_login'))
        return f(*a, **kw)

    return wrapper


@app.context_processor
def inject_user():
    return {
        'current_user': {
            'username': session.get('username'),
            'role': session.get('role'),
        } if 'role' in session else None
    }


# ============================================================
# CSS
# ============================================================
CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    :root {
        --primary: #4f46e5; --primary-hover: #4338ca;
        --bg-grad-start: #e0e7ff; --bg-grad-end: #f3f4f6;
        --surface: #ffffff; --text: #1f2937; --text-muted: #6b7280;
        --border: #e5e7eb;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { 
        font-family: 'Inter', sans-serif; 
        background: linear-gradient(135deg, var(--bg-grad-start) 0%, var(--bg-grad-end) 100%);
        color: var(--text); line-height: 1.5; min-height: 100vh; 
        display: flex; flex-direction: column; 
    }
    nav { background: rgba(255, 255, 255, 0.8); backdrop-filter: blur(10px);
          box-shadow: 0 1px 3px rgba(0,0,0,0.05); padding: 0 30px; 
          display: flex; align-items: center; height: 64px; position: sticky; top: 0; z-index: 100; gap: 15px; }
    nav a.nav-link { color: var(--text-muted); text-decoration: none; font-weight: 500;
            padding: 10px 15px; border-radius: 6px; transition: 0.2s; }
    nav a.nav-link:hover, nav a.nav-link.active { background: var(--bg-grad-start); color: var(--primary); }
    nav .brand { font-weight: 700; font-size: 1.2em; color: var(--primary);
                 margin-right: 15px; display: flex; align-items: center; gap: 8px; }
    nav .right { margin-left: auto; display: flex; gap: 15px; align-items: center; }
    nav.admin-nav { background: #1e1b4b; backdrop-filter: none; color: white; }
    nav.admin-nav .brand { color: white; }
    nav.admin-nav a.nav-link { color: #c7d2fe; }
    nav.admin-nav a.nav-link:hover, nav.admin-nav a.nav-link.active { background: #312e81; color: white; }
    .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; flex: 1; width: 100%; }
    .card { background: var(--surface); border-radius: 16px; padding: 30px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05); border: 1px solid rgba(255,255,255,0.5); }
    h1 { font-size: 1.8em; font-weight: 700; margin-bottom: 20px; color: var(--text); }
    h2 { font-size: 1.3em; font-weight: 600; margin: 25px 0 15px; color: var(--text); }
    .profile-header { display: flex; align-items: center; gap: 20px; margin-bottom: 30px; 
                      padding-bottom: 20px; border-bottom: 1px solid var(--border); }
    .avatar { width: 60px; height: 60px; border-radius: 50%; background: linear-gradient(135deg, #6366f1, #8b5cf6);
              color: white; display: flex; align-items: center; justify-content: center; font-size: 1.5em; font-weight: bold; }
    .profile-info h2 { margin: 0; font-size: 1.4em; }
    .profile-info p { color: var(--text-muted); font-size: 0.95em; }
    .subject-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }
    .subject-card { display: flex; flex-direction: column; text-decoration: none; background: var(--surface);
                    border: 1px solid var(--border); border-radius: 12px; padding: 20px;
                    color: var(--text); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); position: relative; overflow: hidden; }
    .subject-card:hover { border-color: var(--primary); box-shadow: 0 12px 20px -10px rgba(79, 70, 229, 0.25); transform: translateY(-4px); }
    .sub-header { display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }
    .sub-icon { width: 45px; height: 45px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.3em; }
    .sub-title { font-size: 1.15em; font-weight: 600; }
    .icon-math { background: #e0e7ff; color: #4338ca; }
    .icon-rus { background: #fce7f3; color: #be185d; }
    .icon-phys { background: #dbeafe; color: #1d4ed8; }
    .icon-hist { background: #fef3c7; color: #b45309; }
    .icon-inf { background: #dcfce7; color: #15803d; }
    .icon-eng { background: #ffedd5; color: #c2410c; }
    .icon-default { background: #f3f4f6; color: #4b5563; }
    .sub-stats { display: flex; gap: 10px; margin-top: auto; }
    .sub-badge { display: inline-flex; align-items: center; gap: 5px; font-size: 0.85em; font-weight: 500;
                 padding: 4px 10px; border-radius: 20px; background: #f3f4f6; color: var(--text-muted); }
    .sub-badge.grades { background: #ecfdf5; color: #047857; }
    .sub-badge.hw { background: #fffbeb; color: #b45309; }
    .mini-grades { display: flex; gap: 4px; margin-left: auto; }
    .mini-grade { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                  font-size: 0.75em; font-weight: bold; color: white; }
    .mg-5 { background: #10b981; } .mg-4 { background: #3b82f6; } .mg-3 { background: #f59e0b; } .mg-2 { background: #ef4444; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
    th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--border); }
    th { background: #f9fafb; font-weight: 600; color: var(--text-muted); font-size: 0.9em; text-transform: uppercase; letter-spacing: 0.5px; }
    tr:hover td { background: #f9fafb; }
    .schedule-grid { display: grid; grid-template-columns: 80px repeat(5, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .sch-header { background: #f3f4f6; font-weight: 600; padding: 15px 10px; text-align: center; color: var(--text); }
    .sch-time { background: #f9fafb; font-weight: 500; padding: 15px 10px; text-align: center; color: var(--text-muted); display: flex; align-items: center; justify-content: center; }
    .sch-cell { background: var(--surface); padding: 15px 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; min-height: 90px; }
    .sch-subject { font-weight: 600; color: var(--primary); margin-bottom: 4px; }
    .sch-room { font-size: 0.8em; color: var(--text-muted); }
    .sch-note { font-size: 0.75em; color: #ef4444; font-weight: bold; margin-top: 4px; }
    .grade { font-weight: 700; font-size: 1.1em; display: inline-flex; justify-content: center;
             align-items: center; width: 36px; height: 36px; border-radius: 50%; color: white; }
    .grade-5 { background: #10b981; } .grade-4 { background: #3b82f6; }
    .grade-3 { background: #f59e0b; } .grade-2 { background: #ef4444; }
    .card-list { list-style: none; display: flex; flex-direction: column; gap: 10px; }
    .card-list li { background: #f9fafb; border: 1px solid var(--border); border-left: 4px solid var(--primary);
                    padding: 15px; border-radius: 8px; }
    .card-list.remark li { border-left-color: #ef4444; background: #fef2f2; }
    .card-list.homework li { border-left-color: #f59e0b; background: #fffbeb; }
    form label { display: block; font-weight: 500; margin: 15px 0 5px; color: var(--text); font-size: 0.95em; }
    form input, form select, form textarea { width: 100%; max-width: 500px; padding: 10px 12px;
        border: 1px solid var(--border); border-radius: 6px; font-family: inherit; font-size: 1em;
        transition: border-color 0.2s; background: #fff; }
    form input:focus, form select:focus, form textarea:focus { outline: none; border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1); }
    .btn { display: inline-flex; align-items: center; justify-content: center; background: var(--primary); color: white;
           padding: 10px 20px; border: none; border-radius: 6px; font-size: 1em; font-weight: 500;
           cursor: pointer; text-decoration: none; transition: background 0.2s, transform 0.1s; }
    .btn:active { transform: scale(0.98); }
    .btn:hover { background: var(--primary-hover); }
    .btn-danger { background: #ef4444; } .btn-danger:hover { background: #dc2626; }
    .btn-warning { background: #f59e0b; } .btn-warning:hover { background: #d97706; }
    .btn-sm { padding: 6px 12px; font-size: 0.85em; border-radius: 4px; }
    .empty { color: var(--text-muted); font-style: italic; padding: 20px 0; }
    .back-link { display: inline-flex; align-items: center; color: var(--primary); text-decoration: none;
                 font-weight: 500; margin-bottom: 15px; }
    .back-link:hover { text-decoration: underline; }
    .flash { padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; font-weight: 500; }
    .flash.error { background: #fef2f2; color: #991b1b; border: 1px solid #f87171; }
    .flash.success { background: #ecfdf5; color: #065f46; border: 1px solid #34d399; }
    .flash.info { background: #eff6ff; color: #1e40af; border: 1px solid #60a5fa; }
    .auth-box { max-width: 400px; margin: 40px auto; background: var(--surface);
                padding: 40px; border-radius: 16px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }
    .auth-box h1 { text-align: center; margin-bottom: 30px; }
    .auth-box button { width: 100%; margin-top: 20px; }
    .action-cell { display: flex; gap: 8px; align-items: center; }
    .action-cell form { margin: 0; }
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
    .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
                 padding: 25px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .stat-card .num { font-size: 2.5em; font-weight: 700; color: var(--primary); }
    .stat-card .label { color: var(--text-muted); font-weight: 500; margin-top: 5px; }
    footer { text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.85em; margin-top: auto; }
    .admin-link { color: #9ca3af; text-decoration: none; transition: 0.2s; margin-left: 10px; font-size: 1.2em; }
    .admin-link:hover { color: var(--primary); }
</style>
"""

# ============================================================
# ШАБЛОНЫ
# ============================================================
BASE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Электронный дневник{% endblock %}</title>
    """ + CSS + """
</head>
<body>
    <nav>
        <div class="brand">📖 Дневник</div>
        <a href="{{ url_for('index') }}" class="nav-link {% if request.path == '/' %}active{% endif %}">Главная</a>
        {% if current_user and current_user.role == 'student' %}
            <a href="{{ url_for('my_diary') }}" class="nav-link {% if request.path == '/my-diary' or '/subject/' in request.path %}active{% endif %}">Мои предметы</a>
            <a href="{{ url_for('student_schedule') }}" class="nav-link {% if request.path == '/my-schedule' %}active{% endif %}">Расписание</a>
            <div class="right">
                <span style="color:var(--text-muted); font-size:0.9em;">👤 {{ current_user.username }}</span>
                <a href="{{ url_for('student_logout') }}" style="color:#ef4444; text-decoration:none; font-weight:500;">Выйти</a>
            </div>
        {% endif %}
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, msg in messages %}
                <div class="flash {{ category }}">{{ msg }}</div>
            {% endfor %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
    <footer>
        © 2024 Электронный дневник. Все права защищены.
        <a href="{{ url_for('admin_login') }}" class="admin-link" title="Вход для администратора">⚙</a>
    </footer>
</body>
</html>
"""

ADMIN_BASE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}Админ-панель{% endblock %}</title>
    """ + CSS + """
</head>
<body>
    <nav class="admin-nav">
        <div class="brand">🛡 Админ-панель</div>
        <a href="{{ url_for('admin_dashboard') }}" class="nav-link {% if request.path == '/admin' %}active{% endif %}">Обзор</a>
        <a href="{{ url_for('admin_students') }}" class="nav-link {% if '/admin/students' in request.path %}active{% endif %}">Ученики</a>
        <a href="{{ url_for('admin_subjects') }}" class="nav-link {% if '/admin/subjects' in request.path %}active{% endif %}">Предметы</a>
        <a href="{{ url_for('admin_records') }}" class="nav-link {% if '/admin/records' in request.path %}active{% endif %}">Записи</a>
        <a href="{{ url_for('admin_schedule') }}" class="nav-link {% if '/admin/schedule' in request.path %}active{% endif %}">Расписание</a>
        <a href="{{ url_for('admin_users') }}" class="nav-link {% if '/admin/users' in request.path %}active{% endif %}">Аккаунты</a>
        <div class="right">
            <span style="color:#c7d2fe; font-size:0.9em;">👤 {{ current_user.username }}</span>
            <a href="{{ url_for('admin_logout') }}" style="background:#ef4444; color:white; padding:6px 12px; border-radius:6px; text-decoration:none;">Выйти</a>
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, msg in messages %}
                <div class="flash {{ category }}">{{ msg }}</div>
            {% endfor %}
        {% endwith %}
        <div class="card">
            {% block content %}{% endblock %}
        </div>
    </div>
</body>
</html>
"""

STUDENT_LOGIN = """
{% extends "base" %}
{% block title %}Вход ученика{% endblock %}
{% block content %}
<div class="auth-box">
    <h1>🎓 Вход</h1>
    <form method="POST">
        <label>Логин:</label>
        <input type="text" name="username" required autofocus>
        <label>Пароль:</label>
        <input type="password" name="password" required>
        <button type="submit" class="btn">Войти в дневник</button>
    </form>
</div>
{% endblock %}
"""

ADMIN_LOGIN = """
{% extends "admin_base" %}
{% block title %}Вход администратора{% endblock %}
{% block content %}
<div class="auth-box" style="box-shadow:none; padding: 20px;">
    <h1 style="color:#4f46e5;">🛡 Вход для администратора</h1>
    <form method="POST">
        <label>Логин:</label>
        <input type="text" name="username" required autofocus>
        <label>Пароль:</label>
        <input type="password" name="password" required>
        <button type="submit" class="btn" style="background:#1e1b4b;">Войти</button>
    </form>
</div>
{% endblock %}
"""

INDEX = """
{% extends "base" %}
{% block title %}Главная{% endblock %}
{% block content %}
<div class="card" style="text-align:center; padding: 60px 20px;">
    <h1 style="font-size:2.5em; margin-bottom:10px;">📖 Электронный дневник</h1>
    <p style="color:var(--text-muted); font-size:1.1em; margin-bottom:30px;">Современная система для просмотра успеваемости</p>

    {% if current_user and current_user.role == 'student' %}
        <p>Здравствуйте, <strong>{{ current_user.username }}</strong>!</p>
        <a class="btn" style="margin-top:20px;" href="{{ url_for('my_diary') }}">Перейти в мой дневник →</a>
    {% else %}
        <a class="btn" href="{{ url_for('student_login') }}">Войти как ученик</a>
    {% endif %}
</div>
{% endblock %}
"""

MY_DIARY = """
{% extends "base" %}
{% block title %}Мои предметы{% endblock %}
{% block content %}
<div class="card">
    <div class="profile-header">
        <div class="avatar">{{ student.full_name[0] }}</div>
        <div class="profile-info">
            <h2>{{ student.full_name }}</h2>
            <p>Класс: {{ student.class_name }}</p>
        </div>
    </div>

    <h1 style="font-size:1.4em; margin-bottom:20px;">📚 Мои предметы</h1>
    <div class="subject-grid">
        {% for s in subjects %}
        <a href="{{ url_for('subject_detail', subject_id=s.id) }}" class="subject-card">
            <div class="sub-header">
                {% if 'Матем' in s.name %}<div class="sub-icon icon-math">📐</div>
                {% elif 'Рус' in s.name or 'Лит' in s.name %}<div class="sub-icon icon-rus">📖</div>
                {% elif 'Физ' in s.name %}<div class="sub-icon icon-phys">🔬</div>
                {% elif 'Ист' in s.name %}<div class="sub-icon icon-hist">🏛</div>
                {% elif 'Инф' in s.name %}<div class="sub-icon icon-inf">💻</div>
                {% elif 'Англ' in s.name %}<div class="sub-icon icon-eng">🇬🇧</div>
                {% else %}<div class="sub-icon icon-default">📚</div>{% endif %}
                <div class="sub-title">{{ s.name }}</div>
            </div>

            <div class="sub-stats">
                <span class="sub-badge grades">📊 {{ s.grades_count }} оценок</span>
                <span class="sub-badge hw">📝 {{ s.homeworks_count }} заданий</span>

                {% if s.last_grades %}
                <div class="mini-grades">
                    {% for g in s.last_grades %}
                        <span class="mini-grade mg-{{ g }}">{{ g }}</span>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </a>
        {% else %}
        <p class="empty">Предметов пока нет.</p>
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

STUDENT_SCHEDULE = """
{% extends "base" %}
{% block title %}Расписание{% endblock %}
{% block content %}
<div class="card">
    <h1>🗓 Расписание уроков</h1>
    <p style="color:var(--text-muted); margin-bottom:20px;">Класс: <strong>{{ student.class_name }}</strong></p>

    <div class="schedule-grid">
        <div class="sch-header">Урок</div>
        <div class="sch-header">Понедельник</div>
        <div class="sch-header">Вторник</div>
        <div class="sch-header">Среда</div>
        <div class="sch-header">Четверг</div>
        <div class="sch-header">Пятница</div>

        {% for row in schedule_grid %}
            <div class="sch-time">{{ loop.index }}</div>
            {% for cell in row %}
                <div class="sch-cell">
                    {% if cell %}
                        {% for item in cell %}
                            <div style="margin-bottom:8px; width:100%;">
                                <div class="sch-subject">{{ item.subject_name or 'Отмена' }}</div>
                                {% if item.room %}<div class="sch-room">{{ item.room }}</div>{% endif %}
                                {% if item.note %}<div class="sch-note">{{ item.note }}</div>{% endif %}
                            </div>
                        {% endfor %}
                    {% else %}
                        <span style="color:#d1d5db;">—</span>
                    {% endif %}
                </div>
            {% endfor %}
        {% endfor %}
    </div>
</div>
{% endblock %}
"""

SUBJECT_DETAIL = """
{% extends "base" %}
{% block title %}{{ subject.name }}{% endblock %}
{% block content %}
<div class="card">
    <a href="{{ url_for('my_diary') }}" class="back-link">← Назад ко всем предметам</a>
    <h1>{{ subject.name }}</h1>
    <p style="color:var(--text-muted); margin-bottom:20px;">Ученик: <strong>{{ student.full_name }}</strong></p>

    <h2>📊 Оценки</h2>
    {% if grades %}
        <table>
            <tr><th>Оценка</th><th>Дата</th></tr>
            {% for g in grades %}
            <tr>
                <td><span class="grade grade-{{ g.content }}">{{ g.content }}</span></td>
                <td>{{ g.date_created[:10] }}</td>
            </tr>
            {% endfor %}
        </table>
    {% else %}<p class="empty">Оценок пока нет.</p>{% endif %}

    <h2>📚 Домашние задания</h2>
    {% if homeworks %}
        <ul class="card-list homework">
            {% for hw in homeworks %}
            <li>{{ hw.content }}</li>
            {% endfor %}
        </ul>
    {% else %}<p class="empty">Домашних заданий нет.</p>{% endif %}

    <h2>⚠️ Замечания</h2>
    {% if remarks %}
        <ul class="card-list remark">
            {% for r in remarks %}
            <li>{{ r.content }}</li>
            {% endfor %}
        </ul>
    {% else %}<p class="empty">Замечаний нет.</p>{% endif %}
</div>
{% endblock %}
"""

ADMIN_SCHEDULE = """
{% extends "admin_base" %}
{% block content %}
    <h1>🗓 Управление расписанием</h1>
    <p style="margin-bottom:20px;"><a class="btn" href="{{ url_for('admin_schedule_new') }}">➕ Добавить / изменить урок</a></p>

    {% for cls in classes %}
        <h2 style="margin-top:30px;">Класс: {{ cls }}</h2>
        <div style="overflow-x:auto;">
            <table style="background:#f9fafb; border-radius:8px;">
                <tr>
                    <th style="width:50px;">№</th>
                    <th>Пн</th><th>Вт</th><th>Ср</th><th>Чт</th><th>Пт</th><th>Сб</th>
                </tr>
                {% for row in schedule_matrix[cls] %}
                <tr>
                    <td><strong>{{ loop.index }}</strong></td>
                    {% for cell in row %}
                        <td style="padding:8px; vertical-align:top;">
                            {% if cell %}
                                {% for item in cell %}
                                    <div style="border-bottom:1px solid #e5e7eb; padding-bottom:4px; margin-bottom:4px;">
                                        <div style="font-weight:500; font-size:0.9em;">{{ item.subject_name or 'Отмена' }}</div>
                                        <div style="font-size:0.8em; color:#6b7280;">{{ item.room or '' }}</div>
                                        {% if item.note %}<div style="font-size:0.75em; color:#ef4444;">{{ item.note }}</div>{% endif %}
                                        <form method="POST" action="{{ url_for('admin_schedule_delete', sid=item.id) }}" style="margin-top:4px;">
                                            <button class="btn btn-danger btn-sm" style="padding:2px 6px; font-size:0.7em;">Удалить</button>
                                        </form>
                                    </div>
                                {% endfor %}
                            {% else %}
                                <span style="color:#d1d5db;">—</span>
                            {% endif %}
                        </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </table>
        </div>
    {% endfor %}
{% endblock %}
"""

ADMIN_SCHEDULE_FORM = """
{% extends "admin_base" %}
{% block content %}
    <a class="back-link" href="{{ url_for('admin_schedule') }}">← Назад к расписанию</a>
    <h1>Новый урок в расписании</h1>
    <form method="POST">
        <label>Класс (например: 9А):</label>
        <input type="text" name="class_name" required placeholder="9А" value="{{ request.args.get('class_name', '') }}">

        <label>День недели:</label>
        <select name="day_of_week" required>
            <option value="1">Понедельник</option>
            <option value="2">Вторник</option>
            <option value="3">Среда</option>
            <option value="4">Четверг</option>
            <option value="5">Пятница</option>
            <option value="6">Суббота</option>
        </select>

        <label>Номер урока (1-8):</label>
        <input type="number" name="lesson_number" required min="1" max="8">

        <label>Предмет:</label>
        <select name="subject_id">
            <option value="">— Отмена урока (нет предмета) —</option>
            {% for sub in subjects %}
            <option value="{{ sub.id }}">{{ sub.name }}</option>
            {% endfor %}
        </select>

        <label>Кабинет (необязательно):</label>
        <input type="text" name="room" placeholder="каб. 201">

        <label>Примечание (замена/отмена):</label>
        <input type="text" name="note" placeholder="Например: Замена учителя или Отменен">

        <button type="submit" class="btn" style="margin-top:20px;">Сохранить</button>
    </form>
{% endblock %}
"""

ADMIN_DASHBOARD = """
{% extends "admin_base" %}
{% block content %}
    <h1>Обзор системы</h1>
    <div class="stats-grid">
        <div class="stat-card"><div class="num">{{ stats.students }}</div><div class="label">Учеников</div></div>
        <div class="stat-card"><div class="num">{{ stats.subjects }}</div><div class="label">Предметов</div></div>
        <div class="stat-card"><div class="num">{{ stats.records }}</div><div class="label">Записей</div></div>
        <div class="stat-card"><div class="num">{{ stats.users }}</div><div class="label">Аккаунтов</div></div>
    </div>
{% endblock %}
"""

ADMIN_STUDENTS = """
{% extends "admin_base" %}
{% block content %}
    <h1>👨‍🎓 Ученики</h1>
    <p style="margin-bottom:20px;"><a class="btn" href="{{ url_for('admin_student_new') }}">➕ Добавить ученика</a></p>
    <table>
        <tr><th>ID</th><th>ФИО</th><th>Класс</th><th>Действия</th></tr>
        {% for s in students %}
        <tr>
            <td>{{ s.id }}</td>
            <td>{{ s.full_name }}</td>
            <td>{{ s.class_name }}</td>
            <td class="action-cell">
                <a class="btn btn-warning btn-sm" href="{{ url_for('admin_student_edit', sid=s.id) }}">✏️</a>
                <form method="POST" action="{{ url_for('admin_student_delete', sid=s.id) }}"
                      onsubmit="return confirm('Удалить ученика?');">
                    <button class="btn btn-danger btn-sm" type="submit">🗑</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="4" class="empty">Нет учеников.</td></tr>
        {% endfor %}
    </table>
{% endblock %}
"""

ADMIN_STUDENT_FORM = """
{% extends "admin_base" %}
{% block content %}
    <a class="back-link" href="{{ url_for('admin_students') }}">← Назад к списку</a>
    <h1>{{ 'Редактировать ученика' if student else 'Новый ученик' }}</h1>
    <form method="POST">
        <label>ФИО:</label>
        <input type="text" name="full_name" required value="{{ student.full_name if student else '' }}">
        <label>Класс:</label>
        <input type="text" name="class_name" required value="{{ student.class_name if student else '' }}">
        <button type="submit" class="btn" style="margin-top:20px;">Сохранить</button>
    </form>
{% endblock %}
"""

ADMIN_SUBJECTS = """
{% extends "admin_base" %}
{% block content %}
    <h1>📘 Предметы</h1>
    <div style="background:#f9fafb; padding:20px; border-radius:8px; margin-bottom:25px;">
        <form method="POST" action="{{ url_for('admin_subject_save') }}" style="display:flex; gap:15px; align-items:flex-end;">
            <div style="flex:1;">
                <label>Новый предмет:</label>
                <input type="text" name="name" required placeholder="Например: Геометрия">
            </div>
            <button type="submit" class="btn">Добавить</button>
        </form>
    </div>
    <table>
        <tr><th>ID</th><th>Название</th><th>Действия</th></tr>
        {% for sub in subjects %}
        <tr>
            <td>{{ sub.id }}</td>
            <td>{{ sub.name }}</td>
            <td class="action-cell">
                <form method="POST" action="{{ url_for('admin_subject_delete', subid=sub.id) }}"
                      onsubmit="return confirm('Удалить предмет?');">
                    <button class="btn btn-danger btn-sm" type="submit">🗑</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="3" class="empty">Нет предметов.</td></tr>
        {% endfor %}
    </table>
{% endblock %}
"""

ADMIN_RECORDS = """
{% extends "admin_base" %}
{% block content %}
    <h1>📝 Все записи</h1>
    <p style="margin-bottom:20px;"><a class="btn" href="{{ url_for('admin_record_new') }}">➕ Добавить запись</a></p>
    <div style="overflow-x:auto;">
        <table>
            <tr><th>Ученик</th><th>Предмет</th><th>Тип</th><th>Содержание</th><th>Дата</th><th>Действия</th></tr>
            {% for r in records %}
            <tr>
                <td>{{ r.student_name }}</td>
                <td>{{ r.subject_name }}</td>
                <td><span style="font-size:0.85em; padding:4px 8px; border-radius:4px; background:#e5e7eb;">{{ {'grade':'Оценка','homework':'ДЗ','remark':'Замечание'}[r.record_type] }}</span></td>
                <td>{{ r.content }}</td>
                <td>{{ r.date_created[:16] }}</td>
                <td class="action-cell">
                    <a class="btn btn-warning btn-sm" href="{{ url_for('admin_record_edit', rid=r.id) }}">✏️</a>
                    <form method="POST" action="{{ url_for('admin_record_delete', rid=r.id) }}"
                          onsubmit="return confirm('Удалить?');">
                        <button class="btn btn-danger btn-sm" type="submit">🗑</button>
                    </form>
                </td>
            </tr>
            {% else %}
            <tr><td colspan="6" class="empty">Записей нет.</td></tr>
            {% endfor %}
        </table>
    </div>
{% endblock %}
"""

ADMIN_RECORD_FORM = """
{% extends "admin_base" %}
{% block content %}
    <a class="back-link" href="{{ url_for('admin_records') }}">← Назад к списку</a>
    <h1>{{ 'Редактировать запись' if record else 'Новая запись' }}</h1>
    <form method="POST">
        <label>Ученик:</label>
        <select name="student_id" required>
            {% for s in students %}
            <option value="{{ s.id }}" {{ 'selected' if record and record.student_id == s.id }}>
                {{ s.full_name }} ({{ s.class_name }})
            </option>
            {% endfor %}
        </select>
        <label>Предмет:</label>
        <select name="subject_id" required>
            {% for sub in subjects %}
            <option value="{{ sub.id }}" {{ 'selected' if record and record.subject_id == sub.id }}>
                {{ sub.name }}
            </option>
            {% endfor %}
        </select>
        <label>Тип записи:</label>
        <select name="record_type" required>
            <option value="grade" {{ 'selected' if record and record.record_type=='grade' }}>Оценка</option>
            <option value="homework" {{ 'selected' if record and record.record_type=='homework' }}>Домашнее задание</option>
            <option value="remark" {{ 'selected' if record and record.record_type=='remark' }}>Замечание</option>
        </select>
        <label>Содержание:</label>
        <textarea name="content" rows="4" required>{{ record.content if record else '' }}</textarea>
        <button type="submit" class="btn" style="margin-top:20px;">Сохранить</button>
    </form>
{% endblock %}
"""

ADMIN_USERS = """
{% extends "admin_base" %}
{% block content %}
    <h1>👥 Аккаунты учеников</h1>
    <p style="margin-bottom:20px;"><a class="btn" href="{{ url_for('admin_user_new') }}">➕ Создать аккаунт</a></p>
    <table>
        <tr><th>Логин</th><th>Роль</th><th>Ученик</th><th>Создан</th><th>Действия</th></tr>
        {% for u in users %}
        <tr>
            <td><strong>{{ u.username }}</strong></td>
            <td>{{ 'Админ' if u.role == 'admin' else 'Ученик' }}</td>
            <td>{{ u.student_name or '—' }}</td>
            <td>{{ u.created_at[:16] }}</td>
            <td class="action-cell">
                {% if u.role != 'admin' %}
                <form method="POST" action="{{ url_for('admin_user_delete', uid=u.id) }}"
                      onsubmit="return confirm('Удалить аккаунт?');">
                    <button class="btn btn-danger btn-sm" type="submit">🗑</button>
                </form>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
{% endblock %}
"""

ADMIN_USER_FORM = """
{% extends "admin_base" %}
{% block content %}
    <a class="back-link" href="{{ url_for('admin_users') }}">← Назад к списку</a>
    <h1>Новый аккаунт</h1>
    <form method="POST">
        <label>Логин:</label>
        <input type="text" name="username" required minlength="3">
        <label>Пароль:</label>
        <input type="password" name="password" required minlength="6">
        <label>Привязать к ученику:</label>
        <select name="student_id" required>
            <option value="">— выберите ученика —</option>
            {% for s in students %}
            <option value="{{ s.id }}">{{ s.full_name }} ({{ s.class_name }})</option>
            {% endfor %}
        </select>
        <button type="submit" class="btn" style="margin-top:20px;">Создать</button>
    </form>
{% endblock %}
"""

app.jinja_loader = DictLoader({
    'base': BASE, 'admin_base': ADMIN_BASE,
    'student_login': STUDENT_LOGIN, 'admin_login': ADMIN_LOGIN,
    'index': INDEX, 'my_diary': MY_DIARY,
    'student_schedule': STUDENT_SCHEDULE,
    'subject_detail': SUBJECT_DETAIL,
    'admin_dashboard': ADMIN_DASHBOARD,
    'admin_students': ADMIN_STUDENTS, 'admin_student_form': ADMIN_STUDENT_FORM,
    'admin_subjects': ADMIN_SUBJECTS,
    'admin_records': ADMIN_RECORDS, 'admin_record_form': ADMIN_RECORD_FORM,
    'admin_users': ADMIN_USERS, 'admin_user_form': ADMIN_USER_FORM,
    'admin_schedule': ADMIN_SCHEDULE, 'admin_schedule_form': ADMIN_SCHEDULE_FORM,
})


# ============================================================
# МАРШРУТЫ
# ============================================================
@app.route('/')
def index():
    return render_template_string(INDEX)


@app.route('/login', methods=['GET', 'POST'])
def student_login():
    if session.get('role') == 'student':
        return redirect(url_for('my_diary'))
    if request.method == 'POST':
        user = query_db('SELECT * FROM users WHERE username=? AND role=?',
                        [request.form['username'].strip(), 'student'], one=True)
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session.clear()
            session.update(user_id=user['id'], username=user['username'],
                           role='student', student_id=user['student_id'])
            flash('Добро пожаловать!', 'success')
            return redirect(url_for('my_diary'))
        flash('Неверный логин или пароль.', 'error')
    return render_template_string(STUDENT_LOGIN)


@app.route('/logout')
def student_logout():
    session.clear()
    flash('Вы вышли.', 'info')
    return redirect(url_for('index'))


@app.route('/my-diary')
@student_required
def my_diary():
    sid = session.get('student_id')
    student = query_db('SELECT * FROM students WHERE id=?', [sid], one=True)
    if not student:
        flash('Аккаунт не привязан к ученику.', 'error')
        return redirect(url_for('index'))

    subjects = query_db('''
        SELECT s.id, s.name,
            (SELECT COUNT(*) FROM records r WHERE r.subject_id = s.id AND r.student_id = ? AND r.record_type = 'grade') AS grades_count,
            (SELECT COUNT(*) FROM records r WHERE r.subject_id = s.id AND r.student_id = ? AND r.record_type = 'homework') AS homeworks_count
        FROM subjects s ORDER BY s.name
    ''', [sid, sid])

    subjects_list = []
    for s in subjects:
        last_g = query_db('''
            SELECT content FROM records 
            WHERE student_id=? AND subject_id=? AND record_type='grade' 
            ORDER BY date_created DESC LIMIT 3
        ''', [sid, s['id']])

        sub_dict = dict(s)
        sub_dict['last_grades'] = [g['content'] for g in last_g]
        subjects_list.append(sub_dict)

    return render_template_string(MY_DIARY, student=student, subjects=subjects_list)


@app.route('/my-schedule')
@student_required
def student_schedule():
    sid = session.get('student_id')
    student = query_db('SELECT * FROM students WHERE id=?', [sid], one=True)
    if not student:
        return redirect(url_for('index'))

    schedule_grid = [[[] for _ in range(5)] for _ in range(8)]

    lessons = query_db('''
        SELECT sch.*, sub.name as subject_name
        FROM schedule sch
        LEFT JOIN subjects sub ON sch.subject_id = sub.id
        WHERE UPPER(sch.class_name) = UPPER(?) AND sch.day_of_week <= 5
        ORDER BY sch.id
    ''', [student['class_name']])

    for l in lessons:
        if 1 <= l['day_of_week'] <= 5 and 1 <= l['lesson_number'] <= 8:
            schedule_grid[l['lesson_number'] - 1][l['day_of_week'] - 1].append(l)

    return render_template_string(STUDENT_SCHEDULE, student=student, schedule_grid=schedule_grid)


@app.route('/my-diary/subject/<int:subject_id>')
@student_required
def subject_detail(subject_id):
    sid = session.get('student_id')
    student = query_db('SELECT * FROM students WHERE id=?', [sid], one=True)
    subject = query_db('SELECT * FROM subjects WHERE id=?', [subject_id], one=True)

    if not student or not subject:
        return redirect(url_for('my_diary'))

    records = query_db('''
        SELECT * FROM records 
        WHERE student_id = ? AND subject_id = ?
        ORDER BY date_created DESC
    ''', [sid, subject_id])

    return render_template_string(
        SUBJECT_DETAIL, student=student, subject=subject,
        grades=[r for r in records if r['record_type'] == 'grade'],
        homeworks=[r for r in records if r['record_type'] == 'homework'],
        remarks=[r for r in records if r['record_type'] == 'remark']
    )


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        user = query_db('SELECT * FROM users WHERE username=? AND role=?',
                        [request.form['username'].strip(), 'admin'], one=True)
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session.clear()
            session.update(user_id=user['id'], username=user['username'], role='admin')
            flash('Добро пожаловать!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Неверный логин или пароль.', 'error')
    return render_template_string(ADMIN_LOGIN)


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {
        'students': query_db('SELECT COUNT(*) c FROM students', one=True)['c'],
        'subjects': query_db('SELECT COUNT(*) c FROM subjects', one=True)['c'],
        'records': query_db('SELECT COUNT(*) c FROM records', one=True)['c'],
        'users': query_db('SELECT COUNT(*) c FROM users', one=True)['c'],
    }
    return render_template_string(ADMIN_DASHBOARD, stats=stats)


@app.route('/admin/students')
@admin_required
def admin_students():
    students = query_db('SELECT * FROM students ORDER BY full_name')
    return render_template_string(ADMIN_STUDENTS, students=students)


@app.route('/admin/students/add', methods=['GET', 'POST'])
@admin_required
def admin_student_new():
    if request.method == 'POST':
        fn = request.form['full_name'].strip()
        cn = request.form['class_name'].strip().upper()
        if fn and cn:
            execute_db('INSERT INTO students (full_name, class_name) VALUES (?, ?)', (fn, cn))
            flash('Добавлено.', 'success')
            return redirect(url_for('admin_students'))
    return render_template_string(ADMIN_STUDENT_FORM, student=None)


@app.route('/admin/students/<int:sid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_student_edit(sid):
    student = query_db('SELECT * FROM students WHERE id=?', [sid], one=True)
    if not student: return "Not found", 404
    if request.method == 'POST':
        fn = request.form['full_name'].strip()
        cn = request.form['class_name'].strip().upper()
        if fn and cn:
            execute_db('UPDATE students SET full_name=?, class_name=? WHERE id=?', (fn, cn, sid))
            flash('Обновлено.', 'success')
            return redirect(url_for('admin_students'))
    return render_template_string(ADMIN_STUDENT_FORM, student=student)


@app.route('/admin/students/<int:sid>/delete', methods=['POST'])
@admin_required
def admin_student_delete(sid):
    execute_db('DELETE FROM students WHERE id=?', [sid])
    flash('Удалено.', 'success')
    return redirect(url_for('admin_students'))


@app.route('/admin/subjects')
@admin_required
def admin_subjects():
    subjects = query_db('SELECT * FROM subjects ORDER BY name')
    return render_template_string(ADMIN_SUBJECTS, subjects=subjects)


@app.route('/admin/subjects/save', methods=['POST'])
@admin_required
def admin_subject_save():
    name = request.form['name'].strip()
    if name: execute_db('INSERT INTO subjects (name) VALUES (?)', [name])
    return redirect(url_for('admin_subjects'))


@app.route('/admin/subjects/<int:subid>/delete', methods=['POST'])
@admin_required
def admin_subject_delete(subid):
    execute_db('DELETE FROM subjects WHERE id=?', [subid])
    return redirect(url_for('admin_subjects'))


@app.route('/admin/records')
@admin_required
def admin_records():
    records = query_db('''
        SELECT r.*, st.full_name AS student_name, su.name AS subject_name
        FROM records r JOIN students st ON r.student_id = st.id
        JOIN subjects su ON r.subject_id = su.id ORDER BY r.date_created DESC
    ''')
    return render_template_string(ADMIN_RECORDS, records=records)


@app.route('/admin/records/add', methods=['GET', 'POST'])
@admin_required
def admin_record_new():
    if request.method == 'POST':
        sid = request.form['student_id']
        suid = request.form['subject_id']
        rt = request.form['record_type']
        c = request.form['content'].strip()
        if sid and suid and rt and c:
            execute_db('INSERT INTO records (student_id, subject_id, record_type, content) VALUES (?, ?, ?, ?)',
                       (sid, suid, rt, c))
            flash('Добавлено.', 'success')
            return redirect(url_for('admin_records'))
    students = query_db('SELECT * FROM students ORDER BY full_name')
    subjects = query_db('SELECT * FROM subjects ORDER BY name')
    return render_template_string(ADMIN_RECORD_FORM, record=None, students=students, subjects=subjects)


@app.route('/admin/records/<int:rid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_record_edit(rid):
    record = query_db('SELECT * FROM records WHERE id=?', [rid], one=True)
    if not record: return "Not found", 404
    if request.method == 'POST':
        sid = request.form['student_id']
        suid = request.form['subject_id']
        rt = request.form['record_type']
        c = request.form['content'].strip()
        if sid and suid and rt and c:
            execute_db('UPDATE records SET student_id=?, subject_id=?, record_type=?, content=? WHERE id=?',
                       (sid, suid, rt, c, rid))
            flash('Обновлено.', 'success')
            return redirect(url_for('admin_records'))
    students = query_db('SELECT * FROM students ORDER BY full_name')
    subjects = query_db('SELECT * FROM subjects ORDER BY name')
    return render_template_string(ADMIN_RECORD_FORM, record=record, students=students, subjects=subjects)


@app.route('/admin/records/<int:rid>/delete', methods=['POST'])
@admin_required
def admin_record_delete(rid):
    execute_db('DELETE FROM records WHERE id=?', [rid])
    flash('Удалено.', 'success')
    return redirect(url_for('admin_records'))


# --- АДМИН: РАСПИСАНИЕ ---
@app.route('/admin/schedule')
@admin_required
def admin_schedule():
    classes_rows = query_db('SELECT DISTINCT class_name FROM students ORDER BY class_name')
    classes = [c['class_name'] for c in classes_rows]

    schedule_matrix = {}
    for cls in classes:
        matrix = [[[] for _ in range(6)] for _ in range(8)]
        lessons = query_db('''
            SELECT sch.*, sub.name as subject_name
            FROM schedule sch
            LEFT JOIN subjects sub ON sch.subject_id = sub.id
            WHERE UPPER(sch.class_name) = UPPER(?)
            ORDER BY sch.id
        ''', [cls])
        for l in lessons:
            day_idx = l['day_of_week'] - 1
            les_idx = l['lesson_number'] - 1
            if 0 <= day_idx < 6 and 0 <= les_idx < 8:
                matrix[les_idx][day_idx].append(l)
        schedule_matrix[cls] = matrix

    return render_template_string(ADMIN_SCHEDULE, classes=classes, schedule_matrix=schedule_matrix)


@app.route('/admin/schedule/new', methods=['GET', 'POST'])
@admin_required
def admin_schedule_new():
    if request.method == 'POST':
        cls = request.form['class_name'].strip().upper()
        day = request.form['day_of_week']
        num = request.form['lesson_number']
        sub_id = request.form['subject_id'] or None
        room = request.form['room'].strip()
        note = request.form['note'].strip()

        try:
            execute_db('''INSERT INTO schedule (class_name, day_of_week, lesson_number, subject_id, room, note) 
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (cls, day, num, sub_id, room, note))
            flash('Урок добавлен.', 'success')
            return redirect(url_for('admin_schedule'))
        except Exception as e:
            flash(f'Ошибка базы данных: {str(e)}', 'error')

    subjects = query_db('SELECT * FROM subjects ORDER BY name')
    return render_template_string(ADMIN_SCHEDULE_FORM, subjects=subjects)


@app.route('/admin/schedule/<int:sid>/delete', methods=['POST'])
@admin_required
def admin_schedule_delete(sid):
    execute_db('DELETE FROM schedule WHERE id=?', [sid])
    flash('Урок удален из расписания.', 'success')
    return redirect(url_for('admin_schedule'))


@app.route('/admin/users')
@admin_required
def admin_users():
    users = query_db('''
        SELECT u.*, s.full_name AS student_name
        FROM users u LEFT JOIN students s ON u.student_id = s.id ORDER BY u.id
    ''')
    return render_template_string(ADMIN_USERS, users=users)


@app.route('/admin/users/new', methods=['GET', 'POST'])
@admin_required
def admin_user_new():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        student_id = request.form['student_id']
        if username and password and student_id:
            if not query_db('SELECT id FROM users WHERE username=?', [username], one=True) and \
                    not query_db('SELECT id FROM users WHERE student_id=?', [student_id], one=True):
                execute_db('INSERT INTO users (username, password_hash, role, student_id) VALUES (?, ?, ?, ?)',
                           (username, generate_password_hash(password), 'student', student_id))
                flash('Аккаунт создан.', 'success')
                return redirect(url_for('admin_users'))
            flash('Логин занят или у ученика уже есть аккаунт.', 'error')
    students = query_db('SELECT * FROM students ORDER BY full_name')
    return render_template_string(ADMIN_USER_FORM, students=students)


@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_user_delete(uid):
    user = query_db('SELECT * FROM users WHERE id=?', [uid], one=True)
    if user and user['role'] != 'admin':
        execute_db('DELETE FROM users WHERE id=?', [uid])
        flash('Удалено.', 'success')
    return redirect(url_for('admin_users'))


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    check_and_fix_db()
    print('🚀 http://127.0.0.1:5000')
    app.run(debug=True)