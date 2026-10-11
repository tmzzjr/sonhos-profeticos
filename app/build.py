"""Monta a página (HTML único) a partir do dataset e do template."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

HEAD_META = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="lang-routing" content="path">'
    '<meta name="description" content="Sonhos, visões e preços proféticos do propheticmoney.com, da Lista Lucas Borin e da web, organizados numa linha de acontecimentos futuros. Atualizado todo dia.">'
    '<meta property="og:title" content="Sonhos e preços proféticos">'
    '<meta property="og:description" content="A linha de acontecimentos futuros e os preços sonhados para cada moeda, juntando o propheticmoney.com e a Lista Lucas Borin.">'
    '<meta property="og:type" content="website">'
    '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}img{max-width:100%}</style>'
)


WEB = os.path.join(HERE, '..', 'data', 'seed', 'web.json')


def with_web(dataset):
    """Junta os sonhos achados na web (origem 'w'), que ficam fora do sync diário."""
    if not os.path.exists(WEB):
        return dataset
    have = {e.get('i') for e in dataset['E']}
    extra = [e for e in json.load(open(WEB, encoding='utf-8')) if e.get('i') not in have]
    meta = dict(dataset.get('meta') or {})
    meta['metodo'] = list(meta.get('metodo') or []) + [
        f'A fonte "Scraped from web" reúne {len(extra)} sonhos com SHIB, LUNC, XRP, XLM, BNB Frog e PEPE achados no YouTube (vídeos e comentários, inclusive todos os do canal Prophetic Insight), '
        'Reddit, 4chan /biz/, TikTok, X, Facebook, Instagram, Binance Square e Stocktwits, em inglês, português e espanhol, '
        'coletados entre 09 e 11/10/2026. Cada um tem o link da fonte. Não passam pelo sync diário. Os preços citados neles entram nas escadas de preço e na timeline de acontecimentos.']
    out = dict(dataset, E=dataset['E'] + extra, meta=meta)
    wp_path = os.path.join(os.path.dirname(WEB), 'web_points.json')
    if os.path.exists(wp_path):
        wp = json.load(open(wp_path, encoding='utf-8'))
        out['A'] = [dict(a, pts=a['pts'] + wp['A'].get(a['tk'], [])) for a in dataset['A']]
        F = dataset['F']
        out['F'] = dict(F, coins=[dict(c, all=c['all'] + wp['F'].get(c['tk'], [])) for c in F['coins']])
        out['F']['ev'] = [dict(ev, ids=ev['ids'] + wp.get('ev', {}).get(str(k), [])) for k, ev in enumerate(F['ev'], 1)]
    return out


def render(dataset, template_path=None):
    dataset = with_web(dataset)
    t = open(template_path or os.path.join(HERE, 'template.html'), encoding='utf-8').read()
    js = json.dumps(dataset, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = t.replace('/*__DATA__*/', js)
    cut = page.index('</style>') + len('</style>')
    head, body = page[:cut], page[cut:]
    return '<!doctype html><html lang="pt-BR"><head>' + HEAD_META + head + '</head><body>' + body + '</body></html>'


if __name__ == '__main__':
    import sys
    data = json.load(open(sys.argv[1], encoding='utf-8'))
    open(sys.argv[2], 'w', encoding='utf-8').write(render(data))
