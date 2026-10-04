"""Monta a página (HTML único) a partir do dataset e do template."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

HEAD_META = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="lang-routing" content="path">'
    '<meta name="description" content="Sonhos, visões e preços proféticos do propheticmoney.com e da Lista Lucas Borin, organizados numa linha de acontecimentos futuros. Atualizado todo dia.">'
    '<meta property="og:title" content="Sonhos e preços proféticos">'
    '<meta property="og:description" content="A linha de acontecimentos futuros e os preços sonhados para cada moeda, juntando o propheticmoney.com e a Lista Lucas Borin.">'
    '<meta property="og:type" content="website">'
    '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}img{max-width:100%}</style>'
)


def render(dataset, template_path=None):
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
