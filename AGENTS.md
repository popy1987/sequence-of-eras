# sequence-of-eras · Agent 手册

给 Cursor Agent 的常驻上下文。产品约定以 `.cursor/rules/sequence-of-eras.mdc` 为准；**本文件管操作：硬性约束、数据流、快捷操作**。增补快捷命令只改这里。

## 硬性约束（勿破）

- **不要主动操作 Git**（status / diff / commit / push / 切分支等），除非用户明确要求。
- **不要主动打开 IDE 内 Web 预览 / Simple Browser**；验页面只给外部命令，如 `cd web && python -m http.server 8080`。
- 用户未要求时不写无关 markdown；本文件与设计文档除外。
- 史实主轴对齐**日文维基**；不把维基正文大段入库或塞进前端。
- 改语义先改 `doc/数据库设计.md`，再改 `schema` → 种子 → 导出 → 前端。
- 本地继续 **SQLite 单文件**，不引入常驻数据库服务。

## 权威路径

| 用途 | 路径 |
| --- | --- |
| 逻辑设计 | `doc/数据库设计.md` |
| 前端架构 | `doc/前端架构.md` |
| Schema | `db/schema.sql` |
| 建库 | `db/build_db.py` → `db/sequence_of_eras.sqlite` |
| 导出 Web | `db/export_web_data.py` → `web/data/atlas.json` |
| 古坟种子 | `db/data/kofun_burials.json` · `db/seed_kofun_burials.py` |
| 飞鸟–平安事件 | `db/data/asuka_nara_heian_events.json` · `db/seed_asuka_nara_heian_events.py` |
| Web 应用 | `web/js/app.js` · `web/js/core/` · `web/js/map/engines/` |
| 三语 | `web/js/i18n/` |

## 数据约定速记

- 古坟年代 = 维基**築造／埋入**区间，**不是**出土年；争议用闭区间。
- 事件含 `conflict_class`：`civil_war` / `coup` / `pacification` / `external_war` / `intrigue`；争议年用区间 + `alignment=disputed`。
- 地图业务只经 `MapFrame`；换引擎改 `web/js/config.js` 的 `MAP_ENGINE`。
- 名称：`names.zh_hans` / `ja` / `en`；UI 文案走 `t()` / `data-i18n`。

## 快捷操作

> 以后常用一键流程、校验命令、种子入口都记在本节。Agent 被要求「按手册做 X」时优先查这里。

### 全量重建并导出

```bash
python db/build_db.py
python db/export_web_data.py
```

### 只重种古坟（库已存在）

```bash
python db/seed_kofun_burials.py
python db/export_web_data.py
```

### 只重种飞鸟–平安事件

```bash
python db/seed_asuka_nara_heian_events.py
python db/export_web_data.py
```

### 重启预览（一键看最新效果）

导出最新 `atlas.json`、释放 8080、启动静态服务，并用**系统浏览器**打开（不是 IDE 内预览）。前台运行，Ctrl+C 结束。

```bash
python scripts/restart_preview.py
```

常用变体：

```bash
# 先全量建库再导出并重启
python scripts/restart_preview.py --rebuild

# 跳到指定年 / 语言
python scripts/restart_preview.py --year 672 --lang ja

# 只重启服务（不重导 atlas）
python scripts/restart_preview.py --no-export

# 不自动开浏览器
python scripts/restart_preview.py --no-open
```

地址：`http://127.0.0.1:8080/`（脚本已带 query 时直接打开对应页）。

Agent：用户说「重启服务 / 看最新效果」时执行本条；**不要**开 Cursor Simple Browser。

### 本地预览（仅起服务，不导出）

```bash
cd web && python -m http.server 8080
```

### 抽样校验（示例）

```bash
python -c "import sqlite3; c=sqlite3.connect('db/sequence_of_eras.sqlite'); print('kofun', c.execute(\"select count(*) from place where kind='kofun'\").fetchone()[0]); print('events', c.execute('select count(*) from event').fetchone()[0])"
```

### 待补充

- （在此追加：导入新种子、对比 atlas 体积、指定年代冒烟检查等）

## 维护

- 新增可复用流程 → 写入「快捷操作」，保持命令可复制粘贴。
- 产品语义变更 → 改 `doc/数据库设计.md` 与 `.cursor/rules/sequence-of-eras.mdc`，本文件只同步路径与命令。
- 不要把长篇调研笔记堆进本文件；调研结论落成种子或设计文档后再在此加一条快捷入口即可。
