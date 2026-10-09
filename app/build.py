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
        f'A fonte "Scraped from web" reúne {len(extra)} sonhos com Shiba Inu e LUNC achados no YouTube (vídeos e comentários), '
        'Reddit, 4chan /biz/, TikTok, X, Facebook, Instagram, Binance Square e Stocktwits, em inglês, português e espanhol, '
        'coletados em 09/10/2026. Cada um tem o link da fonte. Não passam pelo sync diário e não entram nas escadas de preço.']
    return dict(dataset, E=dataset['E'] + extra, meta=meta)


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
