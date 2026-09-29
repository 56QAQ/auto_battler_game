"""Print everything needed to implement a kit: skills (max level params), traces, eidolons."""
import sys

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from hsrsim.data import get_data

gd = get_data()
for key in sys.argv[1:]:
    enh = key.endswith('+')
    c = gd.character(key.rstrip('+'))
    cid = c['id']
    pre = ('1' + cid) if enh else cid
    tr = c['enhanced']['traces'] if enh else c['traces']
    print(f"##### {cid} {c['name']} / {c['name_cn']} | {c['path']} {c['element']} | energy {c['max_energy']} | spd {c['promotions'][-1]['spd']} aggro {c['promotions'][-1]['aggro']}")
    for sid, s in gd.skills.items():
        ok = (sid[:-2] == pre) if enh else (sid[:-2] == cid or (sid[:-2] == '1' + cid and gd.skills[sid]['type'].startswith('Memosprite')))
        if ok:
            if s['type'] in ('MazeNormal',): continue
            # player max level from traces
            lv = None
            for tid in tr:
                t = gd.traces[tid]
                if sid in t.get('skills', []): lv = t['max_level']
            lv = lv or 1
            prm = s['params'][min(lv, len(s['params'])) - 1] if s['params'] else []
            prm2 = s['params'][min(lv + 2, len(s['params'])) - 1] if s['params'] else []
            print(f"[{sid}] {s['type']} '{s['name']}' lv{lv} energy={s['energy']} tough={s['toughness']} sp_need={s['sp_need']} sp_add={s['sp_add']} atype={s['attack_type']} eff={s['effect']}")
            print(f"   params@lv{lv}: {prm}   @+2: {prm2}")
            print("   " + s.get('desc', '').replace('\n', ' '))
    for tid in tr:
        t = gd.traces[tid]
        if t['type'] in (3, 4, 5) and t.get('desc'):
            print(f"[trace {tid}] {t.get('name')} params={t['params']}: {t.get('desc', '')}".replace('\n', ' '))
    for n in range(1, 7):
        r = gd.ranks.get(f"{pre}0{n}")
        if r: print(f"[E{n}] {r.get('name')} params={r['params']} add={r['skill_add_level']}: {r.get('desc', '')}".replace('\n', ' '))
    print()
