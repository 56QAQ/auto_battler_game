// Bootstrap: catalog, top bar, view switching, keyboard routing.
import { api, store, loadCatalog, savePrefs } from "./store.js";
import { h, clear, toast } from "./util.js";
import { mountSetup } from "./setup.js";
import { startBattle, onKey } from "./battle.js";

const app = document.getElementById("app");
const top = document.getElementById("top");

function renderTop() {
  clear(top);
  top.append(
    h("div.brand", "星穹铁道 · 战斗模拟", h("small", `hsrsim · 数据 ${store.catalog?.version || ""}`)),
    h("div.tabs",
      h("button" + (store.view === "setup" ? ".on" : ""), { onclick: () => go("setup") }, "配置"),
      h("button" + (store.view === "battle" ? ".on" : ""), { disabled: !store.battleStarted, onclick: () => store.battleStarted && go("battle") }, "战斗")),
    h("div.row#battle-status", { style: { gap: "8px", display: store.view === "battle" ? "flex" : "none" } }),
    h("div.right.row",
      h("div.seg",
        h("button" + (store.prefs.lang === "cn" ? ".on" : ""), { onclick: () => setLang("cn") }, "中"),
        h("button" + (store.prefs.lang === "en" ? ".on" : ""), { onclick: () => setLang("en") }, "EN"))),
  );
}

function setLang(l) {
  store.prefs.lang = l;
  savePrefs();
  renderTop();
  if (store.view === "setup") mountSetup(setupRoot, begin);
  else document.dispatchEvent(new Event("hsrsim-rerender"));
}

let battleRoot = null;
function go(view) {
  store.view = view;
  renderTop();
  if (view === "setup") {
    if (battleRoot) battleRoot.classList.add("hidden");
    setupRoot.classList.remove("hidden");
    mountSetup(setupRoot, begin);
  } else {
    setupRoot.classList.add("hidden");
    battleRoot.classList.remove("hidden");
    document.dispatchEvent(new Event("hsrsim-rerender"));
  }
}

let setupRoot = null;
function begin() {
  store.battleStarted = true;
  store.view = "battle";
  renderTop();
  setupRoot.classList.add("hidden");
  if (!battleRoot) {
    battleRoot = h("div#battle-root");
    app.appendChild(battleRoot);
  }
  battleRoot.classList.remove("hidden");
  startBattle(battleRoot, () => go("setup"));
}

window.addEventListener("keydown", (e) => {
  if (e.target.matches && e.target.matches("input, select, textarea")) return;
  if (store.view === "battle") onKey(e);
});

(async function boot() {
  try {
    loadCatalog(await api("/api/catalog"));
  } catch (e) {
    app.appendChild(h("div.card", { style: { margin: "40px auto", maxWidth: "600px" } }, h("h3", "无法连接到 hsrsim 服务"), h("div.muted", e.message), h("div.muted", "请用 python -m hsrsim ui 启动。")));
    return;
  }
  // drop characters that no longer exist in the data (old saved configs)
  store.config.team = store.config.team.filter((m) => !m.character || store.chars.has(String(m.character)) || [...store.chars.values()].some((c) => c.name === m.character));
  setupRoot = h("div#setup-root");
  app.appendChild(setupRoot);
  renderTop();
  mountSetup(setupRoot, begin);
  window.addEventListener("error", (ev) => toast("界面错误：" + ev.message));
})();
