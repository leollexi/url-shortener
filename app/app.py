import os
import string
import random
import time

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, redirect, jsonify, render_template_string
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)

metrics = PrometheusMetrics(app)

def build_short_url(code):
    host = request.headers.get("X-Forwarded-Host") or request.host  # host:port
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)  # http/https
    return f"{scheme}://{host}/{code}"

DB_HOST = os.environ.get("DB_HOST", "db")
DB_NAME = os.environ.get("DB_NAME", "urls")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASS = os.environ.get("DB_PASS", "secret")

APP_VERSION = os.environ.get("APP_VERSION", "dev")
GIT_SHA = os.environ.get("GIT_SHA", "unknown")
BUILD_TIME = os.environ.get("BUILD_TIME", "unknown")

ALPHABET = string.ascii_letters + string.digits  # символы для короткого кода


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        cursor_factory=RealDictCursor,
    )


def init_db():
    for attempt in range(10):
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS links (
                        id SERIAL PRIMARY KEY,
                        code VARCHAR(10) UNIQUE NOT NULL,
                        original_url TEXT NOT NULL,
                        clicks INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
            conn.commit()
            conn.close()
            print("[init_db] Таблица готова.", flush=True)
            return
        except Exception as e:
            print(f"[init_db] Попытка {attempt+1}: БД ещё не готова ({e})", flush=True)
            time.sleep(2)
    raise RuntimeError("Не удалось подключиться к БД после 10 попыток")


def generate_code(length=6):
    return "".join(random.choices(ALPHABET, k=length))


PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>URL Shortener</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 60px auto; padding: 0 16px; }
    h1 { color: #2d6cdf; }
    input[type=url] { width: 100%; padding: 12px; font-size: 16px; box-sizing: border-box; }
    button { margin-top: 12px; padding: 12px 20px; font-size: 16px; background: #2d6cdf; color: #fff; border: 0; border-radius: 6px; cursor: pointer; }
    .result { margin-top: 24px; padding: 16px; background: #f0f5ff; border-radius: 8px; }
    .back-link { display: inline-block; margin-top: 16px; padding: 10px 18px; background: #eee; color: #333; text-decoration: none; border-radius: 6px; }
    .back-link:hover { background: #ddd; }
    a { color: #2d6cdf; }
    table { width: 100%; border-collapse: collapse; margin-top: 30px; }
    td, th { padding: 8px; border-bottom: 1px solid #eee; text-align: left; font-size: 14px; }
  </style>
</head>
<body>
  <h1>Вставь длинную ссылку и получишь короткую.</h1>
  <form method="post" action="/shorten">
    <input type="url" name="url" placeholder="https://example.com/very/long/url" required>
    <button type="submit">Сократить</button>
  </form>
  {% if short %}
  <div class="result">
    Готово! Короткая ссылка:
    <a href="{{ short }}">{{ short }}</a>
  </div>
  <p><a class="back-link" href="/">← На главную</a></p>
  {% endif %}
  {% if links %}
  <table>
    <tr><th>Код</th><th>Оригинал</th><th>Кликов</th></tr>
    {% for l in links %}
    <tr>
      <td><a href="/{{ l.code }}">{{ l.code }}</a></td>
      <td>{{ l.original_url[:50] }}</td>
      <td>{{ l.clicks }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endif %}
</body>
</html>
"""


@app.route("/")
def index():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT code, original_url, clicks FROM links ORDER BY id DESC LIMIT 10;")
        links = cur.fetchall()
    conn.close()
    return render_template_string(PAGE, links=links, short=None)


@app.route("/shorten", methods=["POST"])
def shorten():
    original = request.form.get("url") or (request.json or {}).get("url")
    if not original:
        return jsonify({"error": "url is required"}), 400

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT code FROM links WHERE original_url = %s;", (original,))
        row = cur.fetchone()
        if row:
            code = row["code"]
        else:
            for _ in range(5):
                candidate = generate_code()
                cur.execute("SELECT 1 FROM links WHERE code = %s;", (candidate,))
                if not cur.fetchone():
                    code = candidate
                    break
            cur.execute(
                "INSERT INTO links (code, original_url) VALUES (%s, %s) RETURNING code;",
                (code, original),
            )
            code = cur.fetchone()["code"]
    conn.commit()
    conn.close()

    short_url = build_short_url(code)
    if request.is_json:
        return jsonify({"short_url": short_url, "code": code})
    return render_template_string(PAGE, short=short_url, links=None)


@app.route("/<code>")
def follow(code):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT original_url FROM links WHERE code = %s;", (code,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return "Ссылка не найдена", 404
        cur.execute("UPDATE links SET clicks = clicks + 1 WHERE code = %s;", (code,))
    conn.commit()
    conn.close()
    return redirect(row["original_url"])


@app.route("/health")
def health():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        conn.close()
        return jsonify({"status": "ok", "database": "ok"})
    except Exception as e:
        return jsonify({"status": "degraded", "database": "down", "error": str(e)}), 503


@app.route("/version") 
def version():
    return jsonify({
        "version": APP_VERSION,
        "git_sha": GIT_SHA,
        "build_time": BUILD_TIME,
    })  


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
