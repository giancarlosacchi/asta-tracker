# Listone: PDF Gazzetta Fantacampionato (fonte unica per giocatori e quote).
# In piu': rigoristi/calci piazzati e statistiche 2025-26 da fantacalcio.it (solo come info nelle schede).
import re, json, sys, io, urllib.request, datetime, unicodedata

PDF_URL = 'https://www.gazzetta.it/static_images/infografiche/FREEMIUM/fantacampionato_listone_26-27.pdf'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
      'Accept': '*/*', 'Referer': 'https://www.gazzetta.it/'}

def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    data = urllib.request.urlopen(req, timeout=90).read()
    return data if binary else data.decode('utf-8', 'replace')

import html as _html
def clean(s):
    return _html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip())

def norm(s):
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]', '', s.lower())

# ---------- 1) listone dal PDF Gazzetta ----------
import pdfplumber
ROLES = {'Portieri':'P', 'Difensori':'D', 'Centrocampisti':'C', 'Attaccanti':'A', 'Allenatori':'ALL'}
TEAMS = {'Atalanta','Bologna','Cagliari','Como','Fiorentina','Frosinone','Genoa','Inter','Juventus','Lazio',
         'Lecce','Milan','Monza','Napoli','Parma','Roma','Sassuolo','Torino','Udinese','Venezia',
         'Empoli','Verona','Cremonese','Pisa','Spezia','Palermo','Bari','Sampdoria','Salernitana','Padova'}

def cluster_rows(words, tol=3.5):
    ws = sorted(words, key=lambda w: (w['top'], w['x0']))
    rows = []
    for w in ws:
        if rows and abs(w['top'] - rows[-1][0]['top']) <= tol: rows[-1].append(w)
        else: rows.append([w])
    return [sorted(r, key=lambda w: w['x0']) for r in rows]

pdf_bytes = get(PDF_URL, binary=True)
if len(pdf_bytes) < 50000 or not pdf_bytes.startswith(b'%PDF'):
    print('ERRORE: il PDF Gazzetta non e\' scaricabile o non e\' un PDF', file=sys.stderr); sys.exit(1)

gaz = []; role = None; rejected = 0
with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    for page in pdf.pages:
        W = page.width
        words = page.extract_words(x_tolerance=1.5)
        for col in ([w for w in words if w['x0'] < W/2], [w for w in words if w['x0'] >= W/2]):
            for ws in cluster_rows(col):
                text = ' '.join(w['text'] for w in ws).strip()
                if not text: continue
                hit = next((ROLES[h] for h in ROLES if text.startswith(h)), None)
                if hit: role = hit; continue
                if text.startswith(('Nome', 'IL LISTONE', 'fantacampionato', 'Costo')): continue
                toks = text.split()
                if role in (None, 'ALL'): continue
                if len(toks) >= 3 and re.fullmatch(r'\d{1,3}', toks[-1]) and toks[-2] in TEAMS:
                    gaz.append({'n': ' '.join(toks[:-2]), 't': toks[-2], 'r': role, 'q': int(toks[-1])})
                elif len(toks) >= 2:
                    rejected += 1

if len(gaz) < 450 or rejected > 30:
    print(f'ERRORE: parse PDF sospetto ({len(gaz)} giocatori, {rejected} righe scartate)', file=sys.stderr); sys.exit(1)

# ---------- 2) rigoristi/CP e statistiche da fantacalcio.it (facoltativi) ----------
rig_names, cp_names = set(), set()
try:
    righ = get('https://www.fantacalcio.it/rigoristi-serie-a')
    cards = re.findall(r'class="card team-card"[\s\S]*?(?=class="card team-card"|<footer)', righ)
    for card in cards:
        lists = re.findall(r'<ol[^>]*pill-list[\s\S]*?</ol>', card)
        names = [[clean(a) for a in re.findall(r'<a[^>]*>([\s\S]*?)</a>', o)] for o in lists]
        def _keys(lst):
            out = set()
            for n in lst:
                out.add(norm(n))
                k2 = norm(' '.join(t for t in n.split() if not re.fullmatch(r'[A-Z][a-z]?\.(?:[A-Z]\.)?', t)) or n)
                out.add(k2)
            return out
        if len(names) > 0: rig_names.update(_keys(names[0]))
        if len(names) > 1: cp_names.update(_keys(names[1]))
except Exception as e:
    print('avviso: rigoristi non disponibili:', e, file=sys.stderr)

def parse_rows(html):
    out = []
    for block in re.findall(r'<tr[^>]*class="[^"]*player-row[\s\S]*?</tr>', html):
        cells = {}
        for cm in re.finditer(r'<t[dh][^>]*class="([^"]*)"[^>]*>([\s\S]*?)</t[dh]>', block):
            k = (cm.group(1) or '').split(' ')[0]
            cells.setdefault(k, []).append(clean(cm.group(2)))
        out.append(cells)
    return out

def cell(c, k, i=0, d=''):
    v = c.get(k, []); return v[i] if i < len(v) else d
def num(x):
    try: return int(x)
    except: return 0

def strip_init(name):
    keep = [t for t in name.split() if not re.fullmatch(r'[A-Z][a-z]?\.(?:[A-Z]\.)?', t)]
    return ' '.join(keep) if keep else name

srows = []
try:
    for c in parse_rows(get('https://www.fantacalcio.it/statistiche-serie-a/2025-26')):
        n = cell(c, 'player-name')
        if not n: continue
        sc = c.get('player-scoreds', ['0','0','0 / 0','0'])
        srows.append((n, cell(c, 'player-team'), {
            'pg': num(cell(c, 'player-match-playeds')), 'mv': cell(c, 'player-grade-avg', 0, '0'),
            'fm': cell(c, 'player-fanta-grade-avg', 0, '0'),
            'gol': num(sc[0] if len(sc) > 0 else 0), 'gs': num(sc[1] if len(sc) > 1 else 0),
            'rr': sc[2] if len(sc) > 2 else '0 / 0', 'rp': num(sc[3] if len(sc) > 3 else 0),
            'ass': num(cell(c, 'player-assists')), 'amm': num(cell(c, 'player-yellows')),
            'esp': num(cell(c, 'player-reds')),
        }))
except Exception as e:
    print('avviso: statistiche non disponibili:', e, file=sys.stderr)

smap_full, smap_strip = {}, {}
for n, tm, st in srows:
    smap_full.setdefault(norm(n), []).append((tm, st))
    k2 = norm(strip_init(n))
    if k2 != norm(n): smap_strip.setdefault(k2, []).append((tm, st))

def find_stat(gk, gteam):
    gt = norm(gteam)
    for m in (smap_full, smap_strip):
        c = m.get(gk)
        if c:
            if len(c) == 1: return c[0][1]
            hit = [x for x in c if norm(x[0]) and (gt.startswith(norm(x[0])[:3]) or norm(x[0]).startswith(gt[:3]))]
            return (hit or c)[0][1]
    if len(gk) >= 5:
        for k, c in smap_full.items():
            if k.startswith(gk) or gk.startswith(k): return c[0][1]
    return None

# ---------- 2b) id delle card (foto) dalle rose di fantacalcio.it ----------
fmap = {}
try:
    idx = get('https://www.fantacalcio.it/serie-a/squadre')
    slugs = sorted(set(re.findall(r'/serie-a/squadre/([a-z0-9-]+)"', idx)))
    for ts in slugs:
        try:
            th = get('https://www.fantacalcio.it/serie-a/squadre/' + ts)
        except Exception:
            continue
        for m in re.finditer(r'/serie-a/squadre/' + re.escape(ts) + r'/([a-z0-9-]+)/(\d+)', th):
            fmap.setdefault(norm(m.group(1)), set()).add((ts, int(m.group(2))))
    print(f'foto: {len(slugs)} squadre, {len(fmap)} nomi indicizzati', file=sys.stderr)
except Exception as e:
    print('avviso: foto non disponibili:', e, file=sys.stderr)

def find_fid(gk, gteam):
    gt = norm(gteam)
    c = fmap.get(gk)
    if not c and len(gk) >= 5:
        for k, v in fmap.items():
            if k.startswith(gk) or gk.startswith(k): c = v; break
    if not c: return None
    lst = list(c)
    if len(lst) > 1:
        hit = [x for x in lst if gt and (gt in norm(x[0]) or norm(x[0]) in gt)]
        if hit: lst = hit
    return lst[0][1]

players = []
for g in gaz:
    e = {'n': g['n'], 't': g['t'], 'r': g['r'], 'qi': g['q'], 'qa': g['q']}
    gk = norm(g['n'])
    if gk in rig_names: e['rig'] = 1
    if gk in cp_names: e['cp'] = 1
    st = find_stat(gk, g['t'])
    if st: e['st'] = st
    fid = find_fid(gk, g['t'])
    if fid: e['fid'] = fid
    players.append(e)

# ---------- 3) storico quote: aggiungo il punto di oggi a quello gia' salvato ----------
today = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // 86400)
old_h = {}
try:
    prev = json.load(open('quotes.json', encoding='utf-8'))
    for p in prev.get('players', []):
        if p.get('h'): old_h[(norm(p['n']), p['t'], p['r'])] = p['h']
except Exception:
    pass
for p in players:
    h = old_h.get((norm(p['n']), p['t'], p['r']), [])
    if not h or h[-1][0] != today:
        h = h + [[today, p['qa']]]
    else:
        h[-1][1] = p['qa']
    p['h'] = [pt for pt in h if today - pt[0] <= 21][-15:]   # max 3 settimane / 15 punti

out = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
       'season_stats': '2025-26', 'source': 'gazzetta fantacampionato (pdf 26-27)', 'players': players}
json.dump(out, open('quotes.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'ok: {len(players)} giocatori Gazzetta, {sum(1 for p in players if p.get("rig"))} rigoristi, '
      f'{sum(1 for p in players if p.get("cp"))} CP, {sum(1 for p in players if "st" in p)} con statistiche, '
      f'{sum(1 for p in players if p.get("fid"))} con foto')
