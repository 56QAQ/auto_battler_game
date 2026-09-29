# HSR combat mechanics — verification memo (live 4.6 datamine, researched 2026-09-29)

Confidence tags: **[DATA]** = I read it in the datamine myself. **[COMM]** = community consensus: fribbels optimizer code, or fandom/KQM text seen through search snippets. **[INFER]** = my inference from data structure, with no explicit confirmation. **[UNVERIFIED]** = I could not check it.

## 0. Sources and how I used them

- **Datamine** (DimbreathBot/turnbasedgamedata, `main`):
  - Raw files were downloaded into a local scratch directory (not committed). From `ExcelOutput/`: AvatarSkillConfig, AvatarServantSkillConfig, AvatarPromotionConfig, AvatarServantConfig, AvatarBreakDamage, ElationBasicLevelDamage, ElationSkill, MonsterConfig, MonsterTemplateConfig, HardLevelGroup, EliteGroup, MonsterSkillConfig, StageConfig, the Challenge* and ScheduleDataChallenge* tables, RelicMainAffixConfig, RelicSubAffixConfig, ExtraEffectConfig and BattleEventConfig. Also `TextMap/TextMapEN.json`.
  - From `Config/`: `GlobalConfig/GameCoreConstValue.json`, `ConfigGlobalModifier/GlobalModifier_*.json`, `ConfigAbility/Avatar/Avatar_*_Ability.json` (about 27 characters), `ConfigAbility/BattleEventAbility.json` and `ConfigAbility/Level/*`.
  - **Hash decoding.** Dynamic-value hashes use the C# stable string hash (h1=h2=5381; h1=((h1<<5)+h1)^c[i]; h2 does the same on odd characters; result = h1 + h2*1566083941). I checked it: `MDF_TargetMaxHP` hashes to 518695521. `PostfixExpr.OpCodes` is base64 bytecode: `00 i` pushes FixedValues[i], `01 i` pushes DynamicHashes[i], `02`=+, `03`=−, `04`=×, `11`=return. A small decoder script was used (not committed).
  - **What is not in the data.** Many per-effect numbers (bleed %, wind-shear stacks, burn ratio, etc.) are passed in at runtime by C# code, so they are not in the data. The data only fixes the **formula structure**. The numbers come from community sources.
- **fribbels hsr-optimizer**, commit `bd427fa` (2026-09-29). Main file: `src/lib/optimization/engine/damage/damageCalculator.ts`. Also used: `context/calculateContext.ts`, `stores/optimizerForm/optimizerFormDefaults.ts`, `tabs/tabCalculators/ahaCalculations.ts`, and the character conditionals.
- **Mar-7th StarRailRes** `index_new/en`: `characters`, `character_skills`, `character_skill_trees`, `paths`, `properties`, `relic_*`.
- **Web.** WebFetch to fandom, prydwen, hoyolab wiki, keqingmains and game8 is **blocked** by the egress proxy. Only WebSearch result snippets were available (mostly quoting the fandom "Toughness", "Wind" and "Physical" pages and the KQM speed guide). homdgcat and starrailstation were not tried because the data answered those points.

---

## 1. Outgoing damage formula

```
DMG = Base × DMG%mult × DEFmult × RESmult × VULNmult × DMGreduction(=0.9 if target has toughness)
      × Weaken(attacker) × FinalDMGmult × CRITmult  (+ True DMG handled separately, §1.9)
```

| Term | Exact form | Conf. |
|---|---|---|
| Base | Σ(scaling × stat), using ATK (default), `FormulaType: ByMaxHP` (HP), DEF, and so on. Stat is the unit's current stat. | DATA (FormulaType values: default, `ByMaxHP`, `ByBreakDamage`, `ByElationDamage`) |
| DMG% | `1 + Σ(all DMG% + elemental DMG% + ability-type DMG% …)`. This is one additive bucket. | COMM (fribbels `getTotalDmgBoost`) |
| DEF | `DEFmult = 1 − DEF/(DEF + 200 + 10·L_atk)`. Enemy `DEF = (200 + 10·L_enemy) × max(0, 1 + DEF%buffs − DEFreduction − DEFignore)`. Closed form: `(L_atk+20) / ((L_enemy+20)·max(0,1−red−ign) + L_atk+20)`. At L80 vs L95 with no reduction this is 100/215 = 0.4651. | Constants **DATA**: `GameCoreConstValue.DefenceAdd=200`, `DefenceMultipe=10`, and HardLevelGroup `DefenceRatio × DefenceBase(210)` = 200+10L at every level I checked. Form and max(0) are **COMM** (fribbels `calculateDefMulti`). |
| Enemy DEF by level | 200+10·L exactly: L95 = 1150, L90 = 1100. | DATA |
| RES | `RESmult = 1 − clamp(RES − RESPEN, −1.0, +0.9)`, giving a range of 0.1 to 2.0. Weak elements have RES 0. Non-weak elements are usually 0.2, sometimes 0.4. | fribbels clamp **COMM**. `GameCoreConstValue.OverallResistanceMin=-1` (DATA, matches the −100% floor). `OverallResistanceMax=2` (DATA) is probably the multiplier ceiling 2.0. **The 0.9 upper cap itself was not found in data.** |
| Vulnerability | `1 + min(ΣVuln, 2.5)`. All "DMG taken +x%" effects add together. | **DATA**: `DamageTakenRatioMax = 3.5`. fribbels uses min(2.5). |
| DMG mitigation | Multiplicative: Π(1 − r_i). The engine property is `AllDamageReduce`, capped by `AllDamageReduceMax = 0.99`. | Cap is DATA. Multiplicative stacking is COMM. |
| "0.9" toughness multiplier | This is not a special layer. It is a normal 10% DMG reduction: modifier `MonsterAllDamageReduce` does `StackProperty AllDamageReduce 0.1`. It is added back when `StanceBreakState` ends, i.e. when toughness recovers, and it is absent while broken. So it stacks multiplicatively with other enemy DMG reduction. | DATA (`GlobalModifier_Common_Specific.json`) |
| Weaken | `×(1 − ΣWeaken)` on the weakened unit's outgoing damage. Templates have `MinimumFatigueRatio = 0.2` ("Fatigue" is the internal name for Weaken; its icon is IconImmuneWeakness), which probably means Weaken is capped at 80%. | COMM, with INFER for the cap |
| Final DMG | A separate multiplicative layer `(1 + FinalDMG)`. Several sources multiply together (fribbels `multiplicativeBoost(FINAL_DMG_BOOST)`: Acheron trace, Castorice E1, Evernight E1, Yao Guang E4). Engine property: `Level_FinalDamageAddedRatio`. Game text says "final DMG". | COMM + DATA (property exists in `ServantSyncPropertyList`) |
| Crit | Expected value `cr·(1+cd) + (1−cr)`, with CR capped at 100%. Real rolls are a Bernoulli trial. There is **no damage variance**: `DamageRandomMin = DamageRandomMax = 1`. **DoT and break damage cannot crit**: `AttackTypeForbidCriticalList = ["DOT","ElementDamage"]` (ElementDamage is the AttackType of break and super-break hits). Additional DMG (`AttackType "Pursued"`) and Elation DMG *can* crit. | DATA (constants). Cap is COMM (fribbels). |
| Damage split | `HitSplitRatio` splits the multiplier and toughness across hits. `SPHitRatio` splits energy. | DATA |

### 1.9 True DMG — exists [DATA]

- **Definition.** Glossary (ExtraEffect 10000017): "Non-Type DMG that is not affected by any effects. This DMG is not considered as launching 1 attack."
- **Engine.** `AttackType: "TrueDamage"`, `FinalFormulaType: "ByBaseDamage"`, `DamageValue = ratio × original damage`. I found this in the Cyrene, Tribbie E1 and Silver Wolf LV.999 configs. Cyrene's is `MDF_BasicDamagePercentage × _originalDamage`.
- **How to compute.** `TrueDMG = X% × final DMG of the source instance`, applied after all multipliers. No DEF, RES, crit or vulnerability applies again. It cannot break toughness.
- **Existing sources.** Tribbie E1, Cyrene zone, Remembrance-TB "Mem's Support", Phainon E6, Cipher, Robin • Summeretto E1 and SW LV.999. fribbels models it as `×(1 + TRUE_DMG_MODIFIER)` on the source hit. [COMM]
- **Version.** It became common from 3.x (Amphoreus characters).

---

## 2. Weakness Break

### 2.1 Break DMG [DATA structure + COMM constants]

```
BreakDMG = LvMult(L_attacker) × ElemMult × (0.5 + MaxToughness_data/120) × (1+BE) × (1+BreakDMG%)
           × DEFmult × RESmult × VULNmult × 1.0(broken) × FinalDMG
```

- **Element multiplier:** Physical 2, Fire 2, Wind 1.5, Ice 1, Lightning 1, Quantum 0.5, Imaginary 0.5.
  - COMM: fribbels `ElementToBreakScaling`.
  - DATA for Physical: Boothill's talent computes `BreakDamagePercentage = (0.2*2)*((_maxStance/30)+2)/4 * ratio`, where 2 is the Physical multiplier and 0.2/0.2/0.6 are hit splits.
- **Toughness multiplier:** `0.5 + T_data/120`, which equals `0.5 + T_display/40`. Boothill's expression `((maxStance/30)+2)/4` is the same thing. [DATA]
- **No DMG% and no crit:** "Break DMG cannot CRIT Hit and is not affected by DMG Boost effects." (glossary 10000014) [DATA]. Only break-specific boosts apply.
- **Formula flags:** Break hits use `FormulaType: ByBreakDamage`, `AttackType: ElementDamage`, `FinalFormulaType: ByPureDamage`.
- **Level multiplier table** — `AvatarBreakDamage.json`, field `BreakBaseDamage`, indexed by **attacker** level [DATA]. Character max level is 80 (`AvatarPromotionConfig.MaxLevel`).

```
L  1- 10: 54.0000 58.0000 62.0000 67.5264 70.5094 73.5228 76.5661 79.6385 82.7395 85.8684
L 11- 20: 91.4944 97.0680 102.5892 108.0579 113.4743 118.8383 124.1499 129.4091 134.6159 139.7703
L 21- 30: 149.3323 158.8011 168.1768 177.4594 186.6489 195.7452 204.7484 213.6585 222.4754 231.1992
L 31- 40: 246.4276 261.1810 275.4733 289.3179 302.7275 315.7144 328.2905 340.4671 352.2554 363.6658
L 41- 50: 408.1240 451.7883 494.6798 536.8188 578.2249 618.9172 658.9138 698.2325 736.8905 774.9041
L 51- 60: 871.0599 964.8705 1056.4207 1145.7910 1233.0585 1318.2965 1401.5751 1482.9608 1562.5178 1640.3068
L 61- 70: 1752.3215 1861.9011 1969.1241 2074.0660 2176.7983 2277.3904 2375.9084 2472.4160 2566.9739 2659.6406
L 71- 80: 2780.3044 2898.6023 3014.6030 3128.3730 3239.9758 3349.4731 3456.9236 3562.3843 3665.9100 3767.5535
L 81- 90: 3957.8618 4155.2120 4359.8640 4572.0880 4792.1640 5020.3833 5257.0470 5502.4663 5756.9670 6020.8840
L 91-100: 6294.5654 6578.3735 6872.6826 7177.8810 7494.3716 7822.5723 8162.9165 8515.8540 8881.8500 9261.3870
```

The file has 101 rows (L1–100 plus L120 = L100). Level 80 is **3767.5535** (fribbels hard-codes 3767.5533).

### 2.2 Toughness units [DATA]

- **Two units.** `AvatarSkillConfig.ShowStanceList` is in *data units*. `StanceDamageDisplay` is in *display units*. The ratio is exactly 3: a basic attack is 30 data = 10 display, and a typical skill is 60 = 20.
- **Enemy toughness.** `MonsterTemplateConfig.StanceBase` × `StanceModifyRatio` × `HardLevelGroup.StanceRatio` × `EliteGroup.StanceRatio` is in **data units**. Example: Hoolay has 720 data = 240 display.
- **fribbels mixes units.** `enemyMaxToughness` is in data units (default 360, used with /120). `toughnessDmg` is in display units (a basic is 10).
- **Hit toughness.** A hit's toughness is `AttackData.StanceValue`, split by `HitSplitRatio`.

### 2.3 Break state, delay, recovery [DATA: `StanceBreakState` modifier]

- **On break (OnCreate):**
  - `ModifyActionDelay AddNormalizedValue 0.25`. This is a **fixed 25% delay**, not scaled by BE: gauge +2500, i.e. AV += 0.25·10000/SPD. Const `StanceBreakActionDelayChangeRatio = 0.25`.
  - Then `TriggerBreak`, which starts the break DMG and element effect.
- **Lifetime:** `LifeStepMoment: "ModifierPhase1End"`. The break state is removed **at the end of Phase 1 (turn-start phase) of the enemy's next turn**.
- **On removal (OnDestroy):**
  - `ResetStance` restores full toughness.
  - `MonsterAllDamageReduce` is re-added (the 10% reduction).
  - The enemy **then acts normally in that same turn**. In-game text agrees: "Weakness Break will continue until the start of their next action."
- **Ordering at enemy turn start:**
  1. All `OnPhase1` handlers fire, sorted by `Phase1Priority`: DoTs (Bleed/Burn/Shock/Wind Shear), Entanglement damage and Freeze damage. At this point the enemy is **still broken**, so the multiplier is 1.0.
  2. Phase-1-End lifetime ticks run (DoT durations −1, break state removed).
  3. The action happens.
- **Consequence for 2-turn DoTs.** A break DoT's second tick lands after recovery, so it gets the 0.9 multiplier unless the enemy was re-broken. [INFER, from the above]

### 2.4 Per-element effects

Values are passed by code, so the numbers are **COMM** (fandom Toughness/Physical/Wind pages via search snippets, plus fribbels). **Structure is DATA** (`MCommon_Element_*` in `GlobalModifier_Common_Specific.json`).

- **Base chance:** break debuffs have **150% base chance** (COMM). They are resisted by Effect RES and debuff-specific RES.
- **What "×LvMult" means below:** these use `FormulaType ByBreakDamage`, which already includes LvMult(attacker) × (1+BE). They use DEF, RES and vulnerability. No DMG% and no crit (`FinalFormulaType ByPureDamage`).
- **Snapshot:** the modifiers set `UseSnapshotEntity: true`.

| Effect | Data structure (DATA) | Numbers (COMM) |
|---|---|---|
| **Bleed** (Phys) | `MaxHP × ratio`, where ratio depends on `ByCompareMonsterRank > 2` (i.e. Elite/LittleBoss/BigBoss vs minions). Then `min(…, cap)`. Then `DamageValue = value × (1+BE_snapshot) × layers`. AttackType DOT. `LifeStepMoment Phase1End`. | 16% MaxHP (normal) / **7%** (elite & boss), capped at `2 × LvMult × ToughMult`. The cap is before ×(1+BE). **2 turns.** |
| **Burn** (Fire) | `BreakDamagePercentage = ratio × layer`. DOT. Phase1End. | 1 × LvMult. 2 turns. |
| **Shock** (Lightning) | Same structure (`MCommon_Element_Electric`). | 2 × LvMult. 2 turns. |
| **Wind Shear** (`MCommon_Element_Poison`) | `ratio × MDF_PoisonLayer`. **`MaxLayer 5`** (DATA). | 1 × LvMult per stack. Applies **1 stack to normal, 3 to elite/boss**. Max 5. 2 turns. |
| **Freeze** (Ice) | **Not a DoT.** At the frozen enemy's Phase1: Ice **Additional** DMG (`AttackType Pursued`, ByBreakDamage). Then `ModifyCurrentSkillDelayCost NormalizedValue 0.5 (Set)`: the turn is skipped and the gauge resets to **50%** instead of 100%. This is the "action advanced 50% after thaw". `DisableAction`. | 1 × LvMult. 1 turn. |
| **Entanglement** (Quantum) | On apply: delay `MDF_ActionDelayRatio × (1 + BE_snapshot)`. Each time it is hit: stacks +1 (`MDF_BeingHitDamageValue`, capped at `Max_Count`). At Phase1: Quantum Additional DMG with `BreakDamagePercentage = (1 + hits) × ratio`. `LifeTime 1`, Phase1End. | Delay **20%**×(1+BE). The 0.2 base is also in DATA: `SkillDamageTypePreshowConfigs.Quantum.StanceBreakActionDelayChangeRatio=0.2`. DMG = **0.6 × stacks × LvMult × ToughMult**, stacks 1..5. 1 turn. |
| **Imprisonment** (Imaginary) | `SpeedAddedRatio −x`. Delay `= ratio × (1 + BE_caster)` (OpCodes `dyn0 × (1+dyn1)`). `DisableAction`, `STAT_CTRL`. Phase1End. | Delay **30%**×(1+BE) and SPD −10%. DATA preshow: `Imaginary.StanceBreakActionDelayChangeRatio=0.3`, `StanceBreakActionSpeedChangeRatio=-0.1`. **1 turn.** |

- **CC flags.** Freeze, Entanglement and Imprisonment carry `STAT_CTRL`, so they are blocked by CC-immune enemies (`DebuffResist STAT_CTRL = 1`). The specific RES keys are `STAT_CTRL_Frozen`, `STAT_Entangle` and `STAT_Confine` (`MonsterConfig.DebuffResist`).
- **Snapshot vs live stats:** **[UNVERIFIED]**. DoT modifiers set `UseSnapshotEntity` and read BE from `SnapshotPropertyEntity`. However, `SnapshotEntityInheritBlackList` excludes Attack and Defence, so it is unclear which stats freeze at application. Treat it as uncertain.

### 2.5 BE / Break-efficiency / Break-DMG-taken

- **BE** (`BreakDamageAddedRatio`) multiplies:
  - break DMG,
  - super break,
  - all break DoTs and Additional DMG,
  - Quantum and Imaginary delays.
- **Break Efficiency** (`StanceBreakAddedRatio`) multiplies toughness reduction, and therefore super break.
- **Other properties** that exist [DATA, exact use not verified]:
  - `StanceBreakTakenRatio` (enemy takes more toughness damage)
  - `StanceBreakResistance`, plus per element e.g. `FireStanceBreakResistance`
  - `StanceWeakRatio = 1`
  - `DefaultStanceResistance = 0`
- **Break-DMG-taken / Break-DMG-dealt:** treat as vulnerability and DMG%, restricted to break damage type (fribbels hit-level boosts). [COMM]

---

## 3. Super Break and toughness reduction

- **Super Break formula** [COMM, fribbels `SuperBreakDamageFunction`]:

  ```
  SuperBreak = LvMult(80) × (ToughnessReduced_display / 10) × SuperBreakMod × (1+BE) × (1+BreakDMG%)
               × DEF × RES × VULN × 1.0 × FinalDMG
  ```
  - `ToughnessReduced_display = base_display × (1 + BreakEfficiency) + fixedToughness`.
  - In data units: `LvMult × T_data/30`.
  - No crit and no DMG% ("Super Break DMG is also considered Break DMG", glossary 10000015).
- **Which hits count** [DATA: `Level_BattleCommonRule_Ability.json`, `MStageAbility_BattleCommonRule_SuperBreak_SubOnEnemy`]. The engine sums `MDF_HitStanceDamage` in `OnBeforeBeingStanceDamage` only if the target **already** has the `Break` flag, or the attacker or target has `STAT_ForceSuperBreakDamage`.
  - So the hit that causes the break does **not** generate super break.
  - Hits on an already-broken enemy do, even though toughness is 0.
  - The counter `MDF_TotalStanceDamage` resets per attack.
- **Toughness multiplier for super break: 1.0.** The target is broken by definition, so it has no `MonsterAllDamageReduce`. Initial break DMG is also 1.0. fribbels exposes a manual toggle, but the physics are 1.0. [DATA-derived]
- **Toughness reduction** [COMM; the DATA predicates `ByHasStanceWeak` / `ByTargetIsStanceWeakForCurrentHit` gate it]:

  ```
  ToughDmg = StanceValue × (1 + WeaknessBreakEfficiency)
  ```
  - It is 0 if the target lacks the weakness, unless an "ignore weakness" effect applies. Those are usually at reduced efficiency and defined per character.
  - `Toughness Protection` (70000305) blocks toughness reduction.
  - `Toughness Lock` (70000318) stops toughness at 1.

---

## 4. Durations / turn-phase semantics [DATA structure; semantics partly INFER]

- **Turn phases:**
  1. **Phase1** — turn start. `OnPhase1` handlers run: DoTs, Freeze, Entanglement, the cycle counter.
  2. **Action phase** (`ActionPhaseEnd`).
  3. **Turn end** — `OnListenTurnEnd` / Phase2.
- **`LifeStepMoment`** (where a modifier's `LifeTime` decrements). Values seen:
  - **unset (default)**: decrement at the **end of the holder's turn**. [INFER: default = turn end]
  - **`"ModifierPhase1End"`**: decrement **at the start of the holder's turn**, after Phase-1 effects fire. Used by:
    - every DoT, `StanceBreakState`, Entanglement and Imprisonment;
    - caster-held zones/fields: Ruan Mei `RuanMei_Skill02_Area`/`_Skill03_Area_Caster`, Robin `Skill02_DmgUpCasterListener`, Tribbie `SKL02/SKL03_Buff`, Cyrene `Skill02_Buff_Main`, Sunday `Skill03_Link_ForCaster`, Yao Guang `Skill02_ToSelf`, Rappa `UltraMode`, Boothill `DuelState`;
    - Tingyun `Rank01_SpeedUp`/`SkillTree_B1_SpeedUp`, Sparkle `Skill02_CritDmgAddedRatio02`, aggro up/down.
    - This matches in-game text such as "duration decreases by 1 at the start of Ruan Mei's/this unit's every turn".
  - **`"ActionPhaseEnd"`**: `OneMore` (extra turn), LifeTime 1.
- **Duration counting rules:**
  - A *DoT lasting N turns ticks N times.* It damages in Phase1, then decrements at Phase1End.
  - *Caster-held zones* count the **caster's** turns.
  - *Buffs placed on allies* (Bronya ult, Tingyun Benediction/ult, Sparkle skill) are modifiers on the **recipient** and count the recipient's turns.
  - *Ruan Mei's / Robin's / Tribbie's team buffs* are auras sourced from a modifier on the caster, so they count the caster's turns.
- **`"LifeStepImmediately": true`** is an `AddModifier` flag. It is set on Bronya ult (`MAvatar_Bronya_00_Ultra_PowerUp` → AllTeamMember), Tingyun ult (`MAvatar_TingYun_00_Skill03DamageUp`), Welt ult Imprisonment (`MCommon_Confine`), and `OneMore` also carries it as a behaviour flag. It is **absent** on Tingyun Benediction, Sparkle skill, Bronya skill and Hanya.
  - **Interpretation [INFER, consistent with COMM]:** the default engine rule is "a modifier added to a unit *during that unit's own turn* skips the decrement at the end of that turn". `LifeStepImmediately` opts out, so the current turn counts.
  - **Practical effect:** Bronya/Tingyun ult cast at the start of the DPS's turn gives that turn plus 1 more. A self-buff "for 1 turn" from your own Skill lasts through your *next* turn.
  - There is no explicit "skip first decrement" field. That rule is inferred from this override flag plus the community rule.
- **Examples of lifetime expressions:**
  - Bronya skill: LifeTime = `param (+1 at E6)`, gated by `ByRankActivated`.
  - Tingyun Benediction: LifeTime = skill param (3). It is a `ValueBindList` LifeTime binding; "effective only on the most recent receiver" is handled by code.

---

## 5. Energy and Skill Points

- **Energy by action type.** `AvatarSkillConfig.SPBase` at Level 1, mode per type [DATA]:
  - Basic (`AttackType Normal`): **20** (103 skills)
  - Skill (`BPSkill`): **30** (89)
  - Ultimate (`Ultra`): **5** (106)
  - Elation Skill (`ElationDamage`): **5**
  - Memosprite skills (`AvatarServantSkillConfig`, AttackType `Servant`): mostly 10 (sometimes 5/20/none). Memosprites have no energy bar (`ServantPropertyOverride.HidePropertyList: MaxSP`), so this presumably goes to the summoner. [INFER]
  - Exceptions exist per skill (e.g., basics 30/40, skills 20/6).
- **Energy when hit:** `MonsterSkillConfig.SPHitBase` per enemy skill: mostly 10 (923 skills), also 15/5/20/25. It is multiplied by ERR. [DATA; ERR multiplication is COMM/glossary]
- **Energy on kill: 10.** `Local_SPAdd` (Avatar_Common) fires on `OnTriggerDeath` → `ModifySPNew AddValue MDF_AddValue=10` [DATA]. It uses `AddValue`, which is ERR-scaled. `FixedAddValue` (used elsewhere) is the non-ERR variant.
- **ERR:** `gain = base × (1 + ERR)` for `AddValue`. The glossary says "certain Energy-Regenerating effects won't be impacted".
- **Max energy:** `AvatarConfig.SPNeed` (= `SPNeed` on the Ultra skill: 100–240, e.g. Sparxie 160). Some units use `SpecialMaxSP`.
- **Starting energy in MoC/PF/AS:** 50% of max. **[UNVERIFIED]** — widely assumed; I could not find it in data or snippets.
- **Pure Fiction kill energy:** search snippets say kills give 50% of normal energy in PF. **[UNVERIFIED]**
- **Skill points** [DATA: `GameCoreConstValue.TeamBPFloatStart=3`, `TeamBPFloatMax=5`]:
  - Start 3, max 5.
  - Basic `BPAdd 1`. Skill `BPNeed 1`; `-1` means no cost. Some enhanced basics cost 2–3.

---

## 6. Action Value / turn order

- **Gauge model** [COMM, KQM speed guide via snippet; DATA consistent]:
  - Action gauge AG starts at 10000.
  - AV = AG / SPD.
  - As time passes, `AG -= SPD × ΔAV`.
  - After acting, AG resets to `10000 × DelayRatio`. All skills have `DelayRatio 1`. Freeze sets the next reset to 0.5.
- **Changes to the gauge:**
  - A SPD change mid-gauge keeps the remaining AG, so `AV_new = AV_old × SPD_old / SPD_new`. [COMM]
  - Advance X% gives `AG -= X·10000` (floored at 0). Delay X% gives `AG += X·10000`. The engine uses `ModifyActionDelay AddNormalizedValue` = a fraction of the full gauge. [DATA form]
  - Monsters start at `InitialDelayRatio × 10000`. It is usually 1, sometimes 0.5, 0.25 or 0.75. [DATA field; INFER meaning]
- **MoC cycle.** The cycle counter is a neutral battle event `ChallengerEvent` with `Speed 100` (BattleEvent 1 / 30149 / 31001).
  - `MCommon_ChallengeTurnLimit` does `OnEnterBattle: ModifyActionDelay +0.5`. That makes the **first cycle 150 AV and later cycles 100 AV**.
  - A cycle elapses when this entity's Phase1 fires (`LevelChallengeTurnAcc`). [DATA]
- **Ordering:**
  - Ultimates can be inserted between any actions or at a turn start (states `InsertUltraSkillPrepare`/`InsertUltraSkillWaitOrder`).
  - Follow-ups (`AttackType Insert`) are queued and resolve after the current action.
  - Extra turns (`OneMore`) happen immediately after the current action phase, and no ult can be used during them (glossary 10000000).
  - Countdown and summon entities (Robin's Concerto, Ruan Mei's "Bloom", Khaslana, Aha) are separate action-bar entries with fixed or derived SPD. [DATA + COMM]
- **Ties:** equal AV goes to the leftmost lineup position first. [COMM, snippet] Ally-vs-enemy ties are **[UNVERIFIED]**.

---

## 7. Aggro [DATA: `AvatarPromotionConfig.BaseAggro`]

| Path (internal) | Base aggro |
|---|---|
| Preservation (Knight) | 150 |
| Destruction (Warrior) | 125 |
| Hunt (Rogue) | 75 |
| Erudition (Mage) | 75 |
| Harmony (Shaman) | 100 |
| Nihility (Warlock) | 100 |
| Abundance (Priest) | 100 |
| Remembrance (Memory) | 100 |
| Elation | 100 |

- **Memosprites:** `AvatarServantConfig.Aggro` — Garmentmaker 125, Evey 125, others 100.
- **Modifiers:** `AggroAddedRatio` via `M_SkillTree_AggroUp`/`Down`. `M_LowHP_AggroDown` lowers aggro below an HP threshold.
- **Selection:** single-target selection probability = aggro_i / Σ aggro [COMM]. Taunt (`MCommon_CTRL_Taunt`) forces the target.

---

## 8. Effect hit chance

- **Formula:**

  ```
  P = min(1, Base × (1+EHR) × (1 − EffectRES + EffectRESPEN) × (1 − DebuffSpecificRES))
  ```
  [COMM; fribbels uses `(1 − effRes + effResPen)`]. "Fixed chance" ignores all of these (glossary 30000002).
- **Enemy Effect RES** = `MonsterTemplateConfig.StatusResistanceBase` + `HardLevelGroup.StatusResistance`. [DATA]
  - Template base values across 632 templates: 0.2 for most; elites/bosses are 0.2 (179) or 0.3 (144); a few are 0.4 or 1.0.
  - HLG adds 0.08 at L70 and **0.10 at L80–100**.
  - **Endgame (L85–95): typically 30% for normal and some bosses, 40% for many bosses.**
- **Enemy EHR** = `HardLevelGroup.StatusProbability`: 0.32 at L90, 0.36 at L95.
- **Debuff-specific / CC RES:** `MonsterConfig.DebuffResist` list (Key → value). Current endgame examples:
  - `STAT_CTRL: 1` (fully CC-immune; Yabuli)
  - `STAT_CTRL: 0.75` (Arbiter)
  - `STAT_CTRL_Frozen/STAT_Confine/STAT_Entangle: 0.75` (Hoolay)
  - Key names: `MonsterStatusResistanceType.json`.

---

## 9. Enemy stats from the datamine [DATA]

**Formula** (the stage values override the monster defaults) [override semantics COMM]:

```
HP  = T.HPBase     × M.HPModifyRatio     × HLG[g,L].HPRatio     × Elite[e].HPRatio
ATK = T.AttackBase × M.AttackModifyRatio × HLG.AttackRatio      × Elite.AttackRatio
DEF = T.DefenceBase(210) × M.DefenceModifyRatio × HLG.DefenceRatio × Elite.DefenceRatio   (= 200+10L)
SPD = T.SpeedBase  × M.SpeedModifyRatio  × HLG.SpeedRatio       × Elite.SpeedRatio
Toughness(data units) = T.StanceBase × M.StanceModifyRatio × HLG.StanceRatio × Elite.StanceRatio
EffRES = T.StatusResistanceBase + HLG.StatusResistance ;  EHR = HLG.StatusProbability
Elemental RES = M.DamageTypeResistance[] (weak types in M.StanceWeakList have 0) ; CC RES = M.DebuffResist[]
```

- **Symbols:** T = `MonsterTemplateConfig[M.MonsterTemplateID]`. Note `MonsterTemplateID` ≠ `MonsterID` for variants, e.g. 200401404 → template 2004014. M = `MonsterConfig`. `(g, L, e)` = `StageConfig.HardLevelGroup`, `.Level` and `.EliteGroup`.
- **Other fields:** `TemplateGroupID`, and rarely `SpeedModifyValue` / `StanceModifyValue`. I did not verify the order in which the flat values are applied.
- **Rank enum** used by Bleed and Wind Shear logic: `Minion`, `MinionLv2`, `Elite`, `LittleBoss`, `BigBoss`. The code test is `ByCompareMonsterRank > 2`, meaning Elite and above.
- **Endgame → stage chain:** `ChallengeMazeConfig` (MoC), `ChallengeStoryMazeConfig` (PF) and `ChallengeBossMazeConfig` (AS) have `EventIDList1/2` → `StageConfig.StageID`, which gives `MonsterList` waves. PF waves go through `StageInfiniteGroup` → `StageInfiniteWaveConfig` → `StageInfiniteMonsterGroup`, which has its own `EliteGroup`.
- **Current endgame levels:**

  | Mode | Stages | Level | HLG | EliteGroup | Other |
  |---|---|---|---|---|---|
  | MoC 1036 floor 12 | 30126121/2 | **95** | 3 | 164 (HP×6.5) | 30 cycles |
  | MoC Tierce | 30126123 | 95 | — | 168 | 45 cycles |
  | Pure Fiction 2026/2027 floor 4 | — | **85** | 1 | — | 4 cycles |
  | AS 3020/3021 floor 4 | — | **90** | 1 | e.g. 166 (HP×7.1) | — |

- **Worked example — Borisin Warhead: Hoolay (MonsterID 2034010), MoC floor 12 node 1, wave 2:**
  - Rank LittleBoss.
  - HP = 2557.5 × 1 × 375.4385 × 6.5 = **6,241,196**.
  - ATK = 18 × 34.75065 = 625.5.
  - DEF = 210 × 5.47619 = **1150**.
  - SPD = 200 × 1.32 = **264**.
  - Toughness = **720** data (240 display), so toughness multiplier = 0.5 + 720/120 = **6.5**.
  - Effect RES = 0.2 + 0.1 = **0.30**. EHR 0.36.
  - Weak to Physical/Fire/Wind. RES 20% for Ice/Lightning/Quantum/Imaginary.
  - DebuffRES: Frozen/Confine/Entangle 0.75.
- **Second example — AS: Soulhook Sovereign (200401404), L90 HLG1 Elite 166:**
  - HP = 7207.5 × 1.096774 × 236.5347 × 7.1 = 13.28 M.
  - SPD 198, toughness 900 data, Effect RES 0.30.
  - RES 40% for Ice/Lightning/Quantum.
- The enemy-stat computation above will be ported into `tools/build_gamedata.py` (roadmap).

---

## 10. Relics [DATA]

- **Main stat (5★, groups 51–56 in `RelicMainAffixConfig`):** value at +15 = `BaseValue + 15 × LevelAdd`. Values at +15:

  | Stat | +15 |
  |---|---|
  | HP | 705.6 |
  | ATK | 352.8 |
  | HP% / ATK% / EHR | 43.2% |
  | DEF% | 54.0% |
  | CR | 32.4% |
  | CD | 64.8% |
  | OHB | 34.56% |
  | SPD | 25.032 |
  | Elemental DMG% | 38.88% |
  | BE | 64.8% |
  | ERR | 19.44% |

  Elation is **not** a relic stat.
- **Substat roll (group 5 in `RelicSubAffixConfig`):** `BaseValue + k × StepValue`, with k ∈ {0,1,2} (`StepNum 2`) giving low/mid/high.

  | Stat | Rolls (low / mid / high) |
  |---|---|
  | HP | 33.870 / 38.104 / 42.338 |
  | ATK, DEF | 16.935 / 19.052 / 21.169 |
  | HP%, ATK%, EHR, EffRES | 3.456 / 3.888 / 4.32 % |
  | DEF% | 4.32 / 4.86 / 5.4 % |
  | SPD | 2.0 / 2.3 / 2.6 |
  | CR | 2.592 / 2.916 / 3.24 % |
  | CD, BE | 5.184 / 5.832 / 6.48 % |

- **Upgrade rules** [COMM]: 3–4 initial substats, one upgrade every +3 (5 total by +15).

---

## 11. New mechanics a 4.x engine must support

### Remembrance / memosprites

- **Summoning:** a memosprite is a `Servant` entity (`CreateServant`) with its own action-bar turns and its own HP.
- **HP and SPD** come from `AvatarServantConfig`:
  - `HPBase` (flat) + `HPInherit` × owner max HP
  - `SpeedBase` (flat) or `SpeedInherit` × owner SPD
  - Parameters come from `HPSkill` / `SpeedSkill`.
  - Examples:
    - Garmentmaker: SPD = 35% Aglaea SPD; HP = 66% HP + 720.
    - Mem: SPD 130; HP = 80% + 640.
    - Netherwing: SPD 165, lasts 3 turns.
    - Evey: SPD 160; HP 50%.
    - Summer Songbirds: HP 70%; SPD 180%.
- **Inherited stats:** everything else is **synced from the owner** via `GameCoreConstValue.ServantSyncPropertyList`: ATK, DEF, all DMG%, crit, PEN, BE, EHR/ERR, `Level_FinalDamageAddedRatio`, and so on. So memosprite damage uses the owner's stats.
- **Abilities:** memosprite skills are `AttackType "Servant"` and cost no SP (`BPNeed -1`). Glossary: re-summoning dispels CC on the memosprite.
- **Damage attribution:** memosprite damage is its own damage source. This matters for "memosprite DMG" buffs, and fribbels uses `scalingEntityIndex` so memosprite hits can scale off the owner's stats.

### Elation path (4.x)

- **Roster:** Sparxie 1501, Yao Guang 1502, Pearl 1503, Evanescia 1505, Silver Wolf LV.999 1506, Aventurine • Waveflair 1513, Trailblazer 8009/8010.
- **Not the path mechanic:** `Config/ConfigAbility/ElationBattle` is a **limited event mode** (activity 50064), not the path mechanic.
- **New stats:**
  - `ElationDamageAddedRatio(Base)` ("Elation"; glossary: "affects Elation DMG and boosts its multiplier").
  - "Merrymake" (glossary 30000011: "additionally boost Elation DMG").
- **Punchline:** a team-shared counter. Elation abilities grant it, e.g. Yao Guang's ult gives 5 and her basic/skill give 3.
  - Once the team has Punchline, **Aha** (BattleEvent 70001, `EventSubType Elation`) joins the action bar.
  - **Aha SPD** = 80 + Σ over Elation characters sorted by SPD descending, SPD_i × {1/5, 1/10, 1/20, 1/40}. [COMM, fribbels `ahaCalculations.ts`]
- **Aha's turn — the "Aha Instant":**
  - Every unit with an Elation Skill uses it once, in order of Participant ID.
  - `ElationSkill.json.PriorityValue`, e.g. Yao Guang 116, Sparxie 144. I infer lower goes first. [INFER]
  - If there are none, Aha uses "Let There Be Laughter".
  - Afterwards: **all Punchline is consumed**, and participants gain **"Certified Banger" for 2 turns**. It stores the Punchline counted at that time. Multiple stacks add up, and each has its own duration.
  - Some abilities grant Aha an **extra turn with a fixed Punchline count that does not consume Punchline**. Yao Guang ult: 20, or 40 at E1.
- **Elation Skill:** a separate ability type (`AttackType ElationDamage`, `FormulaType ByElationDamage`, 5 energy).
- **Elation DMG formula** [structure COMM, fribbels; base DATA]:

  ```
  ElationDMG = ElationBase(L) × scaling × (1+Elation) × (1+Merrymake) × (1 + 5P/(P+240))
               × DEF × RES × VULN × 0.9/1.0 × FinalDMG × CRIT     (NOT affected by DMG% boosts)
  ```
  - `ElationBase` is `ElationBasicLevelDamage.json`: L80 = **7535.107** (exactly 2× break base up to L80), L1 = 108, L70 = 5319.28.
  - P = Punchline "taken into account": the Aha-instant count, or the Certified-Banger total.
  - The punchline curve `1+5P/(P+240)` is **COMM** (fribbels; not found in data).
  - Some ATK-scaling hits add `Elation × ATK` terms (fribbels `elationAtkScaling`), e.g. Sparxie's ult is `(0.6×Elation + 30%)×ATK`.

### Other new mechanics and layers

- **True DMG** (§1.9).
- **Additional DMG:** `AttackType Pursued`. Not an attack; uses DMG% and can crit.
- **Joint ATK** (glossary 10000019): several units attack in one action.
- **Assist Skill** (10000032; `AttackType Assist`, 18 energy; Himeko • Nova): granted to allies and consumes the turn.
- **Final-DMG layer**, as in §1.
- Others: "Repellency" (team DMG block), "Territory", "Backup" / "Out-of-Bounds" / "Departed" units, "Coup de Main" (copy ability), and Khaslana's countdown extra turns.

---

## 12. Endgame scoring (essentials)

- **Memory of Chaos** [DATA]:
  - 30-cycle limit (`ChallengeCountDown 30`).
  - Stars: clear with ≥10 cycles left, ≥20 left, and a downed-count condition (`ChallengeTargetConfig` 251/252/253, type `ROUNDS_LEFT`).
  - Tierce: 45 cycles, stars at 15/30 left.
  - Cycle = 150 AV first, then 100 AV (§6).
  - The DPS metric is AV (or cycles) to kill all waves.
- **Pure Fiction:**
  - [DATA] Floor 4 has a cycle limit of 4 (`TurnLimit`) and `ClearScore 30000`. Stars are 40k/50k/60k total over 2 nodes. Tierce: 60k/75k/90k (target 99k).
  - [DATA] Waves: `MaxMonsterCount` 25/45/45 with 5 on field (`MaxTeammateCount 5`). Wave ability params `(0,4.5)`, `(0.05,12)`, `(0.12,55)` have unknown meaning.
  - [COMM] Points come from kills (scaled by wave and enemy rank), damage to the boss, and a bonus for remaining cycles. The "Grit" gauge (e.g. 5 per kill toward 100) enters "Surging Grit". Per-node max ~40k. The exact point table is **[UNVERIFIED]**.
- **Apocalyptic Shadow:**
  - [DATA text] "Score affected by the boss' remaining HP % and remaining action value after defeating the boss; if undefeated only HP %."
  - [COMM] Up to 2000 points for HP depleted, plus remaining AV from a 2000-AV budget converted about 1:1 when the boss dies. Max 4000 per node.
  - [DATA] Star thresholds (total of 2 nodes): 4000 / 5200 / 6600 (`ChallengeBossTargetConfig` 3001–3003). Tierce: 6000/7800/9900.

---

## Known gaps / flags

- **Break numbers:** the break-effect numbers (bleed 16%/7%, burn 1×, shock 2×, wind shear 1 vs 3 stacks, entanglement 0.6, freeze 1×, 150% base chance) come only from community sources. The data proves the formula shape but the constants are injected by code.
- **RES cap:** the 0.9 RES cap was not found in data (only −1 and 2).
- **Duration rule:** the "skip first decrement when applied on own turn" rule is inferred, not read.
- **Other unverified items:** starting energy 50%, PF kill-energy penalty, ally/enemy AV tie order, and DoT snapshot vs live stats.
- **Unknown fields:** `SPMultipleRatio 0.5` (all skills), `StanceTargetSkipRound`, `SpeedToDelayDistance 1000`, `RoundAddBoostPoint 2` and `MonsterRankScore` (0.5/1/1.5/2/3) exist in constants with unknown use.
