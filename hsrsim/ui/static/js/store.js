// Application state, persistence and the JSON API client.

export async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    throw new Error(`HTTP ${res.status}`);
  }
  if (!res.ok) throw new Error(data && data.error ? data.error : `HTTP ${res.status}`);
  return data;
}

const LS = {
  get(k, d) {
    try {
      const v = localStorage.getItem("hsrsim." + k);
      return v ? JSON.parse(v) : d;
    } catch {
      return d;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem("hsrsim." + k, JSON.stringify(v));
    } catch {
      /* private mode */
    }
  },
};

export function defaultMember(character) {
  return {
    character,
    eidolon: 0,
    level: 80,
    light_cone: null,
    superimposition: 1,
    relics: {},
    main_stats: { body: "crit_rate", feet: "spd", sphere: "elemental", rope: "atk%" },
    substats: { crit_rate: "6r", crit_dmg: "8r", "atk%": "3r", spd: "3r" },
    enhanced: false,
    traces: true,
    options: {},
    skill_levels: {},
  };
}

export function defaultConfig() {
  return {
    team: ["1102", "1101", "1106", "1217"].map(defaultMember),
    scenario: { preset: "boss", cycles: 10, weaknesses: "all", enemy: { hp: 2000000, toughness: 160, spd: 132 } },
    config: { crit_mode: "expected", start_energy: 0.5, start_sp: 3, techniques: false, seed: 1, allies_immortal: true },
  };
}

export function defaultSettings() {
  return {
    auto_ult: {},
    pause: { before_enemy: true, before_ally: false, queue: true, mid_action: true },
  };
}

export const store = {
  catalog: null,
  chars: new Map(),
  lcs: new Map(),
  relics: new Map(),
  config: LS.get("config", null) || defaultConfig(),
  settings: LS.get("settings", null) || defaultSettings(),
  prefs: Object.assign({ lang: "cn", anim: true, showHidden: false }, LS.get("prefs", {})),
  presets: LS.get("presets", {}),
  view: "setup",
  slot: 0,
  previews: [null, null, null, null],
  session: null, // {sid, state, log}
};

export function saveConfig() {
  LS.set("config", store.config);
}
export function saveSettings() {
  LS.set("settings", store.settings);
}
export function savePrefs() {
  LS.set("prefs", store.prefs);
}
export function savePresets() {
  LS.set("presets", store.presets);
}

/** Translate an engine label (ability / trace / eidolon / gear / character name) to Chinese when available. */
export function tr(en) {
  if (!en || store.prefs.lang !== "cn" || !store.catalog) return en;
  const names = store.catalog.names || {};
  if (names[en]) return names[en];
  const m = String(en).match(/^(.*?)( \(.*\)| #\d+| [A-Z])$/);
  return m && names[m[1]] ? names[m[1]] + m[2] : en;
}

export function nameOf(obj) {
  if (!obj) return "";
  return store.prefs.lang === "cn" ? obj.name_cn || obj.name : obj.name || obj.name_cn;
}

/** Config as sent to the server: drop empty fields the Build dataclass does not need. */
export function exportConfig(cfg = store.config) {
  const out = JSON.parse(JSON.stringify(cfg));
  for (const m of out.team) {
    if (!m.light_cone) delete m.light_cone;
    for (const [k, v] of Object.entries(m.substats || {})) {
      if (!v || v === "0r") delete m.substats[k];
    }
  }
  out.team = out.team.filter((m) => m.character);
  return out;
}

export function loadCatalog(cat) {
  store.catalog = cat;
  store.chars = new Map(cat.characters.map((c) => [c.id, c]));
  store.lcs = new Map(cat.light_cones.map((c) => [c.id, c]));
  store.relics = new Map(cat.relic_sets.map((c) => [c.id, c]));
}

export function charOf(key) {
  if (!key) return null;
  if (store.chars.has(String(key))) return store.chars.get(String(key));
  const k = String(key).toLowerCase();
  for (const c of store.chars.values()) {
    if (c.name.toLowerCase() === k || c.name_cn === key) return c;
  }
  return null;
}

export function lcOf(key) {
  if (!key) return null;
  if (store.lcs.has(String(key))) return store.lcs.get(String(key));
  for (const c of store.lcs.values()) if (c.name === key || c.name_cn === key) return c;
  return null;
}

export function relicOf(key) {
  if (!key) return null;
  if (store.relics.has(String(key))) return store.relics.get(String(key));
  for (const c of store.relics.values()) if (c.name === key || c.name_cn === key) return c;
  return null;
}
