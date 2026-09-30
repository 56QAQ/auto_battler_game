# hsrsim — 崩坏：星穹铁道 战斗模拟器

用于**测试各角色在不同场景下的输出能力**的《崩坏：星穹铁道》战斗系统复刻（无美术资源，纯逻辑）。

- 所有数值直接来自客户端解包数据（当前 **4.6.0**），公式层逐项验证，见 [可行性研究报告](docs/RESEARCH.md)。
- 行动值时间轴、战技点/能量、韧性与击破、超击破、DoT、追加攻击、召唤物/忆灵、光环、持续时间语义均按游戏规则实现。
- **全部 98 名角色 + 10 个强化版套件**、170 个光锥条件效果、62 套遗器均已实现；角色逻辑逐个手写（只写逻辑，数字全部读数据），并对照游戏技能脚本（`ConfigAbility`）审校命中拆分、生效时机与参数下标。
- 近似/未建模之处在代码中以 `# approximation:` / `# not modelled:` 注释逐条标出（约 150 处），汇总见 [docs/RESEARCH.md §5](docs/RESEARCH.md)。

## 交互式界面（逐回合手动操作）

```bash
python -m hsrsim ui          # 打开 http://127.0.0.1:8765/ （只用标准库，无需额外依赖）
```

- **配置页**：最多 4 名角色；角色 / 光锥 / 遗器可中英文搜索；星魂、等级、强化版、行迹、主词条、副词条（按次数）、技能等级、
  自动策略选项；右侧实时显示战斗外面板，并可展开技能 / 行迹 / 星魂说明（数值已代入）。
  敌人可选当期混沌回忆 / 虚构叙事 / 末日幻影（真实敌人数据，可"复制到自定义波次"后修改数值）、单体 / 多目标预设或自定义波次。
  方案可保存到浏览器，或导出 JSON（与 `python -m hsrsim run` 通用）。
- **战斗页**：行动顺序、敌人（生命、韧性、弱点、状态）、我方（生命、护盾、终结技充能、状态、召唤物 / 忆灵）、战斗记录（每一击的全部乘区）、
  伤害统计、单位详情。
- **终结技插入**：只要有角色终结技就绪，战斗就会在每个可插入时机停下——敌方行动前、我方行动前（可选）、追加攻击 / 插入行动之间、
  "不结束回合"的行动中途——此时按 `1`–`4` 即可插入；我方回合中也可以先放终结技再行动。可对每个角色设置"自动释放"。
- **操作**（与游戏相同的手感）：`Q` 普攻、`E` 战技（其他行动 `R F G T`），再按一次或 `空格` 确认；`←` `→` 切换目标（点击敌人 / 角色也可，双击直接执行）；
  `Esc` 取消；`Z` 撤销（按相同随机种子重放，结果完全一致）；`X` 自动一步，`Shift+X` 自动到下个我方回合，`C` 自动到下一轮；也可一键自动到战斗结束。

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" pyyaml
python -m hsrsim run examples/acheron_boss.yaml          # 运行场景
python -m hsrsim run examples/moc12_elation.yaml         # 当期混沌回忆第 12 层（真实敌人数据）
python -m hsrsim run examples/kafka_dot_waves.yaml --runs 20   # 多种子取平均（效果命中等随机项）
python -m hsrsim trace examples/acheron_boss.yaml --character Acheron   # 逐条伤害 + 全部乘区（与游戏对照用）
python -m hsrsim stats examples/firefly_break_aoe.yaml   # 查看面板
python -m hsrsim list characters --implemented           # 已实现的角色
python -m hsrsim info "Jing Yuan"                         # 打印角色技能/行迹/星魂数据
python -m hsrsim ui                                       # 交互式界面（见上）
python tools/ability_summary.py Acheron --grep Passive    # 查看游戏技能脚本摘要（审校角色逻辑用）
```

输出示例（节选，`examples/acheron_boss.yaml`，20 个种子平均）：

```
Total DMG mean 612,588  sd 30,034  min 553,741  max 686,459
Cycles mean 5.00
  Acheron                      mean        507,205
  Silver Wolf                  mean         73,084
  ...
By damage type:  ult / basic / skill / fua / dot / break / super_break / additional / elation ...
By source:       Acheron | Rainblade (Crimson Knot) ...
```

## 配置文件

```yaml
scenario:
  preset: boss            # boss（单体）| aoe（多目标）| waves（清波）| moc / pf / as（当期真实关卡）
  # 真实关卡：preset: moc, half: 1（上/下半）, floor: 12, group: 1036（默认最新一期）
  cycles: 5               # 轮次上限：首轮 150 AV，之后每轮 100 AV
  weaknesses: [Thunder]   # Physical Fire Ice Thunder Wind Quantum Imaginary，或 all
  enemy: {level: 95, hp: 1.0e+12, toughness: 240, spd: 150, effect_res: 0.3}
  # 自定义波次：waves: [[{name: Boss, hp: 6.0e+6, toughness: 240, rank: boss, weaknesses: [Fire]}]]
config:
  crit_mode: expected     # expected（期望）| random（随机，配合 --runs）
  start_energy: 0.5       # 开局能量比例
  techniques: false       # 是否使用秘技
runs: 20
team:
  - character: Acheron    # 中英文名或 ID 均可（"黄泉" / "1308"）
    eidolon: 0
    light_cone: Along the Passing Shore
    superimposition: 1
    relics: {Pioneer Diver of Dead Waters: 4, Izumo Gensei and Takama Divine Realm: 2}
    main_stats: {body: crit_rate, feet: atk%, sphere: elemental, rope: atk%}
    substats: {crit_rate: 6r, crit_dmg: 12r, atk%: 3r, spd: 3r}   # "6r" = 6 次平均词条；也可写数值 0.3
    enhanced: false       # 有"强化版"套件的角色可切换
    options: {rotation: skill, target: Acheron}                   # 角色策略选项
```

也可以直接用 Python：

```python
from hsrsim import Build, scenarios
team = [Build("Seele", light_cone="In the Night"), Build("Sparkle"), Build("Silver Wolf"), Build("Huohuo")]
report = scenarios.boss_dps(cycles=5, weaknesses="Quantum").run(team)
print(report)                 # 文本报表
report.to_dict()              # 结构化结果（按角色/来源/伤害类型/轮次）
```

## 目录结构

| 路径 | 作用 |
|---|---|
| `hsrsim/battle.py` | 引擎：时间轴、回合流程、行动与命中、伤害、韧性/击破、修饰器、能量/战技点、波次 |
| `hsrsim/formulas.py` | 纯函数公式（有单元测试） |
| `hsrsim/modifiers.py` | 增益/减益/光环/DoT，持续时间语义 |
| `hsrsim/breaks.py` | 各属性击破效果（裂伤/灼烧/冻结/触电/风化/纠缠/禁锢） |
| `hsrsim/kits/` | 角色套件（一个角色一个模块） |
| `hsrsim/gear/` | 光锥与遗器的条件效果 |
| `hsrsim/data/gamedata/` | 数据快照（由 `tools/build_gamedata.py` 生成） |
| `hsrsim/scenarios.py` / `report.py` / `cli.py` | 场景、报表、命令行 |
| `hsrsim/control.py` / `session.py` | 手动操作：决策点（回合 / 终结技插入时机）、行动菜单、交互会话（撤销 = 重放） |
| `hsrsim/ui/` | 本地 Web 界面（`server.py` JSON 接口 + `static/` 前端，纯原生 JS） |
| `docs/RESEARCH.md` | **可行性研究报告**（结论、公式、可信度、限制、路线图） |
| `docs/mechanics_memo.md` | 机制逐条验证记录（含数据字段与置信度） |
| `docs/DEVELOPING.md` | 如何编写角色/光锥/遗器 |

## 更新到新版本

```bash
python tools/build_gamedata.py      # 重新拉取解包数据并生成快照
pytest -q                           # 数值回归测试
```

## 准确性说明

哪些部分与游戏逐位一致、哪些依赖社区共识常数、哪些需要实测校准，见 [docs/RESEARCH.md §1、§5](docs/RESEARCH.md)。
报表中的 `note:` 行会标出"只建模了静态属性"的光锥/遗器，避免误读结果。

## 许可

源代码 MIT。游戏数据版权归 HoYoverse 所有，仅用于研究与个人测试；第三方来源见 [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md)。
