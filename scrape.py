# Aggiorna quotes.json con quote, rigoristi e statistiche da fantacalcio.it
import re, json, sys, urllib.request, datetime

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=90).read().decode('utf-8', 'replace')

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()

def parse_rows(html):
    out = []
    for block in re.findall(r'<tr[^>]*class="[^"]*player-row[\s\S]*?</tr>', html):
        m = re.search(r'class="role"[^>]*data-value="([a-zA-Z])"', block)
        role = (m.group(1) if m else '').upper()
        cells = {}
        for cm in re.finditer(r'<t[dh][^>]*class="([^"]*)"[^>]*>([\s\S]*?)</t[dh]>', block):
            k = (cm.group(1) or '').split(' ')[0]
            cells.setdefault(k, []).append(clean(cm.group(2)))
        out.append((role, cells))
    return out

def cell(c, k, i=0, d=''):
    v = c.get(k, [])
    return v[i] if i < len(v) else d

def num(x):
    try: return int(x)
    except: return 0

def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFD', s)
    return re.sub(r'[^a-z]', '', ''.join(ch for ch in s if not unicodedata.combining(ch)).lower())

quotes = parse_rows(get('https://www.fantacalcio.it/quotazioni-fantacalcio'))
stats  = parse_rows(get('https://www.fantacalcio.it/statistiche-serie-a/2025-26'))
righ   = get('https://www.fantacalcio.it/rigoristi-serie-a')

rig_names, cp_names = set(), set()
cards = re.findall(r'class="card team-card"[\s\S]*?(?=class="card team-card"|<footer)', righ)
for card in cards:
    lists = re.findall(r'<ol[^>]*pill-list[\s\S]*?</ol>', card)
    names = [[clean(a) for a in re.findall(r'<a[^>]*>([\s\S]*?)</a>', o)] for o in lists]
    if len(names) > 0: rig_names.update(norm(n) for n in names[0])
    if len(names) > 1: cp_names.update(norm(n) for n in names[1])

smap = {}
for role, c in stats:
    n = cell(c, 'player-name')
    if not n: continue
    sc = c.get('player-scoreds', ['0','0','0 / 0','0'])
    smap[(norm(n), cell(c, 'player-team'))] = {
        'pg': num(cell(c, 'player-match-playeds')),
        'mv': cell(c, 'player-grade-avg', 0, '0'),
        'fm': cell(c, 'player-fanta-grade-avg', 0, '0'),
        'gol': num(sc[0] if len(sc) > 0 else 0),
        'gs':  num(sc[1] if len(sc) > 1 else 0),
        'rr':  sc[2] if len(sc) > 2 else '0 / 0',
        'rp':  num(sc[3] if len(sc) > 3 else 0),
        'ass': num(cell(c, 'player-assists')),
        'amm': num(cell(c, 'player-yellows')),
        'esp': num(cell(c, 'player-reds')),
    }

players = []
for role, c in quotes:
    n = cell(c, 'player-name')
    if not n or role not in 'PDCA': continue
    t = cell(c, 'player-team')
    p = {'n': n, 't': t, 'r': role,
         'qi': num(cell(c, 'player-classic-initial-price')),
         'qa': num(cell(c, 'player-classic-current-price')),
         'fvm': num(cell(c, 'player-classic-fvm'))}
    if norm(n) in rig_names: p['rig'] = 1
    if norm(n) in cp_names:  p['cp'] = 1
    st = smap.get((norm(n), t))
    if st: p['st'] = st
    players.append(p)

if len(players) < 400:
    print(f'ERRORE: solo {len(players)} giocatori, struttura pagina cambiata?', file=sys.stderr)
    sys.exit(1)

out = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
       'season_stats': '2025-26', 'source': 'fantacalcio.it', 'players': players}
json.dump(out, open('quotes.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'ok: {len(players)} giocatori, {sum(1 for p in players if p.get("rig"))} rigoristi, {sum(1 for p in players if p.get("cp"))} CP, {sum(1 for p in players if "st" in p)} con statistiche')
