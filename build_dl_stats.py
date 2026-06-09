import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import time
import urllib.request

CACHE_DIR  = Path('.cache')
CACHE_TTL  = 3600

API_BASE    = "https://api.deadlock-api.com/v1/players"
ASSETS_BASE = "https://api.deadlock-api.com/v1/assets"
ACCOUNT_ID  = "105130498"

_last_request_time = 0.0
_today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

# ── HTTP / cache ──────────────────────────────────────────────────────────────
def fetch(url: str):
    CACHE_DIR.mkdir(exist_ok=True)
    key  = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / (key + '.json')

    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_TTL:
            return json.loads(path.read_text(encoding='utf-8'))

    global _last_request_time
    gap = 0.75 - (time.monotonic() - _last_request_time)
    if gap > 0:
        time.sleep(gap)
    _last_request_time = time.monotonic()

    req = urllib.request.Request(url, headers={"User-Agent": "thehushline"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()

    path.write_bytes(raw)
    return json.loads(raw)

# ── Core player data ──────────────────────────────────────────────────────────
print("Fetching match history…")
matches    = fetch(f'{API_BASE}/{ACCOUNT_ID}/match-history')
print(f"  {len(matches)} matches")

print("Fetching MMR history…")
mmr_raw    = fetch(f'{API_BASE}/{ACCOUNT_ID}/mmr-history')

print("Fetching hero stats…")
hero_stats = fetch(f'{API_BASE}/{ACCOUNT_ID}/hero-stats')
print(f"  {len(hero_stats)} heroes tracked")

# ── Asset lookups ─────────────────────────────────────────────────────────────
print("Fetching hero assets…")
try:
    _heroes_raw = fetch(f'{ASSETS_BASE}/heroes?language=english')
    selectable  = [h for h in _heroes_raw if h.get('player_selectable')]
    HERO_NAMES  = {h['id']: h['name'] for h in selectable}
    HERO_IMAGES = {
        h['id']: {
            'webp': h['images'].get('icon_image_small_webp', ''),
            'png':  h['images'].get('icon_image_small', ''),
        }
        for h in selectable
    }
    print(f"  {len(HERO_NAMES)} heroes")
except Exception as e:
    print(f"  Hero assets failed: {e}")
    HERO_NAMES  = {}
    HERO_IMAGES = {}

print("Fetching rank assets…")
try:
    _ranks_raw  = fetch(f'{ASSETS_BASE}/ranks')
    RANK_IMAGES = {r['tier']: r['images'] for r in _ranks_raw}
except Exception as e:
    print(f"  Rank assets failed: {e}")
    RANK_IMAGES = {}

# ── Rank helpers ──────────────────────────────────────────────────────────────
RANK_NAMES = {
    1: 'Seeker', 2: 'Alchemist', 3: 'Emissary', 4: 'Archon',
    5: 'Oracle', 6: 'Phantom',   7: 'Ascendant', 8: 'Eternus',
}
_RANK_NAME_TO_API_TIER = {
    'Obscurus': 0, 'Initiate': 1, 'Seeker': 2, 'Alchemist': 3, 'Arcanist': 4,
    'Ritualist': 5, 'Emissary': 6, 'Archon': 7, 'Oracle': 8,
    'Phantom': 9, 'Ascendant': 10, 'Eternus': 11,
}

def _rank_badge_url(rank_int, size='large'):
    if not rank_int:
        return '', ''
    tier  = rank_int // 10
    sub   = rank_int % 10
    name  = RANK_NAMES.get(tier, '')
    api_t = _RANK_NAME_TO_API_TIER.get(name)
    if api_t is None:
        return '', ''
    imgs  = RANK_IMAGES.get(api_t, {})
    k_w   = f'{size}_subrank{sub}_webp' if sub else f'{size}_webp'
    k_p   = f'{size}_subrank{sub}'      if sub else size
    return imgs.get(k_w, imgs.get(f'{size}_webp', '')), imgs.get(k_p, imgs.get(size, ''))

def rank_badge_html(rank_int, px=56):
    webp, png = _rank_badge_url(rank_int, 'large')
    if not webp and not png:
        return ''
    tier = rank_int // 10
    sub  = rank_int % 10
    name = RANK_NAMES.get(tier, '')
    alt  = f'{name} {sub}' if sub else name
    return (f'<picture class="rank-badge">'
            f'<source srcset="{webp}" type="image/webp">'
            f'<img src="{png}" alt="{alt}" width="{px}" height="{px}">'
            f'</picture>')

def hero_icon_html(hero_id, px=24, lazy=True):
    imgs = HERO_IMAGES.get(hero_id, {})
    webp = imgs.get('webp', '')
    png  = imgs.get('png',  '')
    if not webp and not png:
        return ''
    lz = ' loading="lazy"' if lazy else ''
    return (f'<picture class="hero-icon">'
            f'<source srcset="{webp}" type="image/webp">'
            f'<img src="{png}" alt="" aria-hidden="true" width="{px}" height="{px}"{lz}>'
            f'</picture>')

def rank_label(r):
    if not r:
        return 'Unranked'
    tier, sub = r // 10, r % 10
    name = RANK_NAMES.get(tier, f'Tier {tier}')
    return f'{name} {sub}' if sub else name

def format_duration(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m:02d}m"

def fmt_big(n):
    return f"{int(n):,}"

# ── MMR / rank history ────────────────────────────────────────────────────────
mmr_sorted       = sorted(mmr_raw, key=lambda x: x.get('start_time', 0))
current_rank_int = mmr_sorted[-1]['rank'] if mmr_sorted else 0
rank             = rank_label(current_rank_int)

def ts_to_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b '%y")

start_date = ts_to_str(mmr_sorted[0]['start_time'])  if mmr_sorted else '?'
end_date   = ts_to_str(mmr_sorted[-1]['start_time']) if mmr_sorted else '?'

# ── Match-history aggregates ──────────────────────────────────────────────────
n_matches       = len(matches)
wins            = sum(1 for m in matches if m.get('match_result'))
losses          = n_matches - wins
wr              = wins / n_matches * 100 if n_matches else 0

total_kills     = sum(m.get('player_kills', 0)    for m in matches)
total_deaths    = sum(m.get('player_deaths', 0)   for m in matches)
total_assists   = sum(m.get('player_assists', 0)  for m in matches)
total_net_worth = sum(m.get('net_worth', 0)       for m in matches)
total_cs        = sum(m.get('last_hits', 0)       for m in matches)
total_denies_mh = sum(m.get('denies', 0)          for m in matches)
total_duration  = sum(m.get('match_duration_s', 0)for m in matches)

avg_kills     = total_kills     / n_matches if n_matches else 0
avg_deaths    = total_deaths    / n_matches if n_matches else 0
avg_assists   = total_assists   / n_matches if n_matches else 0
avg_net_worth = total_net_worth / n_matches if n_matches else 0
avg_last_hits = total_cs        / n_matches if n_matches else 0
avg_denies    = total_denies_mh / n_matches if n_matches else 0
kda           = (total_kills + total_assists) / max(1, total_deaths)

play_time          = format_duration(total_duration)
avg_match_duration = format_duration(total_duration / n_matches if n_matches else 0)

# Win / loss streaks
best_win_streak = cur_win = 0
best_loss_streak = cur_loss = 0
for m in matches:
    if m.get('match_result'):
        cur_win += 1;  best_win_streak = max(best_win_streak, cur_win); cur_loss = 0
    else:
        cur_loss += 1; best_loss_streak = max(best_loss_streak, cur_loss); cur_win = 0

cur_streak_n, cur_streak_type = 0, None
for m in matches:
    r = bool(m.get('match_result'))
    if cur_streak_type is None:
        cur_streak_type = r;  cur_streak_n = 1
    elif r == cur_streak_type:
        cur_streak_n += 1
    else:
        break
current_streak_label = (f"{cur_streak_n}W" if cur_streak_type else f"{cur_streak_n}L") + " streak"

# Best single-match stats
best_kill_match   = max(matches, key=lambda m: m.get('player_kills', 0),   default={})
best_assist_match = max(matches, key=lambda m: m.get('player_assists', 0), default={})
best_nw_match     = max(matches, key=lambda m: m.get('net_worth', 0),      default={})

best_kills_n    = best_kill_match.get('player_kills', 0)
best_kills_hero = HERO_NAMES.get(best_kill_match.get('hero_id', 0), '?')
best_assists_n    = best_assist_match.get('player_assists', 0)
best_assists_hero = HERO_NAMES.get(best_assist_match.get('hero_id', 0), '?')
best_nw_n    = best_nw_match.get('net_worth', 0)
best_nw_hero = HERO_NAMES.get(best_nw_match.get('hero_id', 0), '?')

# ── Hero-stats aggregates (per-hero rates from endpoint) ──────────────────────
def _wt_avg(field):
    """Weighted average across heroes, weight = matches_played."""
    num   = sum(h.get(field, 0) * h.get('matches_played', 0) for h in hero_stats)
    denom = sum(h.get('matches_played', 0) for h in hero_stats)
    return num / denom if denom else 0

avg_dpm          = _wt_avg('damage_per_min')
avg_dtpm         = _wt_avg('damage_taken_per_min')
avg_mitigated_pm = _wt_avg('damage_mitigated_per_min')
avg_obj_dpm      = _wt_avg('obj_damage_per_min')
avg_accuracy_pct = _wt_avg('accuracy')       * 100
avg_crit_pct     = _wt_avg('crit_shot_rate') * 100
avg_spm_hs       = _wt_avg('networth_per_min')
avg_lhpm         = _wt_avg('last_hits_per_min')

total_player_damage       = sum(h.get('total_player_damage', 0)       for h in hero_stats)
total_player_damage_taken = sum(h.get('total_player_damage_taken', 0) for h in hero_stats)
total_boss_damage         = sum(h.get('total_boss_damage', 0)         for h in hero_stats)
total_creep_damage        = sum(h.get('total_creep_damage', 0)        for h in hero_stats)
total_neutral_damage      = sum(h.get('total_neutral_damage', 0)      for h in hero_stats)

# Best damage / accuracy heroes (from hero-stats totals)
best_dmg_stat  = max(hero_stats, key=lambda h: h.get('total_player_damage', 0), default={})
best_dmg_hid   = best_dmg_stat.get('hero_id', 0)
best_dmg_hero  = HERO_NAMES.get(best_dmg_hid, '?')
best_dmg_total = best_dmg_stat.get('total_player_damage', 0)
best_dmg_dpm   = best_dmg_stat.get('damage_per_min', 0)

qualified      = [h for h in hero_stats if h.get('matches_played', 0) >= 3]
best_acc_stat  = max(qualified, key=lambda h: h.get('accuracy', 0), default={})
best_acc_hero  = HERO_NAMES.get(best_acc_stat.get('hero_id', 0), '?')
best_acc_pct   = best_acc_stat.get('accuracy', 0) * 100

# Main hero (most played)
hs_sorted       = sorted(hero_stats, key=lambda x: x.get('matches_played', 0), reverse=True)
main_hero_data  = hs_sorted[0] if hs_sorted else {}
main_hero_id    = main_hero_data.get('hero_id', 0)
main_hero       = HERO_NAMES.get(main_hero_id, '?')
main_hero_games = main_hero_data.get('matches_played', 0)
_mh_wins        = main_hero_data.get('wins', 0)
main_hero_wr    = _mh_wins / main_hero_games * 100 if main_hero_games else 0

# ── Metadata loop — heatmap + hero composition ────────────────────────────────
HEATMAP_MATCHES       = 30
player_kill_positions  = []
player_death_positions = []

ally_hero_counter  = Counter()
ally_hero_wins     = Counter()
enemy_hero_counter = Counter()
enemy_hero_wins    = Counter()

print(f"Fetching metadata for up to {HEATMAP_MATCHES} matches…")
for i, m in enumerate(matches[:HEATMAP_MATCHES]):
    mid = m['match_id']
    try:
        meta    = fetch(f'https://api.deadlock-api.com/v1/matches/{mid}/metadata')
        players = meta['match_info']['players']

        my_p = next((p for p in players if p.get('account_id') == int(ACCOUNT_ID)), None)
        if my_p is None:
            continue

        my_team   = my_p.get('team')
        my_slot   = my_p.get('player_slot')
        my_result = bool(m.get('match_result'))

        # Ally / enemy hero composition
        for p in players:
            if p.get('account_id') == int(ACCOUNT_ID):
                continue
            hid = p.get('hero_id')
            if not hid:
                continue
            if p.get('team') == my_team:
                ally_hero_counter[hid] += 1
                if my_result:
                    ally_hero_wins[hid] += 1
            else:
                enemy_hero_counter[hid] += 1
                if my_result:
                    enemy_hero_wins[hid] += 1

        # Kill / death heatmap positions
        for p in players:
            for death in p.get('death_details', []):
                pos = death.get('death_pos', {})
                if p.get('player_slot') == my_slot:
                    x, y = pos.get('x'), pos.get('y')
                    if x is not None and y is not None:
                        player_death_positions.append((x, y))
                elif death.get('killer_player_slot') == my_slot:
                    kpos = death.get('killer_pos', {})
                    x, y = kpos.get('x'), kpos.get('y')
                    if x is not None and y is not None:
                        player_kill_positions.append((x, y))

    except Exception as e:
        print(f"  [{i+1}] match {mid} failed: {e}")

print(f"  kills: {len(player_kill_positions)}, deaths: {len(player_death_positions)}")
print(f"  ally heroes tracked: {len(ally_hero_counter)}, enemy heroes: {len(enemy_hero_counter)}")

# ── Render helpers ────────────────────────────────────────────────────────────
def wr_bar_html(pct):
    pct_i = round(pct)
    cls   = 'good' if pct >= 55 else ('bad' if pct < 45 else '')
    return (f'<span class="wr-bar">'
            f'<span class="wr-bar-track" aria-hidden="true">'
            f'<span class="wr-bar-fill {cls}" style="width:{pct:.0f}%"></span>'
            f'</span>{pct_i}%</span>')

def stat_card(value, label, sub=None):
    s = (f'<div class="stat-card" role="listitem">'
         f'<span class="stat-value">{value}</span>'
         f'<span class="stat-label">{label}</span>')
    if sub:
        s += f'<span class="stat-sub">{sub}</span>'
    s += '</div>'
    return s

# ── Hero roster table ─────────────────────────────────────────────────────────
def hero_table_rows(stats, top_n=20):
    rows = []
    for h in sorted(stats, key=lambda x: x.get('matches_played', 0), reverse=True)[:top_n]:
        hid   = h.get('hero_id', 0)
        name  = HERO_NAMES.get(hid, f'Hero {hid}')
        games = h.get('matches_played', 0)
        w     = h.get('wins', 0)
        wr    = w / games * 100 if games else 0
        k     = h.get('kills', 0)   / games if games else 0
        d     = h.get('deaths', 0)  / games if games else 0
        a     = h.get('assists', 0) / games if games else 0
        kda   = (k + a) / max(d, 1)
        dpm   = h.get('damage_per_min', 0)
        spm   = h.get('networth_per_min', 0)
        dn    = h.get('denies_per_match', 0)
        t     = format_duration(h.get('time_played', 0))
        rows.append(
            f'    <tr>'
            f'<th scope="row">{hero_icon_html(hid)}{name}</th>'
            f'<td>{games}</td>'
            f'<td>{wr_bar_html(wr)}</td>'
            f'<td class="kda-cell">{k:.1f}/{d:.1f}/{a:.1f}</td>'
            f'<td>{kda:.2f}</td>'
            f'<td>{dpm:,.0f}</td>'
            f'<td>{spm:,.0f}</td>'
            f'<td>{dn:.1f}</td>'
            f'<td>{t}</td>'
            f'</tr>'
        )
    return '\n'.join(rows)

# ── Combat profile table ──────────────────────────────────────────────────────
def combat_table_rows(stats, top_n=20):
    rows = []
    for h in sorted(stats, key=lambda x: x.get('matches_played', 0), reverse=True)[:top_n]:
        hid  = h.get('hero_id', 0)
        name = HERO_NAMES.get(hid, f'Hero {hid}')
        gms  = h.get('matches_played', 0)
        dpm  = h.get('damage_per_min', 0)
        dtpm = h.get('damage_taken_per_min', 0)
        mit  = h.get('damage_mitigated_per_min', 0)
        obj  = h.get('obj_damage_per_min', 0)
        acc  = h.get('accuracy', 0) * 100
        crit = h.get('crit_shot_rate', 0) * 100
        rows.append(
            f'    <tr>'
            f'<th scope="row">{hero_icon_html(hid)}{name}</th>'
            f'<td>{gms}</td>'
            f'<td>{dpm:,.0f}</td>'
            f'<td>{dtpm:,.0f}</td>'
            f'<td>{mit:,.0f}</td>'
            f'<td>{obj:,.0f}</td>'
            f'<td>{acc:.1f}%</td>'
            f'<td>{crit:.1f}%</td>'
            f'</tr>'
        )
    return '\n'.join(rows)

# ── Hero composition tables (allies / enemies) ────────────────────────────────
def hero_comp_rows(counter, wins_counter, top_n=10):
    rows = []
    for hid, count in counter.most_common(top_n):
        name = HERO_NAMES.get(hid, f'Hero {hid}')
        w    = wins_counter.get(hid, 0)
        wr   = w / count * 100 if count else 0
        rows.append(
            f'    <tr>'
            f'<td>{hero_icon_html(hid)}{name}</td>'
            f'<td>{count}</td>'
            f'<td>{wr_bar_html(wr)}</td>'
            f'</tr>'
        )
    return '\n'.join(rows)

# ── Recent matches table ──────────────────────────────────────────────────────
def recent_match_rows(matches, top_n=15):
    rows = []
    for m in matches[:top_n]:
        result  = 'Win' if m.get('match_result') else 'Loss'
        hid     = m.get('hero_id', 0)
        hero    = HERO_NAMES.get(hid, f'Hero {hid}')
        level   = m.get('hero_level', '?')
        k, d, a = m.get('player_kills', 0), m.get('player_deaths', 0), m.get('player_assists', 0)
        kda     = (k + a) / max(d, 1)
        nw      = m.get('net_worth', 0)
        cs      = m.get('last_hits', 0)
        dn      = m.get('denies', 0)
        dur     = f"{m.get('match_duration_s', 0) // 60}m"
        dt      = datetime.fromtimestamp(m.get('start_time', 0), tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append(
            f'    <tr>'
            f'<td class="{result.lower()}">{result}</td>'
            f'<td>{hero_icon_html(hid)}{hero}</td>'
            f'<td>{level}</td>'
            f'<td class="kda-cell">{k}/{d}/{a}</td>'
            f'<td>{kda:.2f}</td>'
            f'<td>{nw:,}</td>'
            f'<td>{cs}</td>'
            f'<td>{dn}</td>'
            f'<td>{dur}</td>'
            f'<td><time datetime="{dt}">{dt}</time></td>'
            f'</tr>'
        )
    return '\n'.join(rows)

# ── Rank progression SVG ──────────────────────────────────────────────────────
def rank_chart_svg(mmr_sorted):
    if len(mmr_sorted) < 2:
        return '<p>Not enough rank data.</p>'

    PL, PR, PT, PB = 80, 20, 18, 38
    W, H = 880, 220
    cw, ch = W - PL - PR, H - PT - PB

    r_vals = [e['rank'] for e in mmr_sorted]
    t_vals = [e['start_time'] for e in mmr_sorted]
    lo, hi = min(r_vals) - 2, max(r_vals) + 2

    def xp(i): return PL + (i / (len(r_vals) - 1)) * cw
    def yp(r): return PT + ch - (r - lo) / (hi - lo) * ch

    step_pts = []
    for i, rv in enumerate(r_vals):
        x, y = xp(i), yp(rv)
        if i == 0:
            step_pts.append((x, y))
        else:
            step_pts.append((x, step_pts[-1][1]))
            step_pts.append((x, y))
    pts_str = ' '.join(f'{x:.1f},{y:.1f}' for x, y in step_pts)

    grids = ''
    seen_tiers = set()
    ICON_SZ = 14
    for rv in r_vals:
        tier = rv // 10
        if tier in seen_tiers:
            continue
        seen_tiers.add(tier)
        gy  = yp(tier * 10)
        lbl = RANK_NAMES.get(tier, f'Tier {tier}')
        _, badge_png = _rank_badge_url(tier * 10 + 1, 'small')
        badge_img = (f'<image href="{badge_png}" x="{PL-ICON_SZ-32}" y="{gy-ICON_SZ//2:.1f}"'
                     f' width="{ICON_SZ}" height="{ICON_SZ}" aria-hidden="true"/>'
                     if badge_png else '')
        grids += (badge_img
                  + f'<line class="chart-grid" x1="{PL}" y1="{gy:.1f}" x2="{PL+cw}" y2="{gy:.1f}"/>'
                  f'<text class="chart-label" x="{PL-8}" y="{gy+4:.1f}" text-anchor="end"'
                  f' font-size="11" font-family="sans-serif">{lbl}</text>')

    n = len(r_vals)
    xlbls = ''
    for idx in sorted({0, n//4, n//2, 3*n//4, n-1}):
        idx = min(idx, n-1)
        lbl = datetime.fromtimestamp(t_vals[idx], tz=timezone.utc).strftime("%b '%y")
        xlbls += (f'<text class="chart-label" x="{xp(idx):.1f}" y="{PT+ch+24}"'
                  f' text-anchor="middle" font-size="11" font-family="sans-serif">{lbl}</text>')

    ex, ey = xp(n-1), yp(r_vals[-1])
    end_lbl = rank_label(r_vals[-1])
    END_SZ  = 24
    _, end_badge_png = _rank_badge_url(r_vals[-1], 'large')
    end_badge = (f'<image href="{end_badge_png}" x="{ex-END_SZ//2:.1f}" y="{ey-END_SZ-16:.1f}"'
                 f' width="{END_SZ}" height="{END_SZ}" aria-hidden="true"/>'
                 if end_badge_png else '')

    return (f'<svg role="img" aria-labelledby="chart-title chart-desc"'
            f' viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" width="100%">'
            f'<title id="chart-title">Rank Progression Chart</title>'
            f'<desc id="chart-desc">Step chart of rank history from {start_date} to {end_date}.'
            f' Each step represents a rank change.</desc>'
            f'{grids}{xlbls}'
            f'<polyline class="chart-line" points="{pts_str}" fill="none" stroke-width="2"'
            f' stroke-linejoin="miter" stroke-linecap="square"/>'
            f'<circle class="chart-dot" cx="{ex:.1f}" cy="{ey:.1f}" r="4"/>'
            f'{end_badge}'
            f'<text class="chart-label chart-end-label" x="{ex:.1f}" y="{ey-9:.1f}" text-anchor="middle"'
            f' font-size="11" font-weight="bold" font-family="sans-serif">{end_lbl}</text>'
            f'</svg>')

# ── Map SVG ───────────────────────────────────────────────────────────────────
MAP_WORLD = (-10000, -10000, 10000, 10000)

def world_to_svg(wx, wy, svg_w=430, svg_h=430):
    xmin, ymin, xmax, ymax = MAP_WORLD
    x = (wx - xmin) / (xmax - xmin) * svg_w
    y = svg_h - (wy - ymin) / (ymax - ymin) * svg_h
    return x, y

def map_dots(positions, css_class, r=4, opacity=0.18):
    parts = []
    for wx, wy in positions:
        x, y = world_to_svg(wx, wy)
        parts.append(f'<circle class="{css_class}" cx="{x:.1f}" cy="{y:.1f}" r="{r}" opacity="{opacity}"/>')
    return ''.join(parts)

def map_svg():
    n_kill  = len(player_kill_positions)
    n_death = len(player_death_positions)
    kill_d  = map_dots(player_kill_positions,  'map-kill',  r=4, opacity=0.15)
    death_d = map_dots(player_death_positions, 'map-death', r=4, opacity=0.15)
    desc = (f'{n_kill} kill positions and {n_death} death positions '
            f'from {min(HEATMAP_MATCHES, n_matches)} matches.')
    return (
        f'<svg role="img" aria-labelledby="map-title map-desc" '
        f'viewBox="0 0 432 490" xmlns="http://www.w3.org/2000/svg" width="432">'
        f'<title id="map-title">Deadlock Map Activity Heatmap</title>'
        f'<desc id="map-desc">{desc}</desc>'
        f'<rect class="map-border" x="1" y="1" width="430" height="430" fill="none" stroke-width="1.5"/>'
        f'{kill_d}{death_d}'
        f'<text class="map-legend-kill"  x="8" y="448" font-size="11" font-family="sans-serif">&#x25CF; Kills</text>'
        f'<text class="map-legend-death" x="8" y="463" font-size="11" font-family="sans-serif">&#x25CF; Deaths</text>'
        f'</svg>'
    )

# ── Conditional sections ──────────────────────────────────────────────────────
_have_enemy_comp = bool(enemy_hero_counter)
_have_ally_comp  = bool(ally_hero_counter)

nav_comp = ''
if _have_enemy_comp:
    nav_comp += '    <li><a href="#enemies">Enemy Hero Tendencies</a></li>\n'
if _have_ally_comp:
    nav_comp += '    <li><a href="#allies">Ally Hero Tendencies</a></li>\n'

def enemy_section():
    if not _have_enemy_comp:
        return ''
    n = min(HEATMAP_MATCHES, n_matches)
    return f'''
<section id="enemies" aria-labelledby="h-enemies">
<h2 id="h-enemies">Enemy Hero Tendencies</h2>
<p>Heroes most frequently on the opposing team in the last {n} tracked matches, with your win rate against lineups featuring that hero.</p>
<table>
  <caption>Enemy hero frequency — {n} matches</caption>
  <thead>
    <tr>
      <th scope="col">Hero</th>
      <th scope="col">Encounters</th>
      <th scope="col">My Win Rate</th>
    </tr>
  </thead>
  <tbody>
{hero_comp_rows(enemy_hero_counter, enemy_hero_wins)}
  </tbody>
</table>
</section>
'''

def ally_section():
    if not _have_ally_comp:
        return ''
    n = min(HEATMAP_MATCHES, n_matches)
    return f'''
<section id="allies" aria-labelledby="h-allies">
<h2 id="h-allies">Ally Hero Tendencies</h2>
<p>Heroes most frequently on your team in the last {n} tracked matches, with win rate when they are on your side.</p>
<table>
  <caption>Ally hero frequency — {n} matches</caption>
  <thead>
    <tr>
      <th scope="col">Hero</th>
      <th scope="col">Matches</th>
      <th scope="col">Win Rate</th>
    </tr>
  </thead>
  <tbody>
{hero_comp_rows(ally_hero_counter, ally_hero_wins)}
  </tbody>
</table>
</section>
'''

# ── Pre-build chunks ──────────────────────────────────────────────────────────
_chart_svg     = rank_chart_svg(mmr_sorted)
_hero_rows     = hero_table_rows(hero_stats)
_combat_rows   = combat_table_rows(hero_stats)
_map_svg       = map_svg()
_recent_rows   = recent_match_rows(matches)
_enemy_sec     = enemy_section()
_ally_sec      = ally_section()

_overview_cards = '\n'.join([
    stat_card(str(n_matches),            'Matches Played'),
    stat_card(f'{wr:.1f}%',             'Win Rate',          f'{wins}W \u2013 {losses}L'),
    stat_card(f'{kda:.2f}',             'KDA Ratio',         f'{avg_kills:.1f}\u2009/\u2009{avg_deaths:.1f}\u2009/\u2009{avg_assists:.1f}'),
    stat_card(play_time,                 'Time Played'),
    stat_card(f'{avg_dpm:,.0f}',        'Avg DPM'),
    stat_card(f'{avg_spm_hs:,.0f}',     'Avg Souls\u2009/\u2009min'),
    stat_card(f'{avg_accuracy_pct:.1f}%','Shot Accuracy'),
    stat_card(f'{avg_denies:.1f}',      'Avg Denies'),
    stat_card(current_streak_label,      'Current Streak'),
])

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Lexington \u2014 Deadlock Statistics</title>
    <link rel="stylesheet" href="dl-stats-style.css">
</head>
<body>

<a href="#main">Skip to main content</a>

<header>
  <h1>Lexington \u2014 Deadlock Statistics</h1>
  <p>
    {rank_badge_html(current_rank_int, px=52)}<strong>{rank}</strong>\u2002\u00b7\u2002{n_matches} matches\u2002\u00b7\u2002{wins}W\u2009\u2013\u2009{losses}L\u2002\u00b7\u2002{wr:.1f}% win rate\u2002\u00b7\u2002{play_time} played\u2002\u00b7\u2002Steam\u00a0ID:\u00a0{ACCOUNT_ID}
  </p>
</header>

<nav aria-label="Page sections">
  <h2>Contents</h2>
  <ol>
    <li><a href="#overview">Overview</a></li>
    <li><a href="#rank">Rank Progression</a></li>
    <li><a href="#highlights">Highlights</a></li>
    <li><a href="#heroes">Hero Roster</a></li>
    <li><a href="#combat">Combat Profile</a></li>
    <li><a href="#map">Map Activity</a></li>
{nav_comp}    <li><a href="#matches">Recent Matches</a></li>
  </ol>
</nav>

<main id="main">

<!-- ── Overview ────────────────────────────────────────────────────────── -->
<section id="overview" aria-labelledby="h-overview">
<h2 id="h-overview">Overview</h2>
<div class="stat-grid" role="list">
{_overview_cards}
</div>
<dl class="overview-dl">
  <dt>Record</dt>                    <dd>{wins} wins \u2014 {losses} losses</dd>
  <dt>Avg Kills</dt>                 <dd>{avg_kills:.1f}</dd>
  <dt>Avg Deaths</dt>                <dd>{avg_deaths:.1f}</dd>
  <dt>Avg Assists</dt>               <dd>{avg_assists:.1f}</dd>
  <dt>Avg Net Worth</dt>             <dd>{avg_net_worth:,.0f}</dd>
  <dt>Avg <abbr title="Last Hits">CS</abbr></dt>
                                     <dd>{avg_last_hits:.1f}</dd>
  <dt>Avg Match Duration</dt>        <dd>{avg_match_duration}</dd>
  <dt>Total Player Damage</dt>       <dd>{fmt_big(total_player_damage)}</dd>
  <dt>Total Damage Taken</dt>        <dd>{fmt_big(total_player_damage_taken)}</dd>
  <dt>Avg Crit Rate</dt>             <dd>{avg_crit_pct:.1f}%</dd>
  <dt>Avg Obj Damage/Min</dt>        <dd>{avg_obj_dpm:,.0f}</dd>
  <dt>Avg Damage Mitigated/Min</dt>  <dd>{avg_mitigated_pm:,.0f}</dd>
  <dt>Longest Win Streak</dt>        <dd>{best_win_streak} games</dd>
  <dt>Longest Loss Streak</dt>       <dd>{best_loss_streak} games</dd>
</dl>
</section>

<!-- ── Rank Progression ─────────────────────────────────────────────────── -->
<section id="rank" aria-labelledby="h-rank">
<h2 id="h-rank">Rank Progression</h2>
<p>{n_matches} matches tracked from {start_date} to {end_date}.</p>
<figure>
  {_chart_svg}
  <figcaption>Rank history: {start_date} \u2192 {end_date}, {n_matches} matches.</figcaption>
</figure>
</section>

<!-- ── Highlights ───────────────────────────────────────────────────────── -->
<section id="highlights" aria-labelledby="h-highlights">
<h2 id="h-highlights">Highlights</h2>
<dl>
  <dt>Main Hero</dt>
    <dd>{hero_icon_html(main_hero_id, px=28)}{main_hero} \u2014 {main_hero_games} games, {main_hero_wr:.1f}% win rate</dd>
  <dt>Best Kill Game</dt>
    <dd>{best_kills_n} kills \u2014 {hero_icon_html(best_kill_match.get('hero_id',0), px=20)}{best_kills_hero}</dd>
  <dt>Best Assist Game</dt>
    <dd>{best_assists_n} assists \u2014 {hero_icon_html(best_assist_match.get('hero_id',0), px=20)}{best_assists_hero}</dd>
  <dt>Best Net Worth Game</dt>
    <dd>{best_nw_n:,} souls \u2014 {hero_icon_html(best_nw_match.get('hero_id',0), px=20)}{best_nw_hero}</dd>
  <dt>Highest Damage Hero</dt>
    <dd>{hero_icon_html(best_dmg_hid, px=20)}{best_dmg_hero} \u2014 {fmt_big(best_dmg_total)} player damage ({best_dmg_dpm:,.0f}\u2009DPM)</dd>
  <dt>Best Accuracy Hero</dt>
    <dd>{hero_icon_html(best_acc_stat.get('hero_id',0), px=20)}{best_acc_hero} \u2014 {best_acc_pct:.1f}% <span class="note">(min.\u200a3 games)</span></dd>
  <dt>Longest Win Streak</dt>
    <dd>{best_win_streak} games in a row</dd>
  <dt>Current Streak</dt>
    <dd>{current_streak_label}</dd>
</dl>
</section>

<!-- ── Hero Roster ───────────────────────────────────────────────────────── -->
<section id="heroes" aria-labelledby="h-heroes">
<h2 id="h-heroes">Hero Roster</h2>
<p>All tracked heroes sorted by games played. <abbr title="Damage Per Minute to enemy players">DPM</abbr>, <abbr title="Net worth per minute (souls efficiency)">SPM</abbr>, and Denies are per-hero averages from the hero-stats endpoint.</p>
<div class="table-scroll">
<table>
  <caption>Hero performance \u2014 sorted by games played</caption>
  <thead>
    <tr>
      <th scope="col">Hero</th>
      <th scope="col">Games</th>
      <th scope="col">Win Rate</th>
      <th scope="col">Avg <abbr title="Kills / Deaths / Assists">K/D/A</abbr></th>
      <th scope="col"><abbr title="(Kills + Assists) \u00f7 Deaths">KDA</abbr></th>
      <th scope="col"><abbr title="Damage Per Minute">DPM</abbr></th>
      <th scope="col"><abbr title="Net worth per minute">SPM</abbr></th>
      <th scope="col"><abbr title="Average denies per game">Den</abbr></th>
      <th scope="col">Time</th>
    </tr>
  </thead>
  <tbody>
{_hero_rows}
  </tbody>
</table>
</div>
</section>

<!-- ── Combat Profile ────────────────────────────────────────────────────── -->
<section id="combat" aria-labelledby="h-combat">
<h2 id="h-combat">Combat Profile</h2>
<p>Damage output, survivability, and accuracy data aggregated from the hero-stats endpoint across all recorded games.</p>
<dl class="overview-dl">
  <dt>Total Player Damage</dt>        <dd>{fmt_big(total_player_damage)}</dd>
  <dt>Total Damage Taken</dt>         <dd>{fmt_big(total_player_damage_taken)}</dd>
  <dt>Total Boss Damage</dt>          <dd>{fmt_big(total_boss_damage)}</dd>
  <dt>Total Creep Damage</dt>         <dd>{fmt_big(total_creep_damage)}</dd>
  <dt>Total Neutral Damage</dt>       <dd>{fmt_big(total_neutral_damage)}</dd>
  <dt>Avg Player DPM</dt>             <dd>{avg_dpm:,.0f}</dd>
  <dt>Avg Damage Taken PM</dt>        <dd>{avg_dtpm:,.0f}</dd>
  <dt>Avg Mitigated PM</dt>           <dd>{avg_mitigated_pm:,.0f}</dd>
  <dt>Avg Objective DPM</dt>          <dd>{avg_obj_dpm:,.0f}</dd>
  <dt>Avg Shot Accuracy</dt>          <dd>{avg_accuracy_pct:.1f}%</dd>
  <dt>Avg Crit Rate</dt>              <dd>{avg_crit_pct:.1f}%</dd>
</dl>
<div class="table-scroll">
<table>
  <caption>Per-hero combat breakdown \u2014 sorted by games played</caption>
  <thead>
    <tr>
      <th scope="col">Hero</th>
      <th scope="col">Games</th>
      <th scope="col"><abbr title="Damage to Players per Minute">DPM</abbr></th>
      <th scope="col"><abbr title="Damage Taken per Minute">DTPM</abbr></th>
      <th scope="col"><abbr title="Damage Mitigated per Minute">MitPM</abbr></th>
      <th scope="col"><abbr title="Objective Damage per Minute">ObjPM</abbr></th>
      <th scope="col">Accuracy</th>
      <th scope="col">Crit\u2009%</th>
    </tr>
  </thead>
  <tbody>
{_combat_rows}
  </tbody>
</table>
</div>
</section>

<!-- ── Map Activity ──────────────────────────────────────────────────────── -->
<section id="map" aria-labelledby="h-map">
<h2 id="h-map">Map Activity</h2>
<figure>
  {_map_svg}
  <figcaption>{len(player_kill_positions)} kill positions and {len(player_death_positions)} death positions from {min(HEATMAP_MATCHES, n_matches)} recent matches. Dark dots mark kills; red dots mark deaths.</figcaption>
</figure>
</section>

{_enemy_sec}
{_ally_sec}

<!-- ── Recent Matches ────────────────────────────────────────────────────── -->
<section id="matches" aria-labelledby="h-matches">
<h2 id="h-matches">Recent Matches</h2>
<p>Last {min(15, n_matches)} of {n_matches} matches, most recent first.</p>
<div class="table-scroll">
<table>
  <caption>Recent match history</caption>
  <thead>
    <tr>
      <th scope="col">Result</th>
      <th scope="col">Hero</th>
      <th scope="col">Lvl</th>
      <th scope="col"><abbr title="Kills / Deaths / Assists">K/D/A</abbr></th>
      <th scope="col"><abbr title="(Kills + Assists) \u00f7 Deaths">KDA</abbr></th>
      <th scope="col">Net Worth</th>
      <th scope="col"><abbr title="Last Hits">CS</abbr></th>
      <th scope="col"><abbr title="Denies">Den</abbr></th>
      <th scope="col">Dur</th>
      <th scope="col">Date</th>
    </tr>
  </thead>
  <tbody>
{_recent_rows}
  </tbody>
</table>
</div>
</section>

</main>

<footer>
  <p>
    Generated <time datetime="{_today}">{_today}</time> \u00b7
    Data via <a href="https://deadlock-api.com">deadlock-api.com</a>
    (not affiliated with Valve) \u00b7
    Account {ACCOUNT_ID} \u00b7
    Static snapshot \u2014 no live data
  </p>
</footer>

</body>
</html>
'''

Path('dl-stats.html').write_text(HTML, encoding='utf-8')
print("dl-stats.html written.")
