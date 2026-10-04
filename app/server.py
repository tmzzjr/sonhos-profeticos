"""Servidor da página + agendador do sync diário (meia-noite em Nova York)."""
import datetime
import gzip
import json
import os
import shutil
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
import sync  # noqa: E402

ROOT = os.path.dirname(HERE)
SEED = os.path.join(ROOT, 'data', 'seed')
DATA = os.environ.get('DATA_DIR') or ('/data' if os.path.isdir('/data') and os.access('/data', os.W_OK) else os.path.join(ROOT, 'data', 'runtime'))
NY = ZoneInfo('America/New_York')
SYNC_TOKEN = os.environ.get('SYNC_TOKEN', '')
LOCK = threading.Lock()
PAGE = {'html': b'', 'gz': b'', 'etag': ''}


def log(msg):
    print(datetime.datetime.now(NY).strftime('%Y-%m-%d %H:%M:%S %Z'), msg, flush=True)


def path(name):
    return os.path.join(DATA, name)


def load(name):
    with open(path(name), encoding='utf-8') as f:
        return json.load(f)


def save(name, obj):
    tmp = path(name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path(name))


def ensure_data():
    os.makedirs(DATA, exist_ok=True)
    for name in ('dataset.json', 'market.json', 'state.json'):
        if not os.path.exists(path(name)):
            shutil.copy(os.path.join(SEED, name), path(name))
            log(f'semente copiada: {name}')


def rebuild():
    D = load('dataset.json')
    html = build.render(D).encode('utf-8')
    with LOCK:
        PAGE['html'] = html
        PAGE['gz'] = gzip.compress(html, 6)
        PAGE['etag'] = '"%x"' % (hash(html) & 0xffffffffffff)
    log(f'página montada: {len(html) // 1024} KB, {len(D["E"])} sonhos')


SYNC_RUNNING = threading.Lock()


def do_sync(market=True):
    if not SYNC_RUNNING.acquire(blocking=False):
        log('sync já está rodando')
        return None
    try:
        D, mk, state = load('dataset.json'), load('market.json'), load('state.json')
        if not state.get('seen_lines'):
            sync.seed_seen(state, D, mk, log)
        out = sync.run(D, mk, state, log, market=market)
        save('dataset.json', D)
        save('market.json', mk)
        save('state.json', state)
        rebuild()
        return out
    except Exception:
        log('sync falhou: ' + traceback.format_exc())
        return None
    finally:
        SYNC_RUNNING.release()


def next_midnight_ny(now=None):
    now = now or datetime.datetime.now(NY)
    tomorrow = (now + datetime.timedelta(days=1)).date()
    return datetime.datetime.combine(tomorrow, datetime.time(0, 0), NY)


def scheduler():
    while True:
        target = next_midnight_ny()
        log(f'próximo sync: {target.isoformat()}')
        while True:
            left = (target - datetime.datetime.now(NY)).total_seconds()
            if left <= 0:
                break
            time.sleep(min(left, 300))
        do_sync()


class Handler(BaseHTTPRequestHandler):
    server_version = 'sonhos-profeticos'

    def log_message(self, fmt, *args):
        pass

    def send_page(self, head_only=False):
        with LOCK:
            html, gz, etag = PAGE['html'], PAGE['gz'], PAGE['etag']
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304); self.end_headers(); return
        use_gz = 'gzip' in (self.headers.get('Accept-Encoding') or '')
        body = gz if use_gz else html
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'public, max-age=300')
        self.send_header('ETag', etag)
        if use_gz:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_HEAD(self):
        p = self.path.split('?')[0].rstrip('/') or '/'
        if p in ('/', '/eng', '/index.html'):
            return self.send_page(head_only=True)
        self.send_response(404); self.end_headers()

    def do_GET(self):
        p, _, qs = self.path.partition('?')
        p = p.rstrip('/') or '/'
        if p in ('/', '/eng', '/index.html'):
            return self.send_page()
        if p == '/healthz':
            return self.send_json({'ok': True})
        if p == '/status.json':
            st = load('state.json')
            return self.send_json({'ultimo_sync': st.get('last_sync'), 'resultado': st.get('last_result'),
                                   'proximo_sync': next_midnight_ny().isoformat(), 'posts_vistos': len(st.get('seen_posts', []))})
        if p == '/sync':
            token = dict(x.split('=', 1) for x in qs.split('&') if '=' in x).get('token', '')
            if not SYNC_TOKEN or token != SYNC_TOKEN:
                return self.send_json({'erro': 'token inválido'}, 403)
            threading.Thread(target=do_sync, daemon=True).start()
            return self.send_json({'ok': True, 'mensagem': 'sync iniciado, veja /status.json em alguns minutos'})
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write('Página não encontrada'.encode('utf-8'))


def main():
    ensure_data()
    rebuild()
    threading.Thread(target=scheduler, daemon=True).start()
    if os.environ.get('SYNC_ON_START') == '1':
        threading.Thread(target=do_sync, daemon=True).start()
    port = int(os.environ.get('PORT', '8080'))
    log(f'servindo na porta {port}, dados em {DATA}')
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
