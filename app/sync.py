"""Sincronização diária com o propheticmoney.com, sem IA.

Tudo aqui é regra e expressão regular:
- posts novos viram sonhos (profeta, data, tipo, tema, prazo, preços e acontecimento futuro);
- linhas novas nas páginas de preço de cada moeda viram preços sonhados;
- cabeçalhos novos nas compilações "Other Prophecies" viram sonhos;
- as cotações de mercado são atualizadas e o "já bateu" é recalculado;
- a página é reconstruída.
"""
import bisect
import collections
import datetime
import html as htmlmod
import json
import os
import re
import statistics
import time
import traceback
import unicodedata
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
WP = 'https://propheticmoney.com/wp-json/wp/v2'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; sonhos-profeticos-sync/1.0)', 'Accept': 'application/json'}

AGG_PAGES = {393: 'SHIB', 467: 'XRP', 481: 'LUNC', 464: 'XLM', 423: 'ETN', 4272: 'ETH', 4282: None, 5770: 'ZNOG', 474: 'BTC', 21: 'BNB Tiger antiga'}
COMPILATIONS = [9670, 9703, 9995]
SKIP_POSTS = set(AGG_PAGES) | set(COMPILATIONS) | {1212, 13877}


# ---------------------------------------------------------------- utilidades
def get_json(url, tries=3, pause=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(pause * (k + 1))


def html_to_text(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', h or '', flags=re.S)
    h = re.sub(r'<br\s*/?>|</p>|</li>|</h\d>', '\n', h)
    t = htmlmod.unescape(re.sub(r'<[^>]+>', '', h))
    return re.sub(r'\n\s*\n+', '\n', t).strip()


def nodash(s, title=False):
    if s is None:
        return None
    s = str(s).replace(' — ', ': ' if title else ', ').replace(' – ', ': ' if title else ', ')
    s = s.replace('—', ', ').replace('–', '-').replace('--', ', ')
    return re.sub(r'\s+,', ',', s).strip()


def clean_url(u):
    if not u:
        return None
    u = u.strip().rstrip('.,);').replace('—', '---').replace('–', '--')
    return u if u.startswith('http') else None


def strip_acc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')


def nk(name):
    k = strip_acc((name or '').lower())
    k = re.sub(r'\([^)]*\)', '', k)
    k = re.sub(r'^(prophet|prophetess|profeta|pastor|apostle|dr\.?)\s+', '', k.strip())
    return re.sub(r'[^a-z0-9]', '', k)


def sig(v, n=6):
    if v is None or v == 0:
        return v
    return float(f'{v:.{n}g}')


def us_date(s):
    """M/D/YY ou M/D/YYYY (formato do site) para ISO."""
    m = re.match(r'^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$', s or '')
    if not m:
        return None
    mo, d, y = int(m[1]), int(m[2]), int(m[3])
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def dparse(s):
    m = re.match(r'^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?', s or '')
    if not m:
        return None
    return datetime.date(int(m[1]), int(m[2] or 1), int(m[3] or 1))


MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
MON3 = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}


# ---------------------------------------------------------------- ativos
# rótulo usado na página -> chave do histórico de mercado
LABEL2KEY = {'BTC': 'BTC', 'ETH': 'ETH', 'XRP': 'XRP', 'XLM': 'XLM', 'SHIB': 'SHIB', 'LUNC': 'LUNC', 'ETN': 'ETN', 'Ouro': 'OURO', 'Prata': 'PRATA',
             'ZNOG': 'ZNOG', 'WKC': 'WKC', 'ADA': 'ADA', 'XDC': 'XDC', 'HBAR': 'HBAR', 'PEPE': 'PEPE', 'BONK': 'BONK', 'BNB': 'BNB', 'POL': 'POL',
             'KISHU': 'KISHU', 'CREPE': 'CREPE', 'VOLT': 'VOLT', 'BNB Tiger antiga': 'BNB TIGER (antiga)', 'BNB Tiger nova': 'BNB TIGER INU (nova)',
             'BNB Frog': 'BNB FROG', 'DOGE': 'DOGE', 'SOL': 'SOL', 'Cobre': 'COBRE'}
ASSET_WORDS = [(r'bitcoin|btc', 'BTC'), (r'ethereum|eth', 'ETH'), (r'xrp|ripple', 'XRP'), (r'shiba\s*inu|shib', 'SHIB'), (r'xlm|stellar', 'XLM'),
               (r'luna\s*classic|lunc', 'LUNC'), (r'electroneum|etn', 'ETN'), (r'gold', 'Ouro'), (r'silver', 'Prata'), (r'zion\s*oil|znog', 'ZNOG'),
               (r'wiki\s*cat|wkc', 'WKC'), (r'cardano|ada', 'ADA'), (r'bnb\s*tiger', 'BNB Tiger antiga')]
TAG_ASSET = {'bitcoin': 'BTC', 'btc': 'BTC', 'xrp': 'XRP', 'ripple': 'XRP', 'shiba-inu': 'SHIB', 'shib': 'SHIB', 'xlm': 'XLM', 'stellar': 'XLM',
             'eth': 'ETH', 'ethereum': 'ETH', 'lunc': 'LUNC', 'luna-classic': 'LUNC', 'etn': 'ETN', 'electroneum': 'ETN', 'gold': 'Ouro',
             'silver': 'Prata', 'znog': 'ZNOG', 'ada': 'ADA', 'cardano': 'ADA', 'doge': 'DOGE', 'bnb-tiger': 'BNB Tiger antiga', 'algo': 'ALGO',
             'algorand': 'ALGO', 'xdc': 'XDC', 'copper': 'Cobre', 'oil': 'Petróleo', 'dollar': 'Dólar', 'dinar': 'Dinar', 'pepe': 'PEPE'}
MEME = {'SHIB', 'LUNC', 'WKC', 'ETN', 'KISHU', 'VOLT', 'PEPE', 'BONK', 'CREPE', 'DOGE', 'SHI', 'BNB TIGER (antiga)', 'BNB TIGER INU (nova)', 'BNB FROG', 'BNB LION INU', 'BNB LION CA'}
ISO = {'XRP', 'XLM', 'XDC', 'ADA', 'HBAR', 'ALGO', 'POL'}
METAL = {'OURO', 'PRATA', 'COBRE', 'PLATINA', 'ZNOG', 'PETROLEO'}
BIG = {'BTC', 'ETH', 'BNB', 'SOL'}

# ---------------------------------------------------------------- mercado
SPEC = {'BTC': ('binance', 'BTCUSDT'), 'ETH': ('binance', 'ETHUSDT'), 'XRP': ('binance', 'XRPUSDT'), 'XLM': ('binance', 'XLMUSDT'),
        'SHIB': ('binance', 'SHIBUSDT'), 'LUNC': ('binance', 'LUNCUSDT'), 'ADA': ('binance', 'ADAUSDT'), 'HBAR': ('binance', 'HBARUSDT'),
        'PEPE': ('binance', 'PEPEUSDT'), 'BONK': ('binance', 'BONKUSDT'), 'BNB': ('binance', 'BNBUSDT'), 'POL': ('binance', 'POLUSDT'),
        'ETN': ('kucoin', 'ETN-USDT'), 'XDC': ('kucoin', 'XDC-USDT'), 'OURO': ('yahoo', 'GC=F'), 'PRATA': ('yahoo', 'SI=F'), 'ZNOG': ('yahoo', 'ZNOG'),
        'WKC': ('gate', 'WKC_USDT'), 'KISHU': ('mexc', 'KISHUUSDT'), 'CREPE': ('mexc', 'CREPEUSDT'),
        'BNB TIGER (antiga)': ('gecko', '0xac68931b666e086e9de380cfdb0fb5704a35dc2d'), 'BNB TIGER INU (nova)': ('gecko', '0xf8584516b7d2c156c763c874d6813e06b57e4cb5'),
        'BNB FROG': ('gecko', '0x64da67a12a46f1ddf337393e2da12ed0a507ad3d'), 'BNB LION CA': ('gecko', '0x71d421b6de07cefa2733d044f92a0306308de8b8'),
        'BNB LION INU': ('gecko', '0xda1689c5557564d06e2a546f8fd47350b9d44a73'), 'VOLT': ('gecko', '0x7db5af2b9624e1b3b4bb69d6debd9ad1016a58ac')}


def _d(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')


def fetch_recent(key, days=45):
    src, sym = SPEC[key]
    now = int(time.time())
    if src == 'binance':
        for host in ('https://data-api.binance.vision', 'https://api.binance.com'):
            try:
                d = get_json(f'{host}/api/v3/klines?symbol={sym}&interval=1d&limit={days}')
                return [[_d(k[0] / 1000), float(k[2]), float(k[3]), float(k[4])] for k in d]
            except Exception:
                continue
        raise RuntimeError('binance indisponível')
    if src == 'kucoin':
        d = get_json(f'https://api.kucoin.com/api/v1/market/candles?type=1day&symbol={sym}&startAt={now - days * 86400}&endAt={now}')['data']
        return sorted([_d(int(k[0])), float(k[3]), float(k[4]), float(k[2])] for k in d)
    if src == 'yahoo':
        d = get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={days}d&interval=1d')['chart']['result'][0]
        q = d['indicators']['quote'][0]
        return [[_d(ts), h or c, l or c, c] for ts, h, l, c in zip(d['timestamp'], q['high'], q['low'], q['close']) if c is not None]
    if src == 'gate':
        d = get_json(f'https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={sym}&interval=1d&limit={days}')
        return [[_d(int(k[0])), float(k[3]), float(k[4]), float(k[2])] for k in d]
    if src == 'mexc':
        d = get_json(f'https://api.mexc.com/api/v3/klines?symbol={sym}&interval=1d&limit={days}')
        return [[_d(k[0] / 1000), float(k[2]), float(k[3]), float(k[4])] for k in d]
    if src == 'gecko':
        pools = get_json(f'https://api.geckoterminal.com/api/v2/networks/bsc/tokens/{sym}/pools?page=1')['data']
        if not pools:
            return []
        pool = pools[0]['attributes']['address']
        base = pools[0]['relationships']['base_token']['data']['id']
        token = 'base' if sym.lower() in base.lower() else 'quote'
        time.sleep(3)
        d = get_json(f'https://api.geckoterminal.com/api/v2/networks/bsc/pools/{pool}/ohlcv/day?limit={days}&token={token}')['data']['attributes']['ohlcv_list']
        time.sleep(3)
        return sorted([_d(k[0]), k[2], k[3], k[4]] for k in d)
    return []


def refresh_market(mk, log):
    H = mk['hist']
    ok, fail = [], []
    for key in SPEC:
        try:
            rows = fetch_recent(key)
            if not rows:
                continue
            by = {r[0]: r for r in H.get(key, [])}
            for r in rows:
                by[r[0]] = r
            H[key] = sorted(by.values())
            ok.append(key)
        except Exception as e:
            fail.append(f'{key}: {e.__class__.__name__}')
        time.sleep(0.4)
    log(f'mercado: {len(ok)} atualizados, {len(fail)} falharam {fail[:6]}')
    return ok, fail


# ---------------------------------------------------------------- preço x mercado
class Market:
    def __init__(self, mk):
        self.H = mk['hist']
        self.idx = {k: [r[0] for r in v] for k, v in self.H.items()}

    def price_at(self, k, d):
        if k not in self.H or not d:
            return None
        dd = dparse(d)
        if not dd:
            return None
        ds = dd.isoformat()
        i = bisect.bisect_left(self.idx[k], ds)
        if i >= len(self.H[k]):
            i = len(self.H[k]) - 1
        if i == 0 and self.idx[k][0] > ds and (datetime.date.fromisoformat(self.idx[k][0]) - dd).days > 30:
            return None
        return self.H[k][i][3]

    def check(self, k, p):
        """Recalcula se o preço sonhado já bateu depois da data do sonho."""
        for f in ('st', 'hd', 'mx', 'dirc'):
            p.pop(f, None)
        if p.get('cur'):
            p['st'] = 'nc'; return
        if p.get('v') is None:
            p['st'] = 'nodate' if not p.get('d') else 'nd'; return
        if not p.get('d'):
            p['st'] = 'nodate'; return
        rows = self.H.get(k)
        if not rows:
            p['st'] = 'nd'; return
        d0 = dparse(p['d']).isoformat()
        after = rows[bisect.bisect_left(self.idx[k], d0):]
        if not after:
            p['st'] = 'nd'; return
        covered = rows[0][0] <= (dparse(p['d']) + datetime.timedelta(days=7)).isoformat()
        v = p['v']
        up = v >= after[0][3]
        hit = next((r for r in after if (r[1] >= v if up else r[2] <= v)), None)
        p['dirc'] = 'up' if up else 'down'
        if hit:
            p['st'] = 'hit'; p['hd'] = hit[0]
        elif covered:
            p['st'] = 'miss'; p['mx'] = sig(max(r[1] for r in after) if up else min(r[2] for r in after))
        else:
            p['st'] = 'nd'

    def up_stage(self, k):
        if k in MEME: return 6
        if k in ISO: return 7
        if k in METAL: return 5
        return 1

    def stage_for(self, k, v, d, note):
        """Etapa da linha de acontecimentos para um preço, comparando com o mercado do dia do sonho."""
        n = (note or '').lower()
        if v == 0:
            return 3 if k not in METAL else 4
        if any(w in n for w in ('antes do crash', 'before the crash', 'pico antes', 'manufactured')):
            return 1
        if any(w in n for w in ('crash', 'queda', 'zero', 'buy limit', 'compra')) and k not in METAL:
            return 3
        p0 = self.price_at(k, d) or (self.H[k][-1][3] if k in self.H else None)
        if p0 and v < p0 * 0.4 and k not in METAL:
            return 3
        return self.up_stage(k)


# ---------------------------------------------------------------- classificação por regras
STAGE_RULES = [
    (2, r'hack|cyber|blackout|black out|power grid|emp\b|outage|exchanges? (?:go(?:es)? )?down|rug pull|manipulat'),
    (3, r'flash crash|crash(?:es)? to zero|goes? to zero|to zero|plummet|plunge|crypto crash|bitcoin crash|wiped out'),
    (4, r'bank(?:s|ing)? (?:collapse|fail|crash|run)|collapse of (?:the )?(?:banks|dollar|economy)|dollar (?:collapse|crash)|recession|depression|stock market crash|financial collapse|economic collapse|babylon'),
    (5, r'(?:gold|silver|precious metals?|oil)\b[^.]{0,40}\b(?:skyrocket|explode|soar|surge|triple|rise|jump|moon|breakthrough|priceless)|zion oil|znog|gold standard'),
    (6, r'(?:shib|shiba|lunc|luna classic|memecoin|meme coin|bnb tiger|wkc|wiki cat|kishu|volt|bonk|pepe)\b[^.]{0,40}\b(?:surge|rise|spike|explode|soar|moon|\$)'),
    (7, r'\bxrp\b|\bxlm\b|stellar|iso ?20022|\bqfs\b|quantum financial|new financial system|reset|revalu|dinar|digital (?:dollar|currency)'),
    (8, r'wealth transfer|transfer of wealth|debt(?:s)? (?:cancel|wiped|forgiv)|jubilee|inheritance|millionaires|billionaires|harvest'),
    (1, r'bull run|crypto (?:will )?(?:rise|surge|soar|explode)|bitcoin (?:to|hits?|at) \$?1\d\dk|all[- ]time high|manufactured (?:spike|pump)|crypto rises'),
]


def classify_stage(text):
    t = text.lower()
    scores = {k: len(re.findall(rx, t)) for k, rx in STAGE_RULES}
    pos = [k for k, s in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])) if s > 0]
    return pos


TEMA_PRIO = [('cryptocurrency', 'Cripto'), ('precious-metals', 'Metais preciosos'), ('stocks', 'Ações e empresas'), ('bank-collapse', 'Economia e bancos'),
             ('currency', 'Moedas e dólar'), ('economy', 'Economia e bancos'), ('real-estate', 'Economia e bancos'), ('war', 'Guerra e geopolítica'),
             ('trump', 'Política'), ('rapture-tribulation', 'Fim dos tempos'), ('aliens-ufos', 'Outros'), ('wealth-transfer', 'Transferência de riqueza'),
             ('warnings', 'Outros')]
NUM = r'\$\s?(?P<n>\d[\d,]*(?:\.\d+)?)\s*(?P<u>k\b|m\b|million|billion|trillion)?'
AW = '(?P<a>' + '|'.join(w for w, _ in ASSET_WORDS) + ')'
RX_P1 = re.compile(NUM + r'\s+' + AW + r'\b', re.I)
RX_P2 = re.compile(AW + r"\b[^$\n]{0,25}?\b(?:to|at|hit|hits|reach|reaches|of|=|price of|surge to|soars? to)\s+" + NUM, re.I)
RX_BY = re.compile(r"\b(?:prophec(?:y|ies)|prophetic \w+|dream|vision|word|teaching|message|warning|declaration|revelation)\b[^.\n]{0,40}?\bby\s+(?P<name>[A-Z][\w.'’ ]{1,60}?)(?:\s+(?:from|of)\s+[^\n]{1,40}?)?\s+on\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})", re.I)
RX_SHARED = re.compile(r"\bshared(?:\s+by)?\s+(?P<name>[A-Z][\w.'’ ]{1,60}?)(?:\s+(?:from|of)\s+[^\n]{1,40}?)?\s+on\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})")
RX_BY_NODATE = re.compile(r"\b(?:prophec(?:y|ies)|prophetic \w+|dream|vision|word|teaching)\b[^.\n]{0,30}?\bby\s+(?P<name>[A-Z][\w.'’]+(?:\s+[A-Z][\w.'’]*){0,3})")
RX_ANYDATE = re.compile(r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b')
RX_VIDEODATE = re.compile(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(20\d\d)\b')
RX_QUOTE = re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?\s*[–—-]\s*(.+)$', re.M)
RX_ALVO_M = re.compile(r'\b(?:in|by|before|until|during|this|next)\s+(?:the\s+)?(?:(?:end|beginning|start|fall|summer|spring|winter|month)\s+of\s+)?(' + '|'.join(MONTHS) + r')\s+(?:of\s+)?(20\d\d)\b', re.I)
RX_ALVO_Y = re.compile(r'\b(?:in|by|before|until|during|for|through)\s+(?:the\s+)?(?:(?:end|beginning|fall|summer|spring|winter|year)\s+of\s+)?(20\d\d)\b', re.I)


def parse_value(n, u):
    v = float(n.replace(',', ''))
    u = (u or '').lower()
    mult = {'k': 1e3, 'm': 1e6, 'million': 1e6, 'billion': 1e9, 'trillion': 1e12}.get(u, 1)
    return v * mult


def label_of(word):
    w = word.lower()
    for rx, lab in ASSET_WORDS:
        if re.fullmatch(rx, w):
            return lab
    return None


class Sync:
    def __init__(self, D, mk, state, log=print):
        self.D, self.mk, self.state, self.log = D, mk, state, log
        self.M = Market(mk)
        self.people = {}
        for e in D['E']:
            for p in (e.get('ps') or []) + [e['p']]:
                self.people.setdefault(nk(p), p)
        self.ids = {e['i'] for e in D['E']}
        self.A = {a['tk']: a for a in D['A']}
        self.coins = {c['tk']: c for c in D['F']['coins']}
        self.DX = D.setdefault('DX', {})
        self.res = collections.Counter()

    # ------------------------------------------------ nomes
    def canon(self, name):
        if not name:
            return None
        name = nodash(name).strip(' .,:;')
        k = nk(name)
        if k in self.people:
            return self.people[k]
        words = re.findall(r"[A-Za-zÀ-ú0-9.'’]+", name)
        toks = {strip_acc(w.lower()).strip(".'’") for w in words}
        # mesmo nome com ou sem inicial do meio (Robin Bullock = Robin D. Bullock)
        if len(toks) >= 2:
            for pk, disp in self.people.items():
                ptoks = set(re.findall(r'[a-z0-9]+', strip_acc(disp.lower())))
                if toks <= ptoks and len(ptoks) - len(toks) <= 1:
                    return disp
        # nome conhecido seguido de descrição (Hank Kunneman Discusses..., Christianos Servant Of God)
        for n in range(min(len(words), 4), 0, -1):
            pk = nk(' '.join(words[:n]))
            if pk in self.people and (n >= 2 or len(pk) >= 8):
                return self.people[pk]
        return name

    def person_from_tags(self, tags):
        for slug in tags:
            toks = set(slug.split('-'))
            if len(toks) < 2:
                continue
            for k, disp in self.people.items():
                words = set(re.findall(r'[a-z0-9]+', strip_acc(disp.lower())))
                if toks <= words:
                    return disp
        return None

    # ------------------------------------------------ inclusão de um sonho
    def add_entry(self, e, stages, prices):
        """e: dicionário no formato da página. stages: [principal, ...]. prices: [(rótulo, valor, nota_pt, nota_en)]."""
        if e['i'] in self.ids:
            return False
        e = {k: v for k, v in e.items() if v not in (None, '', [])}
        pr = []
        for lab, v, n_pt, n_en in prices:
            pr.append([lab, v, n_pt])
            if n_en and n_pt and n_pt != n_en:
                self.DX[n_pt] = n_en
        if pr:
            e['pr'] = pr
        self.D['E'].append(e)
        self.ids.add(e['i'])
        for k in dict.fromkeys(stages):
            if 1 <= k <= 8:
                self.D['F']['ev'][k - 1]['ids'].append(e['i'])
        for lab, v, n_pt, _ in prices:
            self.add_point(lab, v, e, n_pt)
        self.res['sonhos'] += 1
        return True

    def add_point(self, lab, v, e, note):
        key = LABEL2KEY.get(lab)
        st = self.M.stage_for(key, v, e.get('d'), note) if key else None
        a = self.A.get(lab)
        if a is not None:
            p = {'v': v, 'p': e['p'], 'd': e.get('d'), 'n': note, 'o': 's', 'i': e['i'], 'lk': e.get('v') or e.get('u'), '_g': str(sig(v, 6))}
            if key:
                self.M.check(key, p)
            a['pts'].append({k: x for k, x in p.items() if x is not None})
        c = self.coins.get(lab)
        if c is not None and st:
            c['all'].append({k: x for k, x in {'e': st, 'v': v, 'p': e['p'], 'd': e.get('d'), 'n': note, 'o': 's', 'i': e['i'], 'lk': e.get('v') or e.get('u')}.items() if x is not None})
        self.res['precos'] += 1

    # ------------------------------------------------ posts novos
    def extract_prices(self, text):
        out, seen = [], set()
        for rx in (RX_P1, RX_P2):
            for m in rx.finditer(text):
                lab = label_of(m.group('a'))
                if not lab:
                    continue
                try:
                    v = parse_value(m.group('n'), m.group('u'))
                except ValueError:
                    continue
                key = LABEL2KEY.get(lab)
                cur = self.M.H[key][-1][3] if key in self.M.H else None
                if v <= 0 or (cur and v > cur * 1e6):
                    continue
                if (lab, sig(v, 4)) in seen:
                    continue
                seen.add((lab, sig(v, 4)))
                out.append((lab, v, 'citado no post', 'mentioned in the post'))
        return out[:8]

    def alvo(self, text, d):
        y0 = (dparse(d) or datetime.date.today()).year
        m = RX_ALVO_M.search(text)
        if m and int(m[2]) >= y0:
            mi = MONTHS.index(m[1].lower())
            a = f'{m[2]}-{mi + 1:02d}'
            pt, en = f'em {MESES[mi]} de {m[2]}', f'in {MONTHS[mi].capitalize()} {m[2]}'
            self.DX[pt] = en
            return a, pt
        m = RX_ALVO_Y.search(text)
        if m and int(m[1]) >= y0:
            pt, en = f'em {m[1]}', f'in {m[1]}'
            self.DX[pt] = en
            return m[1], pt
        return None, None

    def process_post(self, post, cats, tags):
        pid = post['id']
        title = nodash(htmlmod.unescape(post['title']['rendered']), True)
        text = html_to_text(post['content']['rendered'])
        head = text[:1500]
        catslugs = [cats.get(c, '') for c in post.get('categories', [])]
        tagslugs = [tags.get(t, '') for t in post.get('tags', [])]
        # profeta e data
        name, d, dt = None, None, 'c'
        for rx in (RX_BY, RX_SHARED):
            m = rx.search(head)
            if m:
                name, d = m.group('name'), us_date(m.group('date'))
                break
        if not name:
            m = RX_BY_NODATE.search(head)
            if m:
                name = m.group('name')
        if not name:
            name = self.person_from_tags(tagslugs)
        name = self.canon(name) or 'Prophetic Money'
        if not d:
            m = RX_ANYDATE.search(head)
            d = us_date(m.group(1)) if m else None
        if not d:
            m = RX_VIDEODATE.search(head)
            if m:
                try:
                    d = datetime.date(int(m[3]), MON3[m[1][:3].lower()], int(m[2])).isoformat()
                except ValueError:
                    d = None
        if not d:
            d = post['date'][:10]
        # tipo
        low = head.lower()
        if 'teaching' in catslugs and 'prophecy' not in catslugs:
            tipo = 'ensino'
        elif name == 'Prophetic Money' or 'news' in catslugs or 'summary-posts' in catslugs:
            tipo = 'análise'
        elif 'dream' in low or 'dream' in title.lower():
            tipo = 'sonho'
        elif 'vision' in low or 'vision' in title.lower():
            tipo = 'visão'
        else:
            tipo = 'palavra'
        # tema
        tema = next((t for slug, t in TEMA_PRIO if slug in catslugs), 'Outros')
        # status do site
        f = 'failed-prophecies' in catslugs
        c = 'fulfilled-prophecies' in catslugs or 'prophecy-fulfilled' in catslugs
        s = 'p' if (f and c) else 'f' if f else 'c' if c else None
        a, at = self.alvo(title + '\n' + text[:3000], d)
        if s == 'f' and a and a >= datetime.datetime.now(NY).date().isoformat()[:len(a)]:
            s = None
        mq = RX_QUOTE.search(text)
        q = None
        if mq:
            q = nodash(mq.group(1)).strip()
            if len(q) > 200:
                q = q[:197].rsplit(' ', 1)[0] + '…'
        ativos = sorted({TAG_ASSET[t] for t in tagslugs if t in TAG_ASSET})
        prices = self.extract_prices(title + '\n' + text[:4000])
        stages = classify_stage(title + '\n' + text[:3000])
        price_stages = [self.M.stage_for(LABEL2KEY.get(l), v, d, None) for l, v, _, _ in prices if LABEL2KEY.get(l)]
        money = tema in ('Cripto', 'Metais preciosos', 'Ações e empresas', 'Economia e bancos', 'Moedas e dólar', 'Transferência de riqueza') or prices
        if tipo in ('ensino', 'análise') or not money:
            stages = []
        else:
            stages = stages + [s2 for s2 in price_stages if s2 not in stages]
            if not stages and 'wealth-transfer' in catslugs:
                stages = [8]
        e = dict(i=str(pid), d=d, dt=dt, p=name, t=tipo, m=tema, r=title, q=q, a=a, at=at, u=post['link'], ut=title, s=s, o='s',
                 **({'as': ativos} if ativos else {}))
        self.add_entry(e, stages, prices)

    def sync_posts(self, cats, tags):
        seen = set(self.state['seen_posts'])
        news, page = [], 1
        while page <= 5:
            batch = get_json(f'{WP}/posts?per_page=50&page={page}&orderby=date&order=desc&_fields=id,date,link,title,content,categories,tags')
            fresh = [p for p in batch if p['id'] not in seen]
            news += fresh
            if len(fresh) < len(batch) or len(batch) < 50:
                break
            page += 1
        for p in sorted(news, key=lambda p: p['date']):
            if p['id'] not in SKIP_POSTS:
                try:
                    self.process_post(p, cats, tags)
                except Exception:
                    self.log('erro no post %s: %s' % (p['id'], traceback.format_exc(limit=1)))
            self.state['seen_posts'].append(p['id'])
            self.D['meta']['nPosts'] = len(self.state['seen_posts'])
            if p['date'][:10] > self.D['meta'].get('ultimoPost', ''):
                self.D['meta']['ultimoPost'] = p['date'][:10]
        self.res['posts'] += len(news)
        return news

    # ------------------------------------------------ páginas de preço
    @staticmethod
    def agg_lines(text):
        for line in text.split('\n'):
            line = line.strip()
            m = re.search(r'\(?\b(\d{1,2}/\d{1,2}/\d{2,4})\b\)?', line)
            if not m or '$' not in line[:m.start()] or len(line) > 400:
                continue
            yield line, m

    def sync_aggregators(self, seed_only=False):
        seen = set(self.state['seen_lines'])
        for pid, lab0 in AGG_PAGES.items():
            try:
                post = get_json(f'{WP}/posts/{pid}?_fields=id,link,content')
            except Exception:
                self.log(f'página {pid} indisponível'); continue
            text = html_to_text(post['content']['rendered'])
            for line, m in self.agg_lines(text):
                h = re.sub(r'\s+', ' ', line)
                if h in seen:
                    continue
                seen.add(h); self.state['seen_lines'].append(h)
                if seed_only:
                    continue
                d = us_date(m.group(1))
                before = line[:m.start()].rstrip(' (–—-')
                parts = re.split(r'\s+[–—-]\s+', before)
                if len(parts) < 2:
                    continue
                who, price_txt = parts[-1].strip(), ' – '.join(parts[:-1])
                ml = re.search(r'https?://\S+', line[m.end():])
                link = clean_url(ml.group(0)) if ml else None
                lab = lab0
                if lab is None:
                    lab = 'Ouro' if re.search(r'gold', price_txt, re.I) else 'Prata' if re.search(r'silver', price_txt, re.I) else None
                if not lab:
                    continue
                vals = []
                for mm in re.finditer(NUM, price_txt, re.I):
                    try:
                        vals.append(parse_value(mm.group('n'), mm.group('u')))
                    except ValueError:
                        pass
                if not vals or not d:
                    continue
                name = self.canon(who)
                note = nodash(re.sub(NUM, '', price_txt, flags=re.I)).strip(' ,>–-') or None
                v_txt = ' > '.join(f'${x:,.10g}' for x in vals)
                r_pt = f'Viu {lab} a ' + ' e depois '.join(f'US$ {x:,.10g}'.replace(',', 'X').replace('.', ',').replace('X', '.') for x in vals) + '.'
                r_en = f'Saw {lab} at ' + ', then '.join(f'${x:,.10g}' for x in vals) + '.'
                self.DX[r_pt] = r_en
                e = dict(i=f'{pid}-n{len(self.state["seen_lines"])}', d=d, dt='c', p=name, t='preço', m='Metais preciosos' if lab in ('Ouro', 'Prata') else 'Cripto',
                         r=r_pt, u=post['link'], v=link, o='s', **{'as': [lab]})
                key = LABEL2KEY.get(lab)
                stages = [self.M.stage_for(key, x, d, note) for x in vals] if key else []
                self.add_entry(e, [s for s in stages if s], [(lab, x, note or 'lista de preços do site', None) for x in vals])
                self.res['linhas'] += 1
                self.log(f'nova linha de preço: {lab} {v_txt} {name} {d}')

    # ------------------------------------------------ compilações "Other Prophecies"
    def sync_compilations(self, seed_only=False):
        seen = set(self.state['seen_headers'])
        for pid in COMPILATIONS:
            try:
                post = get_json(f'{WP}/posts/{pid}?_fields=id,link,content')
            except Exception:
                self.log(f'compilação {pid} indisponível'); continue
            lines = [l.strip() for l in html_to_text(post['content']['rendered']).split('\n') if l.strip()]
            for i, line in enumerate(lines):
                m = re.match(r"^(?P<name>[A-Z][\w.'’&() ,@-]{1,60}?)\s*[–—-]?\s*(?P<date>\d{1,2}/\d{1,2}/\d{2,4})$", line)
                if not m:
                    continue
                key = f'{pid}|{line}'
                if key in seen:
                    continue
                seen.add(key); self.state['seen_headers'].append(key)
                if seed_only:
                    continue
                d = us_date(m.group('date'))
                link = clean_url(lines[i - 1]) if i > 0 and lines[i - 1].startswith('http') else None
                body = []
                for l2 in lines[i + 1:i + 8]:
                    if re.match(r"^[A-Z][\w.'’&() ,@-]{1,60}?\s*[–—-]?\s*\d{1,2}/\d{1,2}/\d{2,4}$", l2):
                        break
                    if l2.startswith('http'):
                        if not link:
                            link = clean_url(l2)
                        continue
                    body.append(re.sub(r'^\d{1,2}:\d{2}(?::\d{2})?\s*[–—-]\s*', '', l2))
                if not body or not d:
                    continue
                txt = nodash(' '.join(body))
                r = txt if len(txt) <= 240 else txt[:237].rsplit(' ', 1)[0] + '…'
                prices = self.extract_prices(txt)
                stages = classify_stage(txt) + [self.M.stage_for(LABEL2KEY.get(l), v, d, None) for l, v, _, _ in prices if LABEL2KEY.get(l)]
                tipo = 'sonho' if 'dream' in txt.lower() else 'visão' if 'vision' in txt.lower() else 'palavra'
                tema = 'Cripto' if prices or re.search(r'crypto|bitcoin|xrp|shib|lunc|xlm', txt, re.I) else 'Transferência de riqueza'
                e = dict(i=f'{pid}-h{len(self.state["seen_headers"])}', d=d, dt='c', p=self.canon(m.group('name')), t=tipo, m=tema, r=r,
                         q=(r if len(r) <= 200 else r[:197].rsplit(' ', 1)[0] + '…'), u=post['link'], v=link, o='s')
                self.add_entry(e, list(dict.fromkeys(stages)), prices)
                self.res['compilacoes'] += 1

    # ------------------------------------------------ mercado -> página
    def recompute_market(self):
        H = self.M.H
        today = datetime.datetime.now(NY).date().isoformat()
        for a in self.D['A']:
            key = a['k']
            rows = H.get(key) or []
            if rows:
                a['cur'], a['curD'] = sig(rows[-1][3]), rows[-1][0]
                ath = max(rows, key=lambda r: r[1])
                a['ath'], a['athD'] = sig(ath[1]), ath[0]
                ser, last = [], None
                for r in rows:
                    wk = dparse(r[0]).isocalendar()[:2]
                    if wk != last:
                        ser.append([r[0], sig(r[3], 5)]); last = wk
                    else:
                        ser[-1] = [r[0], sig(r[3], 5)]
                a['s'] = ser
            for p in a['pts']:
                self.M.check(key, p)
        for c in self.D['F']['coins']:
            key = LABEL2KEY.get(c['tk'])
            rows = H.get(key) or []
            if rows:
                c['cur'], c['curD'] = sig(rows[-1][3]), rows[-1][0]
        self.D['meta']['hoje'] = today


def run(D, mk, state, log=print, market=True):
    """Roda a sincronização inteira. Altera D, mk e state no lugar e devolve um resumo."""
    t0 = time.time()
    s = Sync(D, mk, state, log)
    cats = {c['id']: c['slug'] for c in get_json(f'{WP}/categories?per_page=100&_fields=id,slug')}
    tags = {}
    for page in range(1, 10):
        batch = get_json(f'{WP}/tags?per_page=100&page={page}&_fields=id,slug')
        if not batch:
            break
        tags.update({t['id']: t['slug'] for t in batch})
    news = s.sync_posts(cats, tags)
    s.sync_aggregators()
    s.sync_compilations()
    if market:
        refresh_market(mk, log)
        s.M = Market(mk)
    s.recompute_market()
    out = dict(quando=datetime.datetime.now(NY).isoformat(timespec='seconds'), posts_novos=len(news), sonhos_novos=s.res['sonhos'],
               precos_novos=s.res['precos'], linhas_de_preco=s.res['linhas'], entradas_de_compilacao=s.res['compilacoes'],
               segundos=round(time.time() - t0, 1))
    state['last_sync'] = out['quando']
    state['last_result'] = out
    log('sync: ' + json.dumps(out, ensure_ascii=False))
    return out


def seed_seen(state, D, mk, log=print):
    """Marca como vistas as linhas e cabeçalhos que já existem hoje nas páginas do site (para não duplicar)."""
    s = Sync(D, mk, state, log)
    s.sync_aggregators(seed_only=True)
    s.sync_compilations(seed_only=True)
    log(f"semente: {len(state['seen_lines'])} linhas de preço e {len(state['seen_headers'])} cabeçalhos já vistos")
