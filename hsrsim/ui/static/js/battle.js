// Battle view: turn-by-turn manual control with Ultimate insertion.
import { api, store, saveSettings, savePrefs, exportConfig, charOf, nameOf, tr } from "./store.js";
import {
  h, clear, put, fmt, fmtInt, pct, toast, modal, EL_CN, EL_SHORT, PATH_CN, RANK_CN, KIND_CN, PART_CN, elColor,
  statLabel, statValue,
} from "./util.js";

const HOTKEYS = ["q", "e", "r", "f", "g", "t"];
const B = {
  root: null,
  sid: null,
  state: null,
  log: [],
  target: null,
  allyTarget: null,
  armed: null, // {type: "act", item} | {type: "ult", who}
  tab: "log",
  detail: null,
  open: new Set(),
  busy: false,
  cards: new Map(),
  ticker: [],
  pointKey: "",
  resultShown: false,
  onExit: null,
};

document.addEventListener("hsrsim-rerender", () => {
  if (B.state) render();
});

// ================================================================================ lifecycle
export async function startBattle(root, onExit) {
  B.root = root;
  B.onExit = onExit;
  B.cards.clear();
  B.ticker = [];
  B.log = [];
  B.target = null;
  B.allyTarget = null;
  B.armed = null;
  B.resultShown = false;
  B.open.clear();
  layout();
  setBusy(true);
  try {
    const st = await api("/api/session", "POST", { config: exportConfig(), settings: store.settings });
    B.sid = st.sid;
    loadDescriptions(st);
    onState(st, true);
  } catch (e) {
    setBusy(false);
    modal("无法开始战斗", h("pre", e.message), [["返回配置", onExit]]);
  }
}

export function battleActive() {
  return !!B.sid && store.view === "battle";
}

const DESC = new Map(); // skill name (EN) -> description (current language)
async function loadDescriptions(st) {
  for (const a of st.allies) {
    try {
      const info = await api(`/api/character/${a.id}?enhanced=${a.enhanced ? 1 : 0}`);
      for (const s of info.skills) DESC.set(s.name, store.prefs.lang === "cn" ? s.desc_cn || s.desc : s.desc);
    } catch {
      /* descriptions are optional */
    }
  }
}

function setBusy(v) {
  B.busy = v;
  document.body.style.cursor = v ? "progress" : "";
}

async function call(path, body, full = false) {
  if (B.busy || !B.sid) return;
  setBusy(true);
  try {
    const st = await api(`/api/session/${B.sid}/${path}`, "POST", Object.assign({ settings: store.settings, since: B.log.length }, body));
    onState(st, full);
  } catch (e) {
    setBusy(false);
    toast(e.message);
  }
}

const decide = (d) => call("decide", { decision: d });
const auto = (mode) => call("auto", { mode });
const undo = () => call("undo", { steps: 1 }, true);

function onState(st, full) {
  setBusy(false);
  const fresh = full ? [] : st.log || [];
  if (full) B.log = st.log || [];
  else B.log.push(...fresh);
  B.state = st;
  if (st.settings) {
    // the server echoes the settings in force (they may come from a replay after undo)
    store.settings.auto_ult = st.settings.auto_ult || {};
    store.settings.pause = st.settings.pause || store.settings.pause;
  }
  const key = st.point ? `${st.decisions}|${st.point.kind}|${st.point.actor || st.point.subject || ""}` : "end";
  if (key !== B.pointKey) B.armed = null;
  B.pointKey = key;
  fixTargets();
  render();
  if (!full) animate(fresh);
  else B.ticker = [];
  if (st.error) toast(st.error);
  if (st.fatal) {
    modal("战斗逻辑出错", h("div", h("div.muted", "角色套件在执行这一步时抛出了异常。可以撤销后换一种操作。"), h("pre", st.fatal)), [["撤销这一步", undo, "primary"]]);
  } else if (st.finished && !B.resultShown) {
    B.resultShown = true;
    setTimeout(showResult, 450);
  } else if (!st.finished) B.resultShown = false;
}

// ================================================================================== targets
function aliveEnemies() {
  return (B.state?.enemies || []).filter((e) => e.alive && e.hp > 0 && e.targetable !== false);
}

function fixTargets() {
  const es = aliveEnemies();
  if (!es.find((e) => e.ref === B.target)) {
    const boss = [...es].sort((a, b) => b.max_hp - a.max_hp)[0];
    const mid = es[Math.floor((es.length - 1) / 2)];
    B.target = (boss && boss.max_hp > (mid?.max_hp || 0) * 1.5 ? boss : mid)?.ref || null;
  }
  const allies = (B.state?.allies || []).filter((a) => a.alive);
  if (!allies.find((a) => a.ref === B.allyTarget)) {
    const actor = B.state?.point?.actor;
    B.allyTarget = (allies.find((a) => a.ref !== actor) || allies[0])?.ref || null;
  }
}

function armedKind() {
  const st = B.state;
  if (!st || !B.armed) return null;
  if (B.armed.type === "act") {
    const it = currentMenu().find((m) => m.id === B.armed.item);
    return it ? { target: it.target, shape: it.shape } : null;
  }
  const a = st.allies.find((x) => x.ref === B.armed.who);
  return a ? { target: a.ult_target, shape: a.ult_shape } : null;
}

function currentMenu() {
  const p = B.state?.point;
  return p && p.kind === "turn" ? p.menu || [] : [];
}

function moveTarget(dir) {
  const k = armedKind();
  if (k && (k.target === "ally")) {
    const allies = B.state.allies.filter((a) => a.alive);
    const i = allies.findIndex((a) => a.ref === B.allyTarget);
    B.allyTarget = allies[(i + dir + allies.length) % allies.length].ref;
  } else {
    const es = aliveEnemies();
    if (!es.length) return;
    const i = es.findIndex((e) => e.ref === B.target);
    B.target = es[(i + dir + es.length) % es.length].ref;
  }
  renderTargets();
}

function targetFor(kind) {
  if (kind === "enemy" || kind === "enemies") return B.target || "";
  if (kind === "ally") return B.allyTarget || "";
  return "";
}

// ================================================================================== actions
function pressItem(item) {
  if (!item || B.busy) return;
  if (!item.enabled) return toast(`${label(item)}：${item.note || "当前不可用"}`);
  if ((B.armed && B.armed.type === "act" && B.armed.item === item.id) || store.prefs.quick) return confirm(item);
  B.armed = { type: "act", item: item.id };
  renderArmed();
}

function pressUlt(ref) {
  const st = B.state;
  if (!st || !st.point || B.busy) return;
  const a = st.allies.find((x) => x.ref === ref);
  if (!a) return;
  if (!a.alive) return;
  if (!a.ult_ready) {
    const r = a.ult_res || { cur: a.energy, max: a.max_energy, label: "能量" };
    return toast(`${nameOf(charOf(a.id) || a)}：终结技未就绪（${r.label} ${+r.cur.toFixed(1)}/${+r.max.toFixed(1)}）`);
  }
  if ((B.armed && B.armed.type === "ult" && B.armed.who === ref) || store.prefs.quick) return confirmUlt(ref);
  B.armed = { type: "ult", who: ref };
  renderArmed();
}

function confirm(item) {
  B.armed = null;
  decide({ kind: "act", item: item.id, target: targetFor(item.target) });
}

function confirmUlt(ref) {
  const a = B.state.allies.find((x) => x.ref === ref);
  B.armed = null;
  decide({ kind: "ult", who: ref, target: targetFor(a.ult_target) });
}

function confirmArmed() {
  const p = B.state?.point;
  if (!p) return;
  if (B.armed?.type === "act") return confirm(currentMenu().find((m) => m.id === B.armed.item));
  if (B.armed?.type === "ult") return confirmUlt(B.armed.who);
  if (p.kind === "window") return decide({ kind: "continue" });
  toast("请先选择行动：Q 普攻 / E 战技，或 1–4 释放终结技");
}

export function onKey(e) {
  if (!battleActive() || document.querySelector(".modal-bg")) return;
  const k = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && k === "z") { e.preventDefault(); return undo(); }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const menu = currentMenu();
  const hk = HOTKEYS.indexOf(k);
  if (hk >= 0 && B.state?.point?.kind === "turn") {
    const item = menu.find((m, i) => hotkeyOf(m, i, menu) === k);
    if (item) { e.preventDefault(); return pressItem(item); }
  }
  if (["1", "2", "3", "4"].includes(k)) {
    const a = B.state?.allies?.[+k - 1];
    if (a) { e.preventDefault(); return pressUlt(a.ref); }
  }
  if (k === "arrowleft" || k === "a") { e.preventDefault(); return moveTarget(-1); }
  if (k === "arrowright" || k === "d") { e.preventDefault(); return moveTarget(1); }
  if (k === " " || k === "enter") { e.preventDefault(); return confirmArmed(); }
  if (k === "escape") { B.armed = null; return renderArmed(); }
  if (k === "z") return undo();
  if (k === "x") return auto(e.shiftKey ? "ally_turn" : "once");
  if (k === "c") return auto("cycle");
}

function hotkeyOf(item, i, menu) {
  if (item.kind === "basic" && !menu.slice(0, i).some((m) => m.kind === "basic")) return "q";
  if (item.kind === "skill" && !menu.slice(0, i).some((m) => m.kind === "skill")) return "e";
  const others = menu.filter((m, j) => !((m.kind === "basic" && !menu.slice(0, j).some((x) => x.kind === "basic")) || (m.kind === "skill" && !menu.slice(0, j).some((x) => x.kind === "skill"))));
  const idx = others.indexOf(item);
  return idx >= 0 ? HOTKEYS[2 + idx] : "";
}

function label(item) {
  return store.prefs.lang === "cn" ? item.label_cn || item.label : item.label;
}

// =================================================================================== layout
function layout() {
  clear(B.root);
  const panel = h("div.panel#panel",
    h("div.ptabs", [["log", "战斗记录"], ["stats", "伤害统计"], ["detail", "单位详情"], ["settings", "操作设置"]].map(([k, t]) =>
      h("button" + (B.tab === k ? ".on" : ""), { dataset: { tab: k }, onclick: () => { B.tab = k; renderPanel(); } }, t))),
    h("div.pbody#pbody"));
  B.root.appendChild(h("div.battle",
    h("div.order#order"),
    h("div.stage",
      h("div.enemies#enemies"),
      h("div.prompt#prompt"),
      h("div.ticker#ticker"),
      h("div.actions#actions"),
      h("div.allies#allies")),
    panel));
}

function render() {
  if (!B.state) return;
  renderStatus();
  renderOrder();
  renderEnemies();
  renderAllies();
  renderPrompt();
  renderActions();
  renderTicker();
  renderPanel();
}

function renderArmed() {
  renderOrder();
  renderActions();
  renderAllies();
  renderTargets();
  renderPrompt();
}

// status in the top bar
function renderStatus() {
  const box = document.getElementById("battle-status");
  if (!box) return;
  const st = B.state;
  clear(box);
  const sp = h("span.row", { style: { gap: "3px" } });
  for (let i = 0; i < st.max_sp; i++) sp.appendChild(h("span", { style: { width: "10px", height: "10px", transform: "rotate(45deg)", background: i < st.sp ? "var(--gold)" : "transparent", border: "1px solid var(--gold2)", display: "inline-block" } }));
  const el = st.elation;
  put(box,
    h("span.pill", "轮次 ", h("b", `${shownCycle(st)}${st.scenario?.cycles ? " / " + st.scenario.cycles : ""}`), h("span.dim", ` · 行动值 ${st.time.toFixed(1)}`)),
    h("span.pill", "波次 ", h("b", `${st.wave} / ${st.waves}`)),
    h("span.pill", "战技点 ", sp, h("b", `${st.sp}/${st.max_sp}`)),
    el ? h("span.pill.punch", { title: `笑点：阿哈行动时发动阿哈时刻并消耗全部笑点，计入欢愉技伤害\n欢愉角色 ${el.chars} 名 · 阿哈速度 ${el.aha_spd}${el.aha ? "" : "（未在行动条上）"}\n已发动阿哈时刻 ${el.instants} 次` }, "笑点 ", h("b", String(el.punchline))) : null,
    h("span.pill", "总伤害 ", h("b", fmt(st.total))),
    h("button.btn.small", { title: "撤销上一步 (Z)", disabled: !st.undo, onclick: undo }, "↶ 撤销"),
    autoMenu(),
    h("button.btn.small", { title: "用同样的配置重新开始", onclick: () => startBattle(B.root, B.onExit) }, "⟲ 重开"),
  );
}

function shownCycle(st) {
  const lim = st.scenario?.cycles;
  return lim && st.finished ? Math.min(st.cycle, lim) : st.cycle;
}

function autoMenu() {
  const sel = h("select", { title: "让角色套件的自动策略代为操作", onchange: (e) => { const v = e.target.value; e.target.value = ""; if (v) auto(v); } },
    h("option", { value: "" }, "自动…"),
    h("option", { value: "once" }, "自动这一步 (X)"),
    h("option", { value: "ally_turn" }, "自动到下个我方回合 (Shift+X)"),
    h("option", { value: "cycle" }, "自动到下一轮 (C)"),
    h("option", { value: "wave" }, "自动到下一波"),
    h("option", { value: "end" }, "自动到战斗结束"));
  sel.addEventListener("keydown", (e) => e.stopPropagation());
  return sel;
}

// action order
function renderOrder() {
  const box = document.getElementById("order");
  const st = B.state;
  clear(box).appendChild(h("h4", "行动顺序"));
  if (B.armed?.type === "ult") {
    const a = st.allies.find((x) => x.ref === B.armed.who);
    box.appendChild(h("div.ord.insert", h("span.el", { style: { "--c": "var(--energy)" } }), h("span", "终结技 · " + unitName(a)), h("span.av", "插入")));
  }
  const cur = st.point?.actor || (st.point?.where === "before_turn" ? st.point?.subject : null);
  st.order.forEach((o, i) => {
    const u = unitByRef(o.ref);
    const color = u?.element ? elColor(u.element) : o.side === "enemy" ? "var(--hp-enemy)" : "var(--hp)";
    box.appendChild(h("div.ord." + (o.side === "enemy" ? "enemy" : "ally") + (i === 0 && o.ref === cur ? ".now" : ""),
      { onclick: () => showDetail(o.ref) },
      h("span.el", { style: { "--c": color } }), h("span", unitName(u) || o.name), h("span.av", o.av.toFixed(1))));
  });
}

// enemies
function renderEnemies() {
  const box = document.getElementById("enemies");
  const st = B.state;
  const refs = new Set(st.enemies.map((e) => e.ref));
  for (const [ref, el] of B.cards) if (ref.startsWith("e") && !refs.has(ref)) { el.remove(); B.cards.delete(ref); }
  st.enemies.forEach((e, i) => {
    let card = B.cards.get(e.ref);
    if (!card) {
      card = enemyCard(e);
      B.cards.set(e.ref, card);
    }
    if (box.children[i] !== card) box.insertBefore(card, box.children[i] || null);
    updateEnemy(card, e);
  });
  renderTargets();
}

function enemyCard(e) {
  const x = {};
  const card = h("div.ecard" + (e.rank === "boss" ? ".boss" : ""),
    { onclick: () => clickEnemy(e.ref), ondblclick: () => { B.target = e.ref; confirmArmed(); } },
    x.nm = h("div.nm"),
    x.sub = h("div.sub"),
    x.wk = h("div.row", { style: { gap: "3px", marginTop: "5px" } }),
    h("div.bar.ehp", x.ghost = h("i.ghost"), x.hp = h("i")),
    x.hpt = h("div.bartext"),
    x.tb = h("div.bar.tough", x.t = h("i")),
    x.tt = h("div.bartext"),
    x.chips = h("div.chips"),
    x.fx = h("div.fx"));
  card._x = x;
  return card;
}

function updateEnemy(card, e) {
  const x = card._x;
  x.nm.textContent = prettify(e.name);
  x.nm.title = e.name;
  put(x.sub, h("span.tag", RANK_CN[e.rank] || e.rank), `Lv.${e.level}`, h("span.right.mono", e.alive ? `行动值 ${e.av ?? "–"}` : "已击败"));
  put(x.wk, ...e.weaknesses.map((w) => h("span.elchip", { style: { "--c": elColor(w), width: "18px", height: "18px", fontSize: "10px" }, title: `${EL_CN[w]}弱点` }, EL_SHORT[w])));
  const hpP = e.max_hp ? Math.max(0, e.hp / e.max_hp) * 100 : 0;
  x.hp.style.width = hpP + "%";
  x.ghost.style.width = hpP + "%";
  put(x.hpt, h("span", fmtInt(Math.max(0, e.hp))), h("span", fmt(e.max_hp)));
  const tP = e.max_toughness ? (e.toughness / e.max_toughness) * 100 : 0;
  x.t.style.width = (e.broken ? 0 : tP) + "%";
  x.tb.classList.toggle("broken", e.broken);
  put(x.tt, e.broken ? h("span.broken-tag", "弱点击破") : h("span", `韧性 ${e.toughness.toFixed(0)} / ${e.max_toughness.toFixed(0)}`), h("span", e.shield ? `护盾 ${fmtInt(e.shield)}` : ""));
  put(x.chips, ...modChips(e.mods));
  card.classList.toggle("dead", !e.alive || e.hp <= 0);
  card.classList.toggle("acting", B.state.point?.actor === e.ref || (B.state.point?.where === "before_turn" && B.state.point?.subject === e.ref));
}

function modChips(mods, max = 8) {
  const shown = mods.filter((m) => !m.hidden || store.prefs.showHidden);
  const out = shown.slice(0, max).map((m) => {
    const cls = m.tags.includes("dot") ? "dot" : m.kind === "debuff" ? "debuff" : m.kind === "buff" ? "buff" : "";
    const stats = Object.entries(m.stats).map(([k, v]) => `${k} ${Math.abs(v) < 5 ? pct(v) : fmtInt(v)}`).join("\n");
    return h("span.chip" + (cls ? "." + cls : ""), { title: `${tr(m.name)}${m.stacks > 1 ? " ×" + m.stacks : ""}${m.duration != null ? `（剩余 ${m.duration} 回合）` : ""}\n来源：${m.source || "–"}${stats ? "\n" + stats : ""}` },
      tr(m.name), m.stacks > 1 ? h("b", "×" + m.stacks) : null, m.duration != null ? h("b", m.duration) : null);
  });
  if (shown.length > max) out.push(h("span.chip", `+${shown.length - max}`));
  return out;
}

function clickEnemy(ref) {
  const e = B.state.enemies.find((x) => x.ref === ref);
  if (!e || !e.alive) return;
  const k = armedKind();
  if (B.target === ref && k && (k.target === "enemy" || k.target === "enemies")) return confirmArmed();
  B.target = ref;
  B.detail = ref;
  renderTargets();
  if (B.tab === "detail") renderPanel();
}

function renderTargets() {
  const st = B.state;
  if (!st) return;
  const k = armedKind() || (st.point?.kind === "turn" ? { target: "enemy", shape: "" } : null);
  const es = st.enemies;
  const ti = es.findIndex((e) => e.ref === B.target);
  for (const e of es) {
    const card = B.cards.get(e.ref);
    if (!card) continue;
    const i = es.indexOf(e);
    const enemyAim = k && (k.target === "enemy" || k.target === "enemies");
    card.classList.toggle("sel", !!enemyAim && e.ref === B.target && e.alive);
    card.classList.toggle("adj", !!enemyAim && k.target === "enemy" && k.shape === "Blast" && Math.abs(i - ti) === 1 && e.alive);
    card.classList.toggle("hit-all", !!k && (k.target === "enemies" || k.shape === "AoEAttack") && e.alive);
  }
  for (const a of st.allies) {
    const card = B.cards.get(a.ref);
    if (!card) continue;
    card.classList.toggle("allysel", !!k && k.target === "ally" && a.ref === B.allyTarget);
    card.classList.toggle("team-hl", !!k && k.target === "allies");
  }
}

// allies
function renderAllies() {
  const box = document.getElementById("allies");
  const st = B.state;
  st.allies.forEach((a, i) => {
    let card = B.cards.get(a.ref);
    if (!card) {
      card = allyCard(a);
      B.cards.set(a.ref, card);
    }
    if (box.children[i] !== card) box.insertBefore(card, box.children[i] || null);
    updateAlly(card, a, i);
  });
  renderTargets();
}

function allyCard(a) {
  const x = {};
  const card = h("div.acard", { style: { "--c": elColor(a.element) }, onclick: (ev) => { if (!ev.target.closest(".ult")) clickAlly(a.ref); } },
    x.ult = h("button.ult", { onclick: () => pressUlt(a.ref) }, x.ultk = h("span")),
    x.nm = h("div.nm", { style: { paddingRight: "50px" } }),
    x.sub = h("div.sub"),
    h("div.bar.hp", x.hp = h("i")),
    x.hpt = h("div.bartext"),
    h("div.bar.en", { style: { height: "5px" } }, x.en = h("i")),
    x.ent = h("div.bartext"),
    x.ela = h("div.ela"),
    x.chips = h("div.chips"),
    x.kit = h("div.kit"),
    x.summ = h("div.summons"),
    x.fx = h("div.fx"));
  card._x = x;
  return card;
}

function updateAlly(card, a, i) {
  const x = card._x;
  const c = charOf(a.id);
  x.nm.textContent = unitName(a);
  put(x.sub, h("span", `${EL_CN[a.element] || ""} · ${PATH_CN[a.path] || ""}`), h("span.tag", "E" + a.eidolon), a.enhanced ? h("span.tag", "强化") : null);
  x.hp.style.width = (a.max_hp ? (a.hp / a.max_hp) * 100 : 0) + "%";
  put(x.hpt, h("span", `${fmtInt(a.hp)} / ${fmtInt(a.max_hp)}`), h("span", a.shield ? `护盾 ${fmtInt(a.shield)}` : ""));
  const res = a.ult_res || { cur: a.energy, max: a.max_energy, label: "能量" };
  const p = res.max ? Math.min(100, (res.cur / res.max) * 100) : 0;
  x.en.style.width = p + "%";
  put(x.ent, h("span", `${res.label} ${+res.cur.toFixed(1)}/${+res.max.toFixed(1)}`), h("span", a.on_timeline ? `行动值 ${a.av ?? "–"}` : "离场"));
  x.ult.style.setProperty("--p", a.ult_ready ? 100 : p);
  x.ult.classList.toggle("ready", !!a.ult_ready);
  x.ult.classList.toggle("armed", B.armed?.type === "ult" && B.armed.who === a.ref);
  x.ult.classList.toggle("auto", !!store.settings.auto_ult?.[a.ref]);
  x.ult.title = `${nameOfUlt(a)}（${i + 1}）${a.ult_ready ? "：可释放" : ""}\n\n${DESC.get(a.ult_name) || ""}`;
  x.ultk.textContent = a.ult_ready ? String(i + 1) : Math.floor(p) + "%";
  put(x.ela, ...elationLine(a.elation));
  x.ela.style.display = a.elation ? "" : "none";
  x.ela.title = a.elation ? elationTitle(a.elation) : "";
  put(x.chips, ...modChips(a.mods, 6));
  const kit = Object.entries(a.kit || {}).filter(([k, v]) => typeof v !== "boolean" || v).slice(0, 4);
  x.kit.textContent = kit.map(([k, v]) => `${k}: ${typeof v === "number" ? +v.toFixed(2) : v}`).join(" · ");
  x.kit.title = Object.entries(a.kit || {}).map(([k, v]) => `${k}: ${v}`).join("\n");
  const sums = B.state.summons.filter((s) => s.owner === a.ref);
  put(x.summ, ...sums.map((s) => h("span.chip", { title: `${s.name}\n生命 ${fmtInt(s.hp)} / ${fmtInt(s.max_hp)}\n行动值 ${s.av ?? "–"}`, onclick: (ev) => { ev.stopPropagation(); showDetail(s.ref); } },
    s.name, s.max_hp ? h("b", fmt(s.hp)) : null, s.on_timeline && s.av != null ? h("b", "⏱" + s.av) : null)));
  const p0 = B.state.point;
  card.classList.toggle("turn", !!p0 && p0.kind === "turn" && (p0.actor === a.ref || sums.some((s) => s.ref === p0.actor)));
  card.classList.toggle("acting", !!p0 && p0.where === "before_turn" && p0.subject === a.ref);
  card.style.opacity = a.alive ? "" : "0.4";
}

function elationLine(e) {
  if (!e) return [];
  return [
    h("span", "欢愉度 ", h("b", pct(e.elation))),
    h("span", "好活当赏 ", h("b", String(e.banger))),
    e.merrymake ? h("span", "增笑 ", h("b", pct(e.merrymake))) : null,
  ];
}

function bangerStacks(e) {
  return e.banger_stacks.map((s) => `${+s.p.toFixed(1)} 点${s.turns == null ? "（常驻）" : `（剩余 ${s.turns} 回合）`}`);
}

function elationTitle(e) {
  const stacks = bangerStacks(e);
  return `欢愉度 ${pct(e.elation)}：提高欢愉伤害\n增笑 ${pct(e.merrymake)}：欢愉伤害额外提高\n好活当赏 ${e.banger} 点` + (stacks.length ? "\n" + stacks.map((s) => "  · " + s).join("\n") : "");
}

function clickAlly(ref) {
  const k = armedKind();
  if (k && k.target === "ally") {
    if (B.allyTarget === ref) return confirmArmed();
    B.allyTarget = ref;
    renderTargets();
    return;
  }
  showDetail(ref);
}

function showDetail(ref) {
  B.detail = ref;
  B.tab = "detail";
  renderPanel();
}

function nameOfUlt(a) {
  return store.prefs.lang === "cn" ? a.ult_name_cn || a.ult_name : a.ult_name;
}

function unitByRef(ref) {
  const st = B.state;
  return st.allies.find((x) => x.ref === ref) || st.enemies.find((x) => x.ref === ref) || st.summons.find((x) => x.ref === ref);
}

function unitName(u) {
  if (!u) return "";
  if (u.kind === "char") return nameOf(charOf(u.id) || u);
  return prettify(u.name);
}

/** Datamined enemy names are internal ids ("W4_Claymore_02"): show them with spaces. */
function prettify(name) {
  return String(name || "").replace(/_/g, " ");
}

function actLabel(e) {
  return store.prefs.lang === "cn" ? e.label_cn || tr(e.label) : e.label;
}

function displayName(name) {
  const a = B.state?.allies.find((x) => x.name === name);
  return a ? unitName(a) : prettify(tr(name));
}

// prompt + actions
function renderPrompt() {
  const box = document.getElementById("prompt");
  const st = B.state;
  const p = st.point;
  box.className = "prompt";
  clear(box);
  if (st.fatal) {
    box.classList.add("err");
    box.append(h("div.title", "出错了"), h("div.hint", "撤销后可重试"), h("button.btn.right", { onclick: undo }, "↶ 撤销"));
    return;
  }
  if (!p) {
    box.classList.add("done");
    box.append(h("div.col", { style: { gap: "0" } }, h("div.title", st.cleared ? `战斗胜利 · 第 ${shownCycle(st)} 轮清场` : "战斗结束（达到轮次上限）"),
      h("div.hint", `总伤害 ${fmtInt(st.total)} · 行动值 ${st.time.toFixed(1)}`)),
      h("div.right.row", h("button.btn", { onclick: undo }, "↶ 撤销"), h("button.btn", { onclick: showResult }, "结算"), h("button.btn", { onclick: B.onExit }, "返回配置")));
    return;
  }
  const armedTxt = B.armed ? armedText() : "";
  if (p.kind === "turn") {
    const who = unitByRef(p.actor);
    box.append(
      h("div.col", { style: { gap: "0" } },
        h("div.title", `${unitName(who) || p.actor_name} 的${p.extra_turn ? "额外" : ""}回合`),
        h("div.hint", armedTxt || "Q 普攻 · E 战技 · 1–4 终结技 · ←/→ 选目标 · 再按一次或空格确认"),
        B.state.ult_locked ? h("div.hint", lockedText()) : null),
    );
  } else {
    box.classList.add("window");
    const subj = p.subject ? unitByRef(p.subject) : null;
    const title = p.where === "before_turn"
      ? `即将轮到 ${unitName(subj) || p.subject_name || "?"}${p.subject_side === "enemy" ? "（敌方）" : ""} 行动`
      : p.where === "after_action" ? `${unitName(subj) || p.subject_name || "?"} 行动完毕，回合尚未结束`
      : p.where === "queue" ? `插入行动队列：${(p.queued || []).join("、") || "…"}` : "行动进行中";
    box.append(h("div.col", { style: { gap: "0" } }, h("div.title", title), h("div.hint", armedTxt || "可插入终结技（1–4），或按空格继续")),
      h("button.btn.right", { onclick: () => decide({ kind: "continue" }) }, "继续 ", h("kbd", "空格")));
  }
}

function lockedText() {
  const queued = (B.state.deferred_ults || []).map((r) => unitName(unitByRef(r)) || r);
  return "终结技插入的额外回合中：此时释放的终结技会在额外回合结束后施放" + (queued.length ? `（已排队：${queued.join("、")}）` : "");
}

function armedText() {
  const st = B.state;
  if (B.armed.type === "ult") {
    const a = st.allies.find((x) => x.ref === B.armed.who);
    return `已选择：${unitName(a)} 的终结技「${nameOfUlt(a)}」${aimText(a.ult_target)} — 再按 ${st.allies.indexOf(a) + 1} 或空格释放，Esc 取消`;
  }
  const it = currentMenu().find((m) => m.id === B.armed.item);
  return it ? `已选择：${label(it)}${aimText(it.target)} — 再按一次或空格确认，Esc 取消` : "";
}

function aimText(kind) {
  if (kind === "enemy") return ` → ${prettify(unitByRef(B.target)?.name) || "目标"}`;
  if (kind === "enemies") return " → 全体敌人";
  if (kind === "ally") return ` → ${unitName(unitByRef(B.allyTarget)) || "我方"}`;
  if (kind === "allies") return " → 我方全体";
  return "";
}

function renderActions() {
  const box = clear(document.getElementById("actions"));
  const p = B.state.point;
  if (!p || p.kind !== "turn") {
    if (p) box.appendChild(h("div.muted", { style: { alignSelf: "center" } }, "等待插入时机 · 已就绪的终结技可随时释放"));
    return;
  }
  const menu = p.menu || [];
  menu.forEach((it, i) => {
    const key = hotkeyOf(it, i, menu);
    const armed = B.armed?.type === "act" && B.armed.item === it.id;
    const desc = DESC.get(it.label) || "";
    box.appendChild(h("button.act" + (armed ? ".armed" : ""), { disabled: !it.enabled, title: [it.note, desc].filter(Boolean).join("\n\n"), onclick: () => pressItem(it) },
      h("span.key", key.toUpperCase() || "·"),
      h("span.col", { style: { gap: "0" } }, h("span.t1", label(it)), h("span.t2", `${KIND_CN[it.kind] || "行动"} · ${targetText(it.target, it.shape)}${it.ends_turn ? "" : " · 不结束回合"}`)),
      it.sp ? h("span.sp." + (it.sp > 0 ? "plus" : "minus"), `${it.sp > 0 ? "+" : ""}${it.sp} 点`) : null));
  });
  box.appendChild(h("button.btn.small", { style: { alignSelf: "center" }, title: "让套件的自动策略决定这一步 (X)", onclick: () => auto("once") }, "自动 ", h("kbd", "X")));
}

function targetText(kind, shape) {
  if (shape === "Blast") return "扩散";
  if (shape === "Bounce") return "弹射";
  return { enemy: "单体", enemies: "群攻", ally: "单体我方", allies: "我方全体", self: "自身" }[kind] || "";
}

// ticker + floaters
function ultFlash(entries) {
  const ults = entries.filter((e) => e.t === "action" && e.kind === "ult");
  ults.forEach((e, i) => setTimeout(() => {
    const el = h("div.ultflash", h("small", `${displayName(e.actor)} · 终结技`), actLabel(e));
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 950);
  }, i * 500));
}

function animate(entries) {
  if (store.prefs.anim !== false) ultFlash(entries);
  let lastAction = null;
  const lines = [];
  const perCard = new Map();
  for (const e of entries) {
    if (e.t === "action") {
      lastAction = { e, dmg: 0 };
      lines.push(lastAction);
    } else if (e.t === "dmg") {
      if (lastAction) lastAction.dmg += e.amount;
      else lines.push({ e: { t: "dot", label: e.label, actor: displayName(e.owner), target: e.target }, dmg: e.amount });
      queueFloat(perCard, e.tref, e.amount, e.crit ? "crit" : e.tags.includes("dot") ? "dot" : "", fmt(e.amount));
    } else if (e.t === "break") {
      queueFloat(perCard, e.tref, 0, "brk", "击破");
      lines.push({ e });
    } else if (e.t === "kill") {
      queueFloat(perCard, e.tref, 0, "kill", "击败");
    } else if (e.t === "heal") {
      queueFloat(perCard, e.tref, e.amount, "heal", "+" + fmt(e.amount));
    } else if (e.t === "wave") {
      lines.push({ e });
    }
  }
  for (const l of lines) B.ticker.push(tickerText(l));
  B.ticker = B.ticker.slice(-6);
  renderTicker();
  if (!store.prefs.anim) return;
  for (const [ref, list] of perCard) {
    const card = B.cards.get(ref);
    if (!card) continue;
    const shown = list.slice(0, 9);
    const rest = list.slice(9).reduce((a, x) => a + x.amount, 0);
    if (rest > 0) shown.push({ cls: "", text: "…+" + fmt(rest) });
    shown.forEach((f, i) => setTimeout(() => {
      const el = h("div.float" + (f.cls ? "." + f.cls : ""), { style: { left: `${50 + ((i % 3) - 1) * 18}%`, top: `${22 + (i % 4) * 9}%` } }, f.text);
      card._x.fx.appendChild(el);
      setTimeout(() => el.remove(), 1300);
      if (f.cls !== "heal" && f.amount > 0) {
        card.classList.remove("shake");
        void card.offsetWidth;
        card.classList.add("shake");
      }
    }, i * 90));
  }
}

function queueFloat(map, ref, amount, cls, text) {
  if (!ref) return;
  if (!map.has(ref)) map.set(ref, []);
  map.get(ref).push({ amount, cls, text });
}

function tickerText(l) {
  const e = l.e;
  if (e.t === "action") {
    const kind = KIND_CN[e.kind] || e.kind;
    return h("div", h("b", displayName(e.actor)), ` ${kind}「${actLabel(e)}」`, e.target ? ` → ${displayName(e.target)}` : "", l.dmg ? h("span.gold", `  ${fmtInt(l.dmg)}`) : "");
  }
  if (e.t === "dot") return h("div", h("b", e.actor || ""), ` ${tr(e.label)} → ${prettify(e.target)}`, h("span.gold", `  ${fmtInt(l.dmg)}`));
  if (e.t === "break") return h("div", "⚡ ", h("b", prettify(e.target)), ` 被 ${displayName(e.by)} 击破（${EL_CN[e.element] || e.element}）`);
  if (e.t === "wave") return h("div.gold", `—— 第 ${e.n} 波 ——`);
  return h("div", "");
}

function renderTicker() {
  const box = document.getElementById("ticker");
  if (!box) return;
  put(box, ...[...B.ticker].reverse());
}

// ==================================================================================== panel
function renderPanel() {
  const panel = document.getElementById("panel");
  if (!panel || !B.state) return;
  panel.querySelectorAll(".ptabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === B.tab));
  const body = clear(document.getElementById("pbody"));
  if (B.tab === "log") body.appendChild(logView());
  else if (B.tab === "stats") body.appendChild(statsView());
  else if (B.tab === "detail") body.appendChild(detailView());
  else body.appendChild(settingsView());
  if (B.tab === "log") body.scrollTop = body.scrollHeight;
}

function logView() {
  const box = h("div.log");
  const groups = [];
  let g = null;
  let act = null;
  for (const e of B.log) {
    if (e.t === "turn" || e.t === "wave") {
      g = { head: e, rows: [] };
      groups.push(g);
      act = null;
      continue;
    }
    if (!g) { g = { head: null, rows: [] }; groups.push(g); }
    if (e.t === "action") { act = { e, dmg: 0, hits: [], extra: [] }; g.rows.push(act); continue; }
    if (e.t === "dmg") {
      if (!act) { act = { e: { t: "action", label: e.label, actor: e.owner, kind: e.tags.includes("dot") ? "dot" : "other", i: e.i }, dmg: 0, hits: [], extra: [] }; g.rows.push(act); }
      act.dmg += e.amount;
      act.hits.push(e);
      continue;
    }
    if (e.t === "ult") continue;
    (act ? act.extra : g.rows).push(e.t === "mod" || e.t === "break" || e.t === "kill" || e.t === "heal" ? { line: e } : { line: e });
  }
  for (const grp of groups.slice(-60)) {
    const gh = grp.head;
    const div = h("div.grp");
    if (gh?.t === "turn") {
      const side = gh.who?.startsWith("e") ? "enemy" : "ally";
      div.appendChild(h("div.gh." + side, h("span.mono", `C${gh.cycle} · ${gh.time.toFixed(1)}`), h("b", displayName(gh.name)), gh.extra ? "额外回合" : "回合"));
    } else if (gh?.t === "wave") div.appendChild(h("div.gh", h("b.gold", `第 ${gh.n} 波`)));
    for (const r of grp.rows) {
      if (r.line) { div.appendChild(logLine(r.line)); continue; }
      const e = r.e;
      const id = e.i;
      const open = B.open.has(id);
      const cls = e.kind === "ult" ? ".ult" : e.kind === "fua" ? ".fua" : e.kind === "enemy" ? ".enemy" : "";
      const row = h("div.ac" + cls, { onclick: () => { if (open) B.open.delete(id); else B.open.add(id); renderPanel(); } },
        h("div.l1", h("span", open ? "▾" : "▸"), h("b", displayName(e.actor || "")), h("span.muted", `${KIND_CN[e.kind] || ""}「${actLabel(e)}」${e.target ? " → " + displayName(e.target) : ""}`), r.dmg ? h("span.tot", fmtInt(r.dmg)) : null));
      div.appendChild(row);
      if (open) {
        for (const hit of r.hits) {
          div.appendChild(h("div.ln" + (hit.crit ? ".crit" : ""), h("span", `${prettify(hit.target)}${hit.label !== e.label ? " · " + tr(hit.label) : ""}`), hit.crit ? "暴击" : "", hit.tough ? h("span.dim", `削韧 ${hit.tough}`) : null, h("span.amt", fmtInt(hit.amount))));
          if (hit.parts) div.appendChild(h("div.parts", Object.entries(hit.parts).filter(([k, v]) => k === "base" || Math.abs(v - 1) > 1e-6).map(([k, v]) => `${PART_CN[k] || k} ${k === "base" ? fmtInt(v) : "×" + v.toFixed(3)}`).join("  ")));
        }
        for (const x of r.extra) div.appendChild(logLine(x.line));
      }
    }
    box.appendChild(div);
  }
  if (!groups.length) box.appendChild(h("div.muted", "还没有记录"));
  return box;
}

function logLine(e) {
  if (e.t === "break") return h("div.ln.brk", `⚡ ${prettify(e.target)} 弱点击破（${EL_CN[e.element] || e.element}）`);
  if (e.t === "kill") return h("div.ln.brk", `✖ ${prettify(e.target)} 被击败`);
  if (e.t === "heal") return h("div.ln.heal", h("span", `${displayName(e.target)} 回复`), h("span.amt", "+" + fmtInt(e.amount)));
  if (e.t === "mod") return h("div.ln", h("span", `${e.kind === "debuff" ? "▼" : "▲"} ${displayName(e.target)}：${tr(e.name)}${e.stacks > 1 ? " ×" + e.stacks : ""}${e.duration != null ? `（${e.duration} 回合）` : ""}`));
  return h("div.ln", JSON.stringify(e));
}

function statsView() {
  const st = B.state;
  const box = h("div.col", { style: { gap: "12px" } });
  const total = st.total || 1;
  box.appendChild(h("div.row", h("div.col", { style: { gap: 0 } }, h("span.label", "总伤害"), h("b.gold", { style: { fontSize: "20px" } }, fmtInt(st.total))),
    h("div.col.right", { style: { gap: 0, textAlign: "right" } }, h("span.label", "每行动值"), h("b", st.time ? fmtInt(st.total / st.time) : "–"))));
  const owners = Object.entries(st.by_owner).sort((a, b) => b[1] - a[1]);
  for (const [name, v] of owners) {
    const a = st.allies.find((x) => x.name === name);
    box.appendChild(h("div.dmgbar", { style: { "--c": a ? elColor(a.element) : "var(--gold)" } }, h("span", displayName(name)), h("div.b", h("i", { style: { width: (v / total) * 100 + "%" } })), h("span.n", `${fmt(v)} · ${pct(v / total, 0)}`)));
  }
  const src = new Map();
  for (const e of B.log) if (e.t === "dmg") { const k = `${displayName(e.owner)} · ${tr(e.label)}`; src.set(k, (src.get(k) || 0) + e.amount); }
  const tbl = h("table.kvtable");
  [...src.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).forEach(([k, v]) => tbl.appendChild(h("tr", h("td", k), h("td", fmtInt(v)))));
  box.appendChild(h("div", h("h4", "按来源"), tbl));
  return box;
}

function detailView() {
  const u = B.detail ? unitByRef(B.detail) : null;
  if (!u) return h("div.muted", "点击任意单位（敌人、角色卡片、行动顺序）查看详情");
  const box = h("div.col", { style: { gap: "10px" } });
  box.appendChild(h("div", h("b", { style: { fontSize: "15px" } }, unitName(u)), " ", h("span.muted", u.kind === "enemy" ? `${RANK_CN[u.rank] || ""} Lv.${u.level}` : u.kind === "summon" ? "召唤物 / 忆灵" : `E${u.eidolon} · ${PATH_CN[u.path] || ""}`)));
  const tbl = h("table.kvtable");
  const row = (k, v) => tbl.appendChild(h("tr", h("td", k), h("td", v)));
  row("生命值", `${fmtInt(u.hp)} / ${fmtInt(u.max_hp)}`);
  row("速度", u.spd.toFixed(1));
  row("行动值", u.av ?? "–");
  if (u.kind === "char") {
    row("能量", `${u.energy.toFixed(1)} / ${u.max_energy}`);
    for (const [k, v] of Object.entries(u.stats || {})) row(statLabel(k), statValue(k, v));
    if (u.elation) {
      if (!("Elation" in (u.stats || {}))) row("欢愉度", pct(u.elation.elation));
      row("增笑", pct(u.elation.merrymake));
      row("好活当赏", `${u.elation.banger} 点`);
      for (const s of bangerStacks(u.elation)) row("", s);
    }
  }
  if (u.kind === "aha" && B.state.elation) {
    const el = B.state.elation;
    row("笑点", String(el.punchline));
    row("欢愉角色", `${el.chars} 名`);
    row("已发动阿哈时刻", `${el.instants} 次`);
  }
  if (u.kind === "enemy") {
    row("韧性", `${u.toughness.toFixed(1)} / ${u.max_toughness}${u.broken ? "（击破）" : ""}`);
    row("效果抵抗", pct(u.effect_res));
    for (const [el, r] of Object.entries(u.res || {})) row(`${EL_CN[el] || el}抗性`, pct(r, 0));
  }
  box.appendChild(tbl);
  if (u.kit && Object.keys(u.kit).length) {
    const kt = h("table.kvtable");
    for (const [k, v] of Object.entries(u.kit)) kt.appendChild(h("tr", h("td", k), h("td", String(v))));
    box.appendChild(h("div", h("h4", "套件状态"), kt));
  }
  const mods = u.mods.filter((m) => !m.hidden || store.prefs.showHidden);
  box.appendChild(h("div", h("div.row", h("h4", `状态效果（${mods.length}）`), h("label.switch.right.label", h("input", { type: "checkbox", checked: store.prefs.showHidden, onchange: (e) => { store.prefs.showHidden = e.target.checked; savePrefs(); render(); } }), "显示常驻/隐藏效果")),
    mods.map((m) => h("div.modrow", h("div", h("b", tr(m.name)), m.stacks > 1 ? ` ×${m.stacks}` : "", h("span.muted", `  ${m.kind === "debuff" ? "减益" : m.kind === "buff" ? "增益" : "其他"}${m.duration != null ? ` · 剩余 ${m.duration} 回合` : ""}${m.source ? " · 来源 " + displayName(m.source) : ""}`)),
      Object.keys(m.stats).length ? h("div.st", Object.entries(m.stats).map(([k, v]) => `${k} ${Math.abs(v) < 5 ? pct(v) : fmtInt(v)}`).join("  ")) : null))));
  return box;
}

function settingsView() {
  const st = B.state;
  const s = store.settings;
  const box = h("div.col", { style: { gap: "14px" } });
  box.appendChild(h("div", h("h4", "自动释放终结技"), h("div.muted", { style: { fontSize: "12px", marginBottom: "6px" } }, "勾选的角色能量满时按套件策略自动释放，不再暂停询问。"),
    st.allies.map((a) => h("label.switch", { style: { display: "flex", margin: "4px 0" } }, h("input", { type: "checkbox", checked: !!s.auto_ult?.[a.ref], onchange: (e) => { s.auto_ult = Object.assign({}, s.auto_ult, { [a.ref]: e.target.checked }); saveSettings(); renderAllies(); } }), unitName(a)))));
  const P = [["before_enemy", "敌方行动前"], ["before_ally", "我方行动前（回合开始前）"], ["after_action", "我方行动后（回合结束前）"], ["queue", "追加攻击 / 插入行动之间"], ["mid_action", "不结束回合的行动中途"]];
  box.appendChild(h("div", h("h4", "终结技插入时机（有终结技就绪时在这些时机暂停）"),
    P.map(([k, t]) => h("label.switch", { style: { display: "flex", margin: "4px 0" } }, h("input", { type: "checkbox", checked: !!s.pause?.[k], onchange: (e) => { s.pause = Object.assign({}, s.pause, { [k]: e.target.checked }); saveSettings(); } }), t)),
    h("div.dim", { style: { fontSize: "11.5px" } }, "我方回合中始终可以用 1–4 先释放终结技再行动。")));
  box.appendChild(h("div", h("h4", "操作"),
    h("label.switch", { style: { display: "flex", margin: "4px 0" } }, h("input", { type: "checkbox", checked: !!store.prefs.quick, onchange: (e) => { store.prefs.quick = e.target.checked; savePrefs(); } }), "单击直接释放（不需要再按一次确认）"),
    h("label.switch", { style: { display: "flex", margin: "4px 0" } }, h("input", { type: "checkbox", checked: store.prefs.anim !== false, onchange: (e) => { store.prefs.anim = e.target.checked; savePrefs(); } }), "伤害数字动画")));
  box.appendChild(h("div.dim", { style: { fontSize: "12px", lineHeight: 1.7 } },
    h("h4", "快捷键"),
    "Q / E（/ R F G T）选择行动，再按一次或空格确认", h("br"),
    "1–4 终结技（任意暂停时机都可插入）", h("br"),
    "← → 或 A D 切换目标；点击敌人/角色也可以选中，双击直接执行", h("br"),
    "空格 继续 · Esc 取消选择 · Z 撤销 · X 自动一步 · Shift+X 自动到我方回合 · C 自动到下一轮"));
  return box;
}

function showResult() {
  const st = B.state;
  if (!st || st.point) return;
  const owners = Object.entries(st.by_owner).sort((a, b) => b[1] - a[1]);
  const body = h("div",
    h("div.result-grid",
      h("div", h("div.label", "结果"), h("div.big", st.cleared ? "清场" : "未清场")),
      h("div", h("div.label", "轮次"), h("div.big", String(shownCycle(st)))),
      h("div", h("div.label", "总伤害"), h("div.big", fmt(st.total)))),
    owners.map(([n, v]) => h("div.dmgbar", { style: { "--c": elColor(st.allies.find((a) => a.name === n)?.element) } }, h("span", displayName(n)), h("div.b", h("i", { style: { width: (v / (st.total || 1)) * 100 + "%" } })), h("span.n", fmt(v)))));
  modal("战斗结算", body, [["↶ 撤销最后一步", undo], ["⟲ 重新开始", () => startBattle(B.root, B.onExit)], ["返回配置", B.onExit, "primary"]]);
}
