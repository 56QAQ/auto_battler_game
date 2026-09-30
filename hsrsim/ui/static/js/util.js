// Small helpers shared by the views.

/** h("div.card#id", {onclick, style, ...attrs}, ...children) */
export function h(sel, attrs, ...kids) {
  const m = sel.match(/^([a-z0-9]+)?((?:[.#][\w-]+)*)$/i);
  const el = document.createElement((m && m[1]) || "div");
  if (m && m[2]) {
    for (const part of m[2].match(/[.#][\w-]+/g)) {
      if (part[0] === ".") el.classList.add(part.slice(1));
      else el.id = part.slice(1);
    }
  }
  if (attrs && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    kids.unshift(attrs);
    attrs = null;
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith("--")) el.style.setProperty(sk, sv);
        else el.style[sk] = sv;
      }
    }
    else if (k === "class") el.className += " " + v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k in el && k !== "list") {
      try { el[k] = v; } catch { el.setAttribute(k, v); }
    } else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}

function append(el, kids) {
  for (const k of kids) {
    if (k === null || k === undefined || k === false) continue;
    if (Array.isArray(k)) append(el, k);
    else el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}

/** Replace an element's children, skipping null/false (Element.append would print "null"). */
export function put(el, ...kids) {
  clear(el);
  append(el, kids);
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function fmt(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e4) return (n / 1e3).toFixed(1) + "K";
  return Math.round(n).toLocaleString("en-US");
}
export const fmtInt = (n) => Math.round(n).toLocaleString("en-US");
export const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";

export const ELEMENTS = ["Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"];
export const EL_CN = { Physical: "物理", Fire: "火", Ice: "冰", Thunder: "雷", Wind: "风", Quantum: "量子", Imaginary: "虚数" };
export const EL_SHORT = { Physical: "物", Fire: "火", Ice: "冰", Thunder: "雷", Wind: "风", Quantum: "量", Imaginary: "虚" };
export const PATH_CN = {
  Warrior: "毁灭", Rogue: "巡猎", Mage: "智识", Shaman: "同谐", Warlock: "虚无", Knight: "存护", Priest: "丰饶",
  Memory: "记忆", Elation: "欢愉",
};
export const PATH_EN = {
  Warrior: "Destruction", Rogue: "The Hunt", Mage: "Erudition", Shaman: "Harmony", Warlock: "Nihility",
  Knight: "Preservation", Priest: "Abundance", Memory: "Remembrance", Elation: "Elation",
};
export const RANK_CN = { normal: "普通", elite: "精英", boss: "首领" };
export const elColor = (el) => `var(--el-${el || "Physical"})`;

export const STAT_CN = {
  HP: "生命值", ATK: "攻击力", DEF: "防御力", SPD: "速度", "CRIT Rate": "暴击率", "CRIT DMG": "暴击伤害",
  "Break Effect": "击破特攻", "Energy Regen": "能量恢复效率", "Effect Hit Rate": "效果命中", "Effect RES": "效果抵抗",
  "Break Efficiency": "削韧效率", "Outgoing Healing": "治疗量加成", "All-Type DMG": "全属性伤害",
};
export const PCT_STATS = new Set([
  "CRIT Rate", "CRIT DMG", "Break Effect", "Energy Regen", "Effect Hit Rate", "Effect RES", "Break Efficiency",
  "Outgoing Healing", "All-Type DMG",
]);
export function statLabel(k) {
  if (STAT_CN[k]) return STAT_CN[k];
  const m = k.match(/^(\w+) DMG$/);
  if (m && EL_CN[m[1]]) return EL_CN[m[1]] + "属性伤害";
  return k;
}
export function statValue(k, v) {
  if (PCT_STATS.has(k) || / DMG$/.test(k)) return pct(v);
  return fmtInt(v);
}

export const KIND_CN = {
  basic: "普攻", skill: "战技", ult: "终结技", fua: "追加攻击", memosprite: "忆灵", extra: "额外", enemy: "敌方",
  elation: "欢愉技",
};
export const PART_CN = {
  base: "基础", dmg_boost: "增伤", def_mult: "防御", res_mult: "抗性", vuln_mult: "易伤", mitig_mult: "减伤",
  broken_mult: "韧性", weaken_mult: "虚弱", crit_mult: "暴击", extra_mult: "最终",
};

export function debounce(fn, ms) {
  let t = null;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

export function toast(msg, ok = false) {
  const box = document.getElementById("toasts");
  for (const t of box.children) if (t.textContent === msg) { t.remove(); }
  while (box.children.length >= 3) box.firstChild.remove();
  const t = h("div.toast" + (ok ? ".ok" : ""), msg);
  box.appendChild(t);
  setTimeout(() => t.remove(), ok ? 1800 : 3200);
}

export function modal(title, body, buttons = []) {
  const bg = h("div.modal-bg");
  const close = () => bg.remove();
  const box = h(
    "div.modal",
    h("h3", { style: { marginTop: 0, color: "var(--gold)" } }, title),
    body,
    h(
      "div.row",
      { style: { justifyContent: "flex-end", marginTop: "14px" } },
      buttons.map(([label, fn, cls]) => h("button.btn" + (cls ? "." + cls : ""), { onclick: () => { close(); fn && fn(); } }, label)),
      h("button.btn.ghost", { onclick: close }, "关闭"),
    ),
  );
  bg.appendChild(box);
  bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
  document.body.appendChild(bg);
  return close;
}

/** Searchable select. items: [{value, label, sub, color, search}] */
export function picker({ items, value, onPick, placeholder = "搜索…", allowNone = false, noneLabel = "（无）" }) {
  const wrap = h("div.picker");
  const cur = items.find((i) => i.value === value);
  const input = h("input", { type: "text", placeholder, value: cur ? cur.label : "" });
  let menu = null;
  let hi = 0;
  let shown = [];
  const close = () => { if (menu) { menu.remove(); menu = null; } };
  const choose = (it) => {
    input.value = it ? it.label : "";
    close();
    onPick(it ? it.value : null);
  };
  const render = () => {
    const q = input.value.trim().toLowerCase();
    shown = items.filter((i) => !q || (i.search || i.label).toLowerCase().includes(q)).slice(0, 80);
    if (allowNone && !q) shown.unshift({ value: null, label: noneLabel, sub: "" });
    if (!menu) {
      menu = h("div.menu");
      wrap.appendChild(menu);
    }
    clear(menu);
    shown.forEach((it, i) => {
      menu.appendChild(
        h(
          "div.opt" + (i === hi ? ".hi" : ""),
          { onmousedown: (e) => { e.preventDefault(); choose(it.value === null ? null : it); } },
          it.color ? h("span.el", { style: { "--c": it.color } }) : null,
          h("span", it.label),
          it.sub ? h("span.sub", it.sub) : null,
        ),
      );
    });
  };
  input.addEventListener("focus", () => { input.select(); hi = 0; render(); });
  input.addEventListener("input", () => { hi = 0; render(); });
  input.addEventListener("blur", () => {
    setTimeout(close, 120);
    const c = items.find((i) => i.value === value);
    if (!input.value.trim() && allowNone) return;
    input.value = c ? c.label : input.value;
  });
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "ArrowDown") { hi = Math.min(hi + 1, shown.length - 1); render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { hi = Math.max(hi - 1, 0); render(); e.preventDefault(); }
    else if (e.key === "Enter" && shown[hi]) { choose(shown[hi].value === null ? null : shown[hi]); input.blur(); }
    else if (e.key === "Escape") { close(); input.blur(); }
  });
  wrap.appendChild(input);
  return wrap;
}

export function stepper(value, onChange, { min = 0, max = 99, step = 1 } = {}) {
  const input = h("input", { type: "text", value: String(value) });
  const set = (v) => {
    v = Math.max(min, Math.min(max, Math.round(v * 10) / 10));
    input.value = String(v);
    onChange(v);
  };
  input.addEventListener("change", () => set(parseFloat(input.value) || 0));
  input.addEventListener("keydown", (e) => e.stopPropagation());
  return h(
    "div.stepper",
    h("button", { type: "button", onclick: () => set((parseFloat(input.value) || 0) - step) }, "−"),
    input,
    h("button", { type: "button", onclick: () => set((parseFloat(input.value) || 0) + step) }, "+"),
  );
}

export function seg(options, value, onChange) {
  const box = h("div.seg");
  for (const [v, label] of options) {
    box.appendChild(
      h("button" + (v === value ? ".on" : ""), { type: "button", onclick: () => onChange(v) }, label),
    );
  }
  return box;
}

export function download(name, text) {
  const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "application/json" })), download: name });
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
