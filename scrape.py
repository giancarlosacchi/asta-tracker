# Listone: PDF fantacalcio-online (riserva: Gazzetta). Giocatori e quote.
# In piu': rigoristi/calci piazzati e statistiche da fantacalcio.it (solo come info nelle schede).
import re, json, sys, io, urllib.request, datetime, unicodedata

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

# ---------- 1) listone dal PDF (fantacalcio-online, con riserva Gazzetta) ----------
import pdfplumber
PDF_URL = 'https://www.fantacalcio-online.com/it/serie-a/2026-2027/quotazioni/pdf'
PDF_URL_RISERVA = 'https://www.gazzetta.it/static_images/infografiche/FREEMIUM/fantacampionato_listone_26-27.pdf'

SIG = {'ATA':'Atalanta','BOL':'Bologna','CAG':'Cagliari','COM':'Como','FIO':'Fiorentina','FRO':'Frosinone',
       'GEN':'Genoa','INT':'Inter','JUV':'Juventus','LAZ':'Lazio','LEC':'Lecce','MIL':'Milan','MON':'Monza',
       'NAP':'Napoli','PAR':'Parma','ROM':'Roma','SAS':'Sassuolo','TOR':'Torino','UDI':'Udinese','VEN':'Venezia',
       'VER':'Verona','PIS':'Pisa','CRE':'Cremonese','EMP':'Empoli','SPE':'Spezia','PAL':'Palermo','BAR':'Bari',
       'SAM':'Sampdoria','SAL':'Salernitana','PAD':'Padova'}
TEAMS = set(SIG.values())
ROLES_UP = {'PORTIERI':'P','DIFENSORI':'D','CENTROCAMPISTI':'C','ATTACCANTI':'A','ALLENATORI':'ALL'}
ROLES_OLD = {'Portieri':'P','Difensori':'D','Centrocampisti':'C','Attaccanti':'A','Allenatori':'ALL'}

def titlecase(n):
    def cap(tok):
        parts = re.split(r"([`'\u2019-])", tok.lower())
        return ''.join(p.capitalize() if p and p not in "`'\u2019-" else p for p in parts)
    return ' '.join(cap(t) for t in n.split())

def cluster_rows(words, tol=3.5):
    ws = sorted(words, key=lambda w: (w['top'], w['x0']))
    rows = []
    for w in ws:
        if rows and abs(w['top'] - rows[-1][0]['top']) <= tol: rows[-1].append(w)
        else: rows.append([w])
    return [sorted(r, key=lambda w: w['x0']) for r in rows]

def parse_pdf(pdf_bytes):
    """Riconosce sia il formato a 3 colonne (Q NOME SIGLA ETA') sia il vecchio a 2 (NOME Squadra COSTO)."""
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append((page.width, page.extract_words(x_tolerance=1.5)))
    # formato nuovo
    out, rej, role = [], 0, None
    for W, words in pages:
        cols = ([w for w in words if w['x0'] < W/3],
                [w for w in words if W/3 <= w['x0'] < 2*W/3],
                [w for w in words if w['x0'] >= 2*W/3])
        for col in cols:
            for ws in cluster_rows(col):
                text = ' '.join(w['text'] for w in ws).strip()
                if not text: continue
                hit = next((ROLES_UP[k] for k in ROLES_UP if text.upper().startswith(k)), None)
                if hit: role = hit; continue
                if re.match(r'^(Q |Listone|FANTACALCIO|ONLINE|SQUADRA|CALCIATORE|In$|verde |stampato|il \d|\d+ calciatori|\d{1,3}$|fantacalcio)', text, re.I): continue
                toks = text.split()
                if role in (None, 'ALL'): continue
                if len(toks) >= 4 and toks[0].isdigit() and re.fullmatch(r'[A-Z]{3}', toks[-2]) and re.fullmatch(r'\d{1,2}', toks[-1]):
                    team = SIG.get(toks[-2], toks[-2])
                    out.append({'n': titlecase(' '.join(toks[1:-2])), 't': team, 'r': role, 'q': int(toks[0])})
                elif len(toks) >= 2: rej += 1
    if len(out) >= 400: return out, rej, 'colonne triple'
    # formato vecchio
    out, rej, role = [], 0, None
    for W, words in pages:
        for col in ([w for w in words if w['x0'] < W/2], [w for w in words if w['x0'] >= W/2]):
            for ws in cluster_rows(col):
                text = ' '.join(w['text'] for w in ws).strip()
                if not text: continue
                hit = next((ROLES_OLD[h] for h in ROLES_OLD if text.startswith(h)), None)
                if hit: role = hit; continue
                if text.startswith(('Nome', 'IL LISTONE', 'fantacampionato', 'Costo')): continue
                toks = text.split()
                if role in (None, 'ALL'): continue
                if len(toks) >= 3 and re.fullmatch(r'\d{1,3}', toks[-1]) and toks[-2] in TEAMS:
                    out.append({'n': ' '.join(toks[:-2]), 't': toks[-2], 'r': role, 'q': int(toks[-1])})
                elif len(toks) >= 2: rej += 1
    return out, rej, 'colonne doppie'

gaz = []
for url in (PDF_URL, PDF_URL_RISERVA):
    try:
        pdf_bytes = get(url, binary=True)
        if len(pdf_bytes) < 50000 or not pdf_bytes.startswith(b'%PDF'):
            raise ValueError('non e\' un PDF')
        lst, rejected, fmt = parse_pdf(pdf_bytes)
        if len(lst) >= 450 and rejected <= 60:
            gaz = lst
            print(f'listone da {url} ({fmt}): {len(lst)} giocatori, {rejected} righe scartate', file=sys.stderr)
            break
        print(f'avviso: {url} sospetto ({len(lst)} giocatori, {rejected} scartate)', file=sys.stderr)
        for _r in lst[:5]: print('  esempio:', _r, file=sys.stderr)
    except Exception as e:
        print(f'avviso: {url} non leggibile: {e}', file=sys.stderr)

if len(gaz) < 450:
    print('ERRORE: nessuna fonte del listone leggibile', file=sys.stderr); sys.exit(1)

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
    for c in parse_rows(get('https://www.fantacalcio.it/statistiche-serie-a/2026-27')):
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


# ---------- 2c) prezzi medi delle aste reali + infortunati (fantacalcio-online) ----------
pm_sur, pm_full, inj_sur = {}, {}, {}
try:
    hp = get('https://www.fantacalcio-online.com/it/i-piu-comprati')
    for row in re.findall(r'<tr>[\s\S]*?</tr>', hp):
        tds = re.findall(r'<td[^>]*>([\s\S]*?)</td>', row)
        if len(tds) < 7: continue
        ruolo = clean(tds[0]); team = clean(tds[1]); nome = clean(tds[2])
        own = clean(tds[4]).replace('%', '').replace(',', '.')
        p500 = clean(tds[6]).replace(',', '.')
        msur = re.search(r'text-bold"[^>]*>([^<]+)', row)
        sur = clean(msur.group(1)) if msur else (nome.split(' ')[0] if nome else '')
        if not nome or not p500: continue
        try: pmv = round(float(p500))
        except Exception: continue
        try: ownv = round(float(own))
        except Exception: ownv = 0
        ent = (team, ruolo, pmv, ownv)
        pm_sur.setdefault((norm(sur), ruolo), []).append(ent)
        pm_full.setdefault((norm(nome), ruolo), []).append(ent)
    print(f'prezzi medi asta: {len(pm_full)} nomi', file=sys.stderr)
except Exception as e:
    print('avviso: prezzi medi non disponibili:', e, file=sys.stderr)

try:
    hi = get('https://www.fantacalcio-online.com/it/infortunati-serie-a')
    for row in re.findall(r'<tr>[\s\S]*?</tr>', hi):
        tds = re.findall(r'<td[^>]*>([\s\S]*?)</td>', row)
        if len(tds) < 4: continue
        team = clean(tds[0]); back = clean(tds[3])
        msur = re.search(r'<strong>([^<]+)</strong>', row)
        sur = clean(msur.group(1)) if msur else ''
        if not sur or not re.fullmatch(r'\d{2}/\d{2}/\d{4}', back): continue
        inj_sur.setdefault(norm(sur), []).append((team, back))
    print(f'infortunati: {len(inj_sur)} nomi', file=sys.stderr)
except Exception as e:
    print('avviso: infortunati non disponibili:', e, file=sys.stderr)

def _pick_team(cands, team):
    if not cands: return None
    if len(cands) == 1: return cands[0]
    t = [c for c in cands if norm(c[0]) == norm(team)]
    return (t or cands)[0]

def find_pm(gk, gteam, grole):
    hit = _pick_team(pm_full.get((gk, grole)), gteam) or _pick_team(pm_sur.get((gk, grole)), gteam)
    if not hit and len(gk) >= 5:
        for (nm, rr), v in pm_full.items():
            if rr == grole and (nm.startswith(gk) or gk.startswith(nm)):
                hit = _pick_team(v, gteam)
                if hit: break
    return hit

def find_inj(gk, gteam):
    c = inj_sur.get(gk)
    if not c and len(gk) >= 5:
        for kk, v in inj_sur.items():
            if kk.startswith(gk) or gk.startswith(kk): c = v; break
    if not c: return None
    hit = [x for x in c if norm(x[0]) == norm(gteam)]
    return hit[0][1] if hit else None

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
    hpm = find_pm(gk, g['t'], g['r'])
    if hpm:
        e['pm'] = hpm[2]
        if hpm[3]: e['own'] = hpm[3]
    binj = find_inj(gk, g['t'])
    if binj: e['inj'] = binj
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
       'season_stats': '2026-27', 'source': 'fantacalcio-online.com (listone 26-27)', 'players': players}
json.dump(out, open('quotes.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'ok: {len(players)} giocatori, {sum(1 for p in players if p.get("rig"))} rigoristi, '
      f'{sum(1 for p in players if p.get("cp"))} CP, {sum(1 for p in players if "st" in p)} con statistiche, '
      f'{sum(1 for p in players if p.get("fid"))} con foto, {sum(1 for p in players if p.get("pm"))} con prezzo asta, '
      f'{sum(1 for p in players if p.get("inj"))} infortunati')
