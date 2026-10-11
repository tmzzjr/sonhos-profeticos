"""Preços dos sonhos da web (origem 'w') para as escadas de preço e a timeline de acontecimentos.

Lê data/seed/web.json e data/seed/market.json e grava data/seed/web_points.json com os pontos
de cada ativo (A) e de cada moeda da timeline (F), no mesmo formato que o sync usa,
mas marcados com 'o': 'w'. Rodar de novo sempre que web.json mudar:

    python3 app/web_points.py
"""
import json
import os

import sync

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, '..', 'data', 'seed')
# a página usa 'BNB FROG' em 'as'; o sync usa o rótulo 'BNB Frog'
LABEL = {'BNB FROG': 'BNB Frog'}


def build():
    web = json.load(open(os.path.join(SEED, 'web.json'), encoding='utf-8'))
    mk = json.load(open(os.path.join(SEED, 'market.json'), encoding='utf-8'))
    D = json.load(open(os.path.join(SEED, 'dataset.json'), encoding='utf-8'))
    M = sync.Market(mk)
    a_tk = {a['tk'] for a in D['A']}
    f_tk = {c['tk'] for c in D['F']['coins']}
    out = {'A': {}, 'F': {}, 'ev': {}}
    for e in web:
        for lab, v, note in e.get('pr') or []:
            lab = LABEL.get(lab, lab)
            key = sync.LABEL2KEY.get(lab)
            p = {'v': v, 'p': e['p'], 'd': e.get('d'), 'n': note, 'o': 'w', 'i': e['i'], 'lk': e.get('u'), '_g': str(sync.sig(v, 6))}
            if key:
                M.check(key, p)
            if lab in a_tk:
                out['A'].setdefault(lab, []).append({k: x for k, x in p.items() if x is not None})
            stage = M.stage_for(key, v, e.get('d'), note) if key else None
            if lab in f_tk and stage:
                q = {'e': stage, 'v': v, 'p': e['p'], 'd': e.get('d'), 'n': note, 'o': 'w', 'i': e['i'], 'lk': e.get('u')}
                out['F'].setdefault(lab, []).append({k: x for k, x in q.items() if x is not None})
                ids = out['ev'].setdefault(str(stage), [])
                if e['i'] not in ids:
                    ids.append(e['i'])
    json.dump(out, open(os.path.join(SEED, 'web_points.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return out


if __name__ == '__main__':
    o = build()
    print({k: sum(map(len, v.values())) for k, v in o.items()})
