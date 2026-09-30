// Setup view: team, builds, enemies, battle config, presets.
import {
  api, store, saveConfig, savePresets, nameOf, exportConfig, charOf, lcOf, relicOf, defaultMember, defaultConfig,
} from "./store.js";
import {
  h, clear, picker, stepper, seg, toast, debounce, download, fmtInt, statLabel, statValue,
  EL_CN, EL_SHORT, PATH_CN, RANK_CN, ELEMENTS, elColor, fmt,
} from "./util.js";

let root = null;
let startBattle = null;
const infoCache = new Map();
const stageCache = new Map();

export function mountSetup(el, onStart) {
  root = el;
  startBattle = onStart;
  render();
  store.config.team.forEach((_, i) => refreshPreview(i));
}

function changed(rerender = true) {
  saveConfig();
  if (rerender) render();
}

function render() {
  const y = window.scrollY;
  clear(root);
  const main = h("div.col", { style: { gap: "14px", minWidth: 0 } }, teamRow(), editorCard(), enemyCard());
  const side = h("div.side-sticky", previewCard(), configCard(), presetCard(), startCard());
  root.appendChild(h("div.setup", main, side));
  window.scrollTo(0, y);
}

// ---------------------------------------------------------------------------------- team
function teamRow() {
  const row = h("div.team-row");
  store.config.team.forEach((m, i) => row.appendChild(slotCard(m, i)));
  while (row.children.length < 4) {
    const i = row.children.length;
    row.appendChild(
      h("div.slot", { onclick: () => { store.config.team.push(defaultMember(null)); store.slot = i; changed(); } },
        h("div.nm.dim", "＋ 添加角色"), h("div.meta", "空位")),
    );
  }
  return row;
}

function slotCard(m, i) {
  const c = charOf(m.character);
  const p = store.previews[i];
  const lc = lcOf(m.light_cone);
  const sets = Object.keys(m.relics || {}).map((k) => relicOf(k)).filter(Boolean);
  const card = h(
    "div.slot" + (store.slot === i ? ".on" : ""),
    { id: `slot-${i}`, style: { "--c": c ? elColor(c.element) : "var(--line2)" }, onclick: () => { store.slot = i; render(); } },
    h("div.num", i + 1),
    h("div.nm", c ? nameOf(c) : "（未选择）"),
    h(
      "div.meta",
      c ? `${EL_CN[c.element]} · ${PATH_CN[c.path]} · E${m.eidolon}${m.enhanced ? " · 强化版" : ""}` : "点击选择角色",
    ),
    h("div.meta", lc ? `${nameOf(lc)} S${m.superimposition}` : "无光锥"),
    h("div.meta", sets.length ? sets.map((s) => nameOf(s)).join(" + ") : "无套装"),
    p && p.stats
      ? h(
          "div.kv",
          h("span", "攻"), fmtInt(p.stats.ATK), h("span", "速"), p.stats.SPD.toFixed(1),
          h("span", "暴"), (p.stats["CRIT Rate"] * 100).toFixed(1) + "%", h("span", "爆"), (p.stats["CRIT DMG"] * 100).toFixed(0) + "%",
        )
      : null,
  );
  return card;
}

// -------------------------------------------------------------------------------- editor
function editorCard() {
  const i = store.slot;
  const m = store.config.team[i];
  if (!m) return h("div.card", h("h3", "角色配置"), h("div.muted", "选择上方的一个位置"));
  const c = charOf(m.character);
  const card = h("div.card", h("div.row", h("h3", `${i + 1} 号位 · 角色配置`),
    h("div.right.row",
      i > 0 ? h("button.btn.small", { onclick: () => swap(i, i - 1) }, "← 前移") : null,
      i < store.config.team.length - 1 ? h("button.btn.small", { onclick: () => swap(i, i + 1) }, "后移 →") : null,
      h("button.btn.small.danger", { onclick: () => { store.config.team.splice(i, 1); store.previews.splice(i, 1); store.previews.push(null); store.slot = Math.max(0, i - 1); changed(); } }, "移除"),
    )));
  const left = h("div.col", { style: { gap: "12px" } });
  const right = h("div.col", { style: { gap: "12px" } });
  card.appendChild(h("div.editor", left, right));

  // character
  const charItems = store.catalog.characters.filter((x) => x.implemented).map((x) => ({
    value: x.id,
    label: nameOf(x),
    sub: `${EL_CN[x.element]}·${PATH_CN[x.path]} ${"★".repeat(x.rarity === 5 ? 5 : 4)}`,
    color: elColor(x.element),
    search: `${x.name} ${x.name_cn} ${x.id}`,
  }));
  left.appendChild(
    field("角色", picker({
      items: charItems, value: c ? c.id : null, placeholder: "搜索角色（中/英文）",
      onPick: (v) => {
        if (!v) return;
        const dup = store.config.team.findIndex((x, j) => j !== i && x.character === v);
        if (dup >= 0) { toast("队伍中已有该角色"); render(); return; }
        m.character = v; m.enhanced = false; m.options = {};
        changed(); refreshPreview(i);
      },
    })),
  );
  if (!c) return card;

  left.appendChild(
    h("div.row.wrap", { style: { gap: "14px" } },
      field("星魂", seg([0, 1, 2, 3, 4, 5, 6].map((e) => [e, "E" + e]), m.eidolon, (v) => { m.eidolon = v; update(i); })),
      field("等级", numInput(m.level, 1, 80, (v) => { m.level = v; update(i); })),
      c.enhanced
        ? field("版本", seg([[false, "原版"], [true, "强化版"]], !!m.enhanced, (v) => { m.enhanced = v; update(i); infoCache.clear(); }))
        : null,
      field("行迹", h("label.switch", h("input", { type: "checkbox", checked: m.traces !== false, onchange: (e) => { m.traces = e.target.checked; update(i, false); } }), "全部点亮")),
    ),
  );

  // light cone
  const showAll = !!store.lcAll;
  const lcItems = store.catalog.light_cones
    .filter((x) => showAll || x.path === c.path)
    .map((x) => ({
      value: x.id,
      label: nameOf(x),
      sub: `${PATH_CN[x.path]} ${"★".repeat(x.rarity)}${x.effect ? "" : " · 仅属性"}`,
      search: `${x.name} ${x.name_cn}`,
    }));
  left.appendChild(
    h("div.grid2",
      field("光锥", picker({ items: lcItems, value: m.light_cone, allowNone: true, noneLabel: "（无光锥）", placeholder: "搜索光锥", onPick: (v) => { m.light_cone = v; update(i); } })),
      field("叠影", seg([1, 2, 3, 4, 5].map((s) => [s, "S" + s]), m.superimposition || 1, (v) => { m.superimposition = v; update(i); })),
    ),
  );
  left.appendChild(h("label.switch.muted", { style: { fontSize: "12px", marginTop: "-6px" } },
    h("input", { type: "checkbox", checked: showAll, onchange: (e) => { store.lcAll = e.target.checked; render(); } }), "显示所有命途的光锥"));

  // relics
  left.appendChild(relicEditor(m, i));
  // main stats
  const mains = h("div.grid4");
  for (const slot of ["body", "feet", "sphere", "rope"]) {
    const opts = store.catalog.main_stats[slot];
    const sel = h("select", { onchange: (e) => { m.main_stats[slot] = e.target.value; update(i); } },
      opts.map((o) => h("option", { value: o.key, selected: (m.main_stats || {})[slot] === o.key }, o.label_cn)));
    mains.appendChild(field({ body: "躯干", feet: "脚部", sphere: "位面球", rope: "连结绳" }[slot], sel));
  }
  left.appendChild(h("div", h("div.label", { style: { marginBottom: "4px" } }, "主词条"), mains));

  // substats
  right.appendChild(substatEditor(m, i));
  // skill levels + options
  right.appendChild(levelsEditor(m, i));
  right.appendChild(optionsEditor(m, i, c));
  right.appendChild(infoBlock(c, m));
  return card;
}

function swap(a, b) {
  const t = store.config.team;
  [t[a], t[b]] = [t[b], t[a]];
  [store.previews[a], store.previews[b]] = [store.previews[b], store.previews[a]];
  store.slot = b;
  changed();
}

function update(i, rerender = true) {
  saveConfig();
  if (rerender) render();
  refreshPreview(i);
}

function field(label, control) {
  return h("div.field", h("label", label), control);
}

function numInput(value, min, max, on, step = 1) {
  const inp = h("input", { type: "number", value, min, max, step });
  inp.addEventListener("change", () => {
    let v = parseFloat(inp.value);
    if (Number.isNaN(v)) v = min;
    on(Math.max(min, Math.min(max, v)));
  });
  inp.addEventListener("keydown", (e) => e.stopPropagation());
  return inp;
}

function relicEditor(m, i) {
  const caverns = Object.entries(m.relics || {}).filter(([k]) => relicOf(k) && !relicOf(k).planar);
  const planar = Object.keys(m.relics || {}).find((k) => relicOf(k) && relicOf(k).planar) || null;
  const mode = caverns.length === 2 ? "22" : "4";
  const cavItems = store.catalog.relic_sets.filter((r) => !r.planar).map((r) => ({ value: r.id, label: nameOf(r), sub: r.effect ? "" : "仅属性", search: `${r.name} ${r.name_cn}` }));
  const plaItems = store.catalog.relic_sets.filter((r) => r.planar).map((r) => ({ value: r.id, label: nameOf(r), sub: r.effect ? "" : "仅属性", search: `${r.name} ${r.name_cn}` }));
  const write = (cav, pla) => {
    const out = {};
    if (cav.length === 1 && cav[0]) out[cav[0]] = 4;
    if (cav.length === 2) cav.filter(Boolean).forEach((k) => (out[k] = (out[k] || 0) + 2));
    if (pla) out[pla] = 2;
    m.relics = out;
    update(i);
  };
  const cur = caverns.map(([k]) => k);
  const box = h("div.col", { style: { gap: "6px" } },
    h("div.row", h("div.label", "遗器套装"), h("div.right", seg([["4", "4 件套"], ["22", "2 + 2"]], mode, (v) => write(v === "4" ? [cur[0] || null] : [cur[0] || null, cur[1] || null], planar)))),
  );
  if (mode === "4") {
    box.appendChild(picker({ items: cavItems, value: cur[0] || null, allowNone: true, noneLabel: "（无）", placeholder: "隧洞遗器 4 件", onPick: (v) => write([v], planar) }));
  } else {
    box.appendChild(h("div.grid2",
      picker({ items: cavItems, value: cur[0] || null, allowNone: true, placeholder: "隧洞遗器 2 件", onPick: (v) => write([v, cur[1] || null], planar) }),
      picker({ items: cavItems, value: cur[1] || null, allowNone: true, placeholder: "隧洞遗器 2 件", onPick: (v) => write([cur[0] || null, v], planar) })));
  }
  box.appendChild(picker({ items: plaItems, value: planar, allowNone: true, noneLabel: "（无）", placeholder: "位面饰品 2 件", onPick: (v) => write(mode === "4" ? [cur[0] || null] : [cur[0] || null, cur[1] || null], v) }));
  return box;
}

function rollsOf(v) {
  if (v === undefined || v === null) return 0;
  if (typeof v === "number") return v;
  return parseFloat(String(v).replace(/r(olls)?/i, "")) || 0;
}

function substatEditor(m, i) {
  const subs = store.catalog.substats;
  const total = subs.reduce((a, s) => a + rollsOf(m.substats[s.key]), 0);
  const box = h("div.subs");
  for (const s of subs) {
    const r = rollsOf(m.substats[s.key]);
    const isPct = !["spd", "atk", "hp", "def"].includes(s.key);
    const val = h("span.val", r ? (isPct ? (r * s.roll * 100).toFixed(1) + "%" : (r * s.roll).toFixed(1)) : "");
    box.appendChild(h("div.sub-row", h("span.nm", s.label_cn), val,
      stepper(r, (v) => { if (v) m.substats[s.key] = v + "r"; else delete m.substats[s.key]; update(i, false); val.textContent = v ? (isPct ? (v * s.roll * 100).toFixed(1) + "%" : (v * s.roll).toFixed(1)) : ""; totalEl.textContent = String(subs.reduce((a, x) => a + rollsOf(m.substats[x.key]), 0)); }, { min: 0, max: 40 })));
  }
  const totalEl = h("b", String(total));
  return h("div", h("div.row", h("div.label", "副词条（次数 × 平均单次值）"), h("div.right.label", "合计 ", totalEl, " 次")), box);
}

function levelsEditor(m, i) {
  const kinds = [["basic", "普攻"], ["skill", "战技"], ["ult", "终结技"], ["talent", "天赋"]];
  const row = h("div.grid4");
  for (const [k, label] of kinds) {
    const inp = h("input", { type: "number", min: 1, max: 15, placeholder: "满级", value: (m.skill_levels || {})[k] || "" });
    inp.addEventListener("change", () => {
      m.skill_levels = m.skill_levels || {};
      const v = parseInt(inp.value, 10);
      if (v > 0) m.skill_levels[k] = v; else delete m.skill_levels[k];
      update(i, false);
    });
    inp.addEventListener("keydown", (e) => e.stopPropagation());
    row.appendChild(field(label, inp));
  }
  return h("div", h("div.label", { style: { marginBottom: "4px" } }, "技能等级（留空 = 行迹满级 + 星魂加成）"), row);
}

function optionsEditor(m, i, c) {
  const defaults = c.options || {};
  const keys = Object.keys(defaults);
  if (!keys.length) return h("div.label", "自动策略选项：无（手动操作时不影响）");
  const box = h("div.grid2");
  for (const k of keys) {
    const d = defaults[k];
    const v = k in (m.options || {}) ? m.options[k] : d;
    const set = (x) => { m.options = m.options || {}; if (x === d) delete m.options[k]; else m.options[k] = x; update(i, false); };
    let ctrl;
    if (typeof d === "boolean") ctrl = h("label.switch", h("input", { type: "checkbox", checked: !!v, onchange: (e) => set(e.target.checked) }), k);
    else if (typeof d === "number") ctrl = numInput(v, -1e9, 1e9, set, 0.01);
    else {
      ctrl = h("input", { type: "text", value: v ?? "" });
      ctrl.addEventListener("change", () => set(ctrl.value));
      ctrl.addEventListener("keydown", (e) => e.stopPropagation());
    }
    box.appendChild(field(k, ctrl));
  }
  return h("div", h("div.label", { style: { marginBottom: "4px" } }, "自动策略选项（仅影响“自动”行动）"), box);
}

function infoBlock(c, m) {
  const key = `${c.id}:${m.enhanced ? 1 : 0}`;
  const box = h("details", { open: !!store.infoOpen, ontoggle: (e) => (store.infoOpen = e.target.open) }, h("summary.label", { style: { cursor: "pointer" } }, "技能 / 行迹 / 星魂说明"));
  const body = h("div.info-block", h("div.muted", "加载中…"));
  box.appendChild(body);
  const fill = (info) => {
    clear(body);
    const L = (x) => (store.prefs.lang === "cn" ? x.desc_cn || x.desc : x.desc);
    for (const s of info.skills) {
      body.appendChild(h("div.item", h("div.ttl", h("span.tag", s.type_text || s.type), nameOf(s)), h("div.muted", L(s))));
    }
    for (const t of info.traces) body.appendChild(h("div.item", h("div.ttl", h("span.tag", "行迹"), nameOf(t)), h("div.muted", L(t))));
    for (const r of info.ranks) {
      body.appendChild(h("div.item" + (r.rank > m.eidolon ? ".off" : ""), h("div.ttl", h("span.tag", "E" + r.rank), nameOf(r)), h("div.muted", L(r))));
    }
  };
  if (infoCache.has(key)) fill(infoCache.get(key));
  else api(`/api/character/${c.id}?enhanced=${m.enhanced ? 1 : 0}`).then((info) => { infoCache.set(key, info); fill(info); }).catch((e) => (body.textContent = e.message));
  return box;
}

// ------------------------------------------------------------------------------- preview
const pending = new Map();
export function refreshPreview(i) {
  const m = store.config.team[i];
  if (!m || !m.character) { store.previews[i] = null; return; }
  clearTimeout(pending.get(i));
  pending.set(i, setTimeout(async () => {
    try {
      const build = exportConfig({ team: [m], scenario: {}, config: {} }).team[0];
      store.previews[i] = await api("/api/preview", "POST", { build });
    } catch (e) {
      store.previews[i] = { error: e.message };
    }
    if (store.view !== "setup") return;
    const old = document.getElementById(`slot-${i}`);
    if (old) old.replaceWith(slotCard(m, i));
    if (i === store.slot) {
      const pc = document.getElementById("preview-card");
      if (pc) pc.replaceWith(previewCard());
    }
  }, 180));
}

function previewCard() {
  const m = store.config.team[store.slot];
  const p = store.previews[store.slot];
  const card = h("div.card#preview-card", h("h3", "面板预览（战斗外）"));
  if (!m || !m.character) return card.appendChild(h("div.muted", "未选择角色")), card;
  if (!p) return card.appendChild(h("div.muted", "计算中…")), card;
  if (p.error) return card.appendChild(h("div.notes", p.error)), card;
  const list = h("div.statlist");
  for (const [k, v] of Object.entries(p.stats)) list.append(h("span.k", statLabel(k)), h("span.v", statValue(k, v)));
  for (const [k, v] of Object.entries(p.extra || {})) list.append(h("span.k", statLabel(k)), h("span.v", statValue(k, v)));
  list.append(h("span.k", "能量上限"), h("span.v", String(p.max_energy)));
  card.appendChild(list);
  if (p.notes && p.notes.length) card.appendChild(h("div.notes", p.notes.map((n) => h("div", "⚠ " + n))));
  return card;
}

// -------------------------------------------------------------------------------- enemies
function scenarioMode(sc) {
  if (sc.waves) return "custom";
  if (["moc", "pf", "as"].includes(sc.preset)) return sc.preset;
  return sc.preset === "aoe" ? "aoe" : "boss";
}

function enemyCard() {
  const sc = store.config.scenario;
  const mode = scenarioMode(sc);
  const card = h("div.card", h("h3", "敌人与关卡"));
  card.appendChild(seg([["moc", "混沌回忆"], ["pf", "虚构叙事"], ["as", "末日幻影"], ["boss", "单体首领"], ["aoe", "多目标"], ["custom", "自定义波次"]], mode, (v) => {
    if (v === mode) return;
    if (["moc", "pf", "as"].includes(v)) {
      const g = store.catalog.endgame[v].at(-1);
      const fl = g.floors.at(-1);
      store.config.scenario = { preset: v, group: g.group, floor: fl.floor, half: 1 };
    } else if (v === "boss") store.config.scenario = { preset: "boss", cycles: 10, weaknesses: "all", enemy: { hp: 2000000, toughness: 160, spd: 132 } };
    else if (v === "aoe") store.config.scenario = { preset: "aoe", cycles: 10, count: 5, weaknesses: "all", enemy: { hp: 600000, toughness: 100, spd: 132 } };
    else store.config.scenario = { name: "custom", cycles: 10, waves: [[enemySpec()]] };
    changed();
  }));
  const body = h("div", { style: { marginTop: "12px" } });
  card.appendChild(body);
  if (["moc", "pf", "as"].includes(mode)) body.appendChild(endgameEditor(sc, mode));
  else if (mode === "custom") body.appendChild(customEditor(sc));
  else body.appendChild(presetEditor(sc, mode));
  return card;
}

function enemySpec(extra = {}) {
  return Object.assign({ name: "Enemy", rank: "elite", level: 95, hp: 1000000, toughness: 100, spd: 132, weaknesses: ["Physical", "Fire"], effect_res: 0.3, default_res: 0.2, count: 1 }, extra);
}

function weakToggle(list, onChange) {
  const cur = list === "all" ? [...ELEMENTS] : [...(list || [])];
  const box = h("div.wk");
  for (const el of ELEMENTS) {
    box.appendChild(h("button" + (cur.includes(el) ? ".on" : ""), {
      type: "button", title: EL_CN[el], style: { "--c": elColor(el) },
      onclick: () => {
        const i = cur.indexOf(el);
        if (i >= 0) cur.splice(i, 1); else cur.push(el);
        onChange(cur.length === 7 ? "all" : ELEMENTS.filter((e) => cur.includes(e)));
      },
    }, EL_SHORT[el]));
  }
  return box;
}

function endgameEditor(sc, mode) {
  const groups = store.catalog.endgame[mode];
  const g = groups.find((x) => x.group === sc.group) || groups.at(-1);
  const fl = g.floors.find((x) => x.floor === sc.floor) || g.floors.at(-1);
  const half = sc.half || 1;
  const set = (patch) => { Object.assign(store.config.scenario, patch); changed(); };
  const box = h("div.col");
  box.appendChild(h("div.row.wrap", { style: { gap: "12px" } },
    field("期数", h("select", { onchange: (e) => { const ng = groups.find((x) => x.group === +e.target.value); set({ group: ng.group, floor: ng.floors.at(-1).floor }); } },
      groups.map((x) => h("option", { value: x.group, selected: x.group === g.group }, `${x.group}（${x.begin.slice(0, 10)} ~ ${x.end.slice(0, 10)}）`)))),
    field("层数", h("select", { onchange: (e) => set({ floor: +e.target.value }) }, g.floors.map((x) => h("option", { value: x.floor, selected: x.floor === fl.floor }, `第 ${x.floor} 层`)))),
    field("上/下半", seg([[1, "上半"], [2, "下半"]], half, (v) => set({ half: v }))),
    field("轮次上限", numInput(sc.cycles || fl.cycles || (mode === "moc" ? 30 : 4), 1, 100, (v) => set({ cycles: v }))),
    h("div.field", h("label", "弱点提示"), h("div.row", (fl.halves[half - 1] || []).map((e) => h("span.elchip", { style: { "--c": elColor(e) }, title: EL_CN[e] }, EL_SHORT[e])))),
  ));
  const table = h("div.muted", "加载敌人数据…");
  box.appendChild(table);
  const key = `${mode}/${g.group}/${fl.floor}/${half}`;
  const show = (stage) => {
    const t = h("table.enemy-table", h("tr", ["波次", "敌人", "级别", "等级", "生命", "韧性", "速度", "弱点"].map((x) => h("th", x))));
    stage.waves.forEach((w, wi) => {
      const mons = Array.isArray(w) ? w : w.monsters;
      mons.forEach((mo, mi) => t.appendChild(h("tr",
        h("td", mi === 0 ? (Array.isArray(w) ? `第 ${wi + 1} 波` : `无限波 ${wi + 1}（最多 ${w.max_count} 只，场上 ${w.on_field}）`) : ""),
        h("td", mo.name), h("td", RANK_CN[mo.rank] || mo.rank), h("td", mo.level), h("td", fmt(mo.hp)), h("td", Math.round(mo.toughness)), h("td", mo.spd.toFixed(0)),
        h("td", h("div.row", { style: { gap: "2px" } }, mo.weaknesses.map((e) => h("span.elchip", { style: { "--c": elColor(e), width: "16px", height: "16px", fontSize: "9px" } }, EL_SHORT[e])))),
      )));
    });
    clear(table).className = "";
    table.appendChild(t);
    const infinite = stage.waves.some((w) => !Array.isArray(w));
    table.appendChild(h("div.row", { style: { marginTop: "8px" } },
      h("button.btn.small", { disabled: infinite, title: infinite ? "虚构叙事的无限波次不能复制" : "", onclick: () => {
        store.config.scenario = { name: `${mode}-${g.group}-${fl.floor}-${half}`, cycles: sc.cycles || fl.cycles || 30, waves: stage.waves.map((w) => w.map((mo) => ({ name: mo.name, rank: mo.rank, level: mo.level, hp: Math.round(mo.hp), atk: mo.atk, toughness: mo.toughness, spd: mo.spd, weaknesses: mo.weaknesses, res: mo.res, default_res: 0, effect_res: mo.effect_res, initial_delay: mo.initial_delay, count: 1 }))) };
        changed();
        toast("已复制到自定义波次，可以修改敌人数值", true);
      } }, "复制到自定义波次（可修改数值）")));
  };
  if (stageCache.has(key)) show(stageCache.get(key));
  else api(`/api/endgame/${key}`).then((s) => { stageCache.set(key, s); show(s); }).catch((e) => (table.textContent = e.message));
  return box;
}

function presetEditor(sc, mode) {
  const e = (sc.enemy = sc.enemy || {});
  const set = () => changed(false);
  return h("div.col",
    h("div.row.wrap", { style: { gap: "12px" } },
      mode === "aoe" ? field("数量", numInput(sc.count || 5, 1, 5, (v) => { sc.count = v; set(); })) : null,
      field("生命值", numInput(e.hp || 1e6, 1, 1e13, (v) => { e.hp = v; set(); }, 1000)),
      field("韧性", numInput(e.toughness || 100, 1, 10000, (v) => { e.toughness = v; set(); })),
      field("速度", numInput(e.spd || 132, 1, 1000, (v) => { e.spd = v; set(); })),
      field("等级", numInput(e.level || 95, 1, 120, (v) => { e.level = v; set(); })),
      field("效果抵抗", numInput(e.effect_res ?? 0.3, 0, 5, (v) => { e.effect_res = v; set(); }, 0.05)),
      field("轮次上限", numInput(sc.cycles || 10, 1, 100, (v) => { sc.cycles = v; set(); })),
    ),
    field("弱点", weakToggle(sc.weaknesses || "all", (v) => { sc.weaknesses = v; changed(); })),
  );
}

function customEditor(sc) {
  const box = h("div.col");
  box.appendChild(h("div.row", field("轮次上限", numInput(sc.cycles || 10, 1, 100, (v) => { sc.cycles = v; changed(false); })),
    h("button.btn.small.right", { onclick: () => { sc.waves.push([enemySpec()]); changed(); } }, "＋ 添加波次")));
  sc.waves.forEach((wave, wi) => {
    const wb = h("div.wave-box", h("div.row", h("b", `第 ${wi + 1} 波`),
      h("button.btn.small.right", { onclick: () => { wave.push(enemySpec()); changed(); } }, "＋ 敌人"),
      sc.waves.length > 1 ? h("button.btn.small.danger", { onclick: () => { sc.waves.splice(wi, 1); changed(); } }, "删除波次") : null));
    const t = h("table.enemy-table", h("tr", ["名称", "级别", "等级", "生命", "韧性", "速度", "效果抵抗", "数量", "弱点", ""].map((x) => h("th", x))));
    wave.forEach((en, ei) => {
      const set = (k) => (v) => { en[k] = v; changed(false); };
      const name = h("input", { type: "text", value: en.name });
      name.addEventListener("change", () => { en.name = name.value || "Enemy"; changed(false); });
      name.addEventListener("keydown", (e) => e.stopPropagation());
      t.appendChild(h("tr",
        h("td", name),
        h("td", h("select", { onchange: (e) => set("rank")(e.target.value) }, ["normal", "elite", "boss"].map((r) => h("option", { value: r, selected: en.rank === r }, RANK_CN[r])))),
        h("td", numInput(en.level || 95, 1, 120, set("level"))),
        h("td", numInput(en.hp, 1, 1e13, set("hp"), 1000)),
        h("td", numInput(en.toughness, 1, 10000, set("toughness"))),
        h("td", numInput(en.spd, 1, 1000, set("spd"))),
        h("td", numInput(en.effect_res ?? 0.3, 0, 5, set("effect_res"), 0.05)),
        h("td", numInput(en.count || 1, 1, 5, set("count"))),
        h("td", weakToggle(en.weaknesses, (v) => { en.weaknesses = v; changed(); })),
        h("td", wave.length > 1 ? h("button.btn.small.danger", { onclick: () => { wave.splice(ei, 1); changed(); } }, "×") : null),
      ));
    });
    wb.appendChild(h("div", { style: { overflowX: "auto" } }, t));
    box.appendChild(wb);
  });
  return box;
}

// --------------------------------------------------------------------------------- config
function configCard() {
  const c = store.config.config;
  const set = (k) => (v) => { c[k] = v; changed(false); };
  return h("div.card", h("h3", "战斗设置"),
    h("div.col",
      h("div.row", h("span.label.grow", "暴击"), seg([["expected", "期望值"], ["random", "随机"]], c.crit_mode || "expected", (v) => { c.crit_mode = v; changed(); })),
      h("div.row", h("span.label.grow", "开局能量"), numInput(Math.round((c.start_energy ?? 0.5) * 100), 0, 100, (v) => set("start_energy")(v / 100)), h("span.muted", "%")),
      h("div.row", h("span.label.grow", "开局战技点"), numInput(c.start_sp ?? 3, 0, 5, set("start_sp"))),
      h("div.row", h("span.label.grow", "随机种子"), numInput(c.seed ?? 1, 0, 1e9, set("seed"))),
      h("label.switch", h("input", { type: "checkbox", checked: !!c.techniques, onchange: (e) => set("techniques")(e.target.checked) }), "开局使用秘技"),
      h("label.switch", h("input", { type: "checkbox", checked: c.allies_immortal !== false, onchange: (e) => set("allies_immortal")(e.target.checked) }), "我方不会倒下（生命最低为 1）"),
    ));
}

function presetCard() {
  const names = Object.keys(store.presets).sort();
  const nameIn = h("input", { type: "text", placeholder: "方案名称" });
  nameIn.addEventListener("keydown", (e) => e.stopPropagation());
  const fileIn = h("input", { type: "file", accept: ".json,application/json", class: "hidden", onchange: async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const cfg = JSON.parse(await f.text());
      if (!Array.isArray(cfg.team)) throw new Error("缺少 team");
      loadConfigObject(cfg);
      toast("已导入", true);
    } catch (err) { toast("导入失败：" + err.message); }
  } });
  return h("div.card", h("h3", "配置方案"),
    h("div.row", nameIn, h("button.btn", { onclick: () => {
      const n = nameIn.value.trim();
      if (!n) return toast("请输入名称");
      store.presets[n] = JSON.parse(JSON.stringify(store.config));
      savePresets(); render(); toast("已保存", true);
    } }, "保存")),
    names.length ? h("div.col", { style: { marginTop: "8px", gap: "4px" } }, names.map((n) => h("div.row",
      h("span.grow", n),
      h("button.btn.small", { onclick: () => { loadConfigObject(store.presets[n]); toast(`已载入 ${n}`, true); } }, "载入"),
      h("button.btn.small.danger", { onclick: () => { delete store.presets[n]; savePresets(); render(); } }, "删除")))) : h("div.muted", { style: { fontSize: "12px", marginTop: "6px" } }, "还没有保存的方案"),
    h("div.row", { style: { marginTop: "10px" } },
      h("button.btn.small", { onclick: () => download("hsrsim-config.json", JSON.stringify(exportConfig(), null, 2)) }, "导出 JSON"),
      h("button.btn.small", { onclick: () => fileIn.click() }, "导入 JSON"), fileIn,
      h("button.btn.small.ghost.right", { onclick: () => { loadConfigObject(defaultConfig()); } }, "恢复默认")),
    h("div.dim", { style: { fontSize: "11px", marginTop: "6px" } }, "导出的 JSON 可直接用于 python -m hsrsim run"),
  );
}

function loadConfigObject(cfg) {
  const base = defaultConfig();
  const team = (cfg.team || []).slice(0, 4).map((m) => {
    const c = charOf(m.character);
    const lc = lcOf(m.light_cone);
    const relics = {};
    for (const [k, v] of Object.entries(m.relics || {})) { const r = relicOf(k); if (r) relics[r.id] = v; }
    return Object.assign(defaultMember(c ? c.id : null), m, { character: c ? c.id : null, light_cone: lc ? lc.id : null, relics });
  });
  store.config = { team, scenario: cfg.scenario || base.scenario, config: Object.assign(base.config, cfg.config || {}) };
  store.previews = [null, null, null, null];
  store.slot = 0;
  changed();
  store.config.team.forEach((_, i) => refreshPreview(i));
}

function startCard() {
  const team = store.config.team.filter((m) => m.character);
  return h("div.card",
    h("button.btn.primary", { style: { width: "100%", padding: "12px", fontSize: "16px" }, disabled: !team.length, onclick: () => startBattle() }, "开始战斗 ▶"),
    h("div.dim", { style: { fontSize: "11.5px", marginTop: "8px", lineHeight: 1.6 } },
      "战斗中：", h("kbd", "Q"), " 普攻 ", h("kbd", "E"), " 战技 ", h("kbd", "1"), "–", h("kbd", "4"), " 终结技（可在任意插入时机释放）",
      h("br"), h("kbd", "←"), h("kbd", "→"), " 切换目标 ", h("kbd", "空格"), " 确认 / 继续 ", h("kbd", "Z"), " 撤销 ", h("kbd", "X"), " 自动一步"),
  );
}
