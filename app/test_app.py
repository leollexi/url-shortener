import sys, types
fake_db = {}  # code -> {"u": url, "c": clicks}

class FakeCursor:
    def __init__(self): self._last=None
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def execute(self, sql, params=None):
        s=sql.strip().upper()
        if s.startswith("CREATE TABLE"): self._last=None
        elif s.startswith("SELECT CODE, ORIGINAL_URL, CLICKS"):
            self._last=[dict(code=k,original_url=v["u"],clicks=v["c"]) for k,v in fake_db.items()]
        elif s.startswith("SELECT CODE FROM LINKS WHERE ORIGINAL_URL"):
            url=params[0]
            found=[k for k,v in fake_db.items() if v["u"]==url]
            self._last=dict(code=found[0]) if found else None
        elif s.startswith("SELECT 1 FROM LINKS WHERE CODE"):
            code=params[0]
            self._last=dict(one=1) if code in fake_db else None
        elif s.startswith("INSERT"):
            code,url=params; fake_db[code]={"u":url,"c":0}; self._last=dict(code=code)
        elif s.startswith("SELECT ORIGINAL_URL"):
            code=params[0]; self._last=dict(original_url=fake_db[code]["u"]) if code in fake_db else None
        elif s.startswith("UPDATE"):
            code=params[0]
            if code in fake_db: fake_db[code]["c"]+=1
            self._last=None
        else:
            self._last=None
    def fetchall(self): return self._last or []
    def fetchone(self): return self._last

class FakeConn:
    def cursor(self,**k): return FakeCursor()
    def commit(self): pass
    def close(self): pass

psy=types.ModuleType("psycopg2"); psy.connect=lambda *a,**k: FakeConn()
extras=types.ModuleType("psycopg2.extras"); extras.RealDictCursor=object; psy.extras=extras
sys.modules["psycopg2"]=psy; sys.modules["psycopg2.extras"]=extras

import app as application
client = application.app.test_client()

def test_index():
    assert client.get("/").status_code == 200

def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.get_json()["status"] == "ok"

def test_shorten_and_redirect():
    r = client.post("/shorten", json={"url":"https://example.com"},
                    headers={"Host":"localhost:8080"})
    data = r.get_json()
    assert ":8080" in data["short_url"]
    r2 = client.get("/"+data["code"])
    assert r2.status_code == 302
    assert r2.headers["Location"] == "https://example.com"

def test_404():
    assert client.get("/nonexistent").status_code == 404

def test_dedup_same_url_same_code():
    """Одинаковый URL должен возвращать ОДИН И ТОТ ЖЕ код."""
    r1 = client.post("/shorten", json={"url":"https://dedup-test.com"}, headers={"Host":"localhost:8080"})
    r2 = client.post("/shorten", json={"url":"https://dedup-test.com"}, headers={"Host":"localhost:8080"})
    assert r1.get_json()["code"] == r2.get_json()["code"], "коды должны совпадать для одинакового URL"

def test_different_url_different_code():
    """Разные URL - разные коды."""
    r1 = client.post("/shorten", json={"url":"https://aaa.com"}, headers={"Host":"localhost:8080"})
    r2 = client.post("/shorten", json={"url":"https://bbb.com"}, headers={"Host":"localhost:8080"})
    assert r1.get_json()["code"] != r2.get_json()["code"]

def test_version():
    r = client.get("/version")
    assert r.status_code == 200
    data = r.get_json()
    assert "version" in data and "git_sha" in data and "build_time" in data

def test_health_checks_db():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok" and data["database"] == "ok"