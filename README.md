# sequence-of-eras

日本历史时序地图（Web + iOS）。按日期切换地图上的势力、地点、事件与争议地区。

## 数据库

本地单文件库：**SQLite**（`db/sequence_of_eras.sqlite`）。

选型理由：单文件、零服务端、便于版本管理与分发，iOS 可直接打包进 App Bundle，Web 可用同一文件或由其导出的只读包。

| 路径 | 说明 |
| --- | --- |
| `doc/数据库设计.md` | 逻辑设计（字段语义、约束、默认内容骨架） |
| `db/schema.sql` | SQLite 表结构 |
| `db/build_db.py` | 建库脚本 + 种子数据 |
| `db/sequence_of_eras.sqlite` | 生成后的本地库 |

重建：

```bash
python db/build_db.py
python db/export_web_data.py
```

当前种子包含：默认情景、地图图层、列岛通史时代骨架、日本/中国纪年轨、近代日本年号样例、中国主体王朝骨架、以及四条争议地区（北方四岛、竹岛/独岛、尖阁/钓鱼岛、琉球）。详细历史几何与全量年号事件仍待后续录入。

## Web 前端

静态本地页，结构参照[江山时序](https://github.com/DeanChensj/jiangshan-map)：顶栏三行纪年、主地图、底时间轴、图例、点选卡片、`?year=` 深链与 `window.atlasAPI`。

地图引擎与业务解耦，见 `doc/前端架构.md`。默认 `svg_mercator`；以后换 MapLibre 等只需加引擎实现并改 `web/js/config.js`。

```bash
python db/export_web_data.py
cd web
python -m http.server 8080
```

浏览器打开 `http://localhost:8080/`。默认起点约公元前 2000 年（对齐夏商周视野；日本仍为绳文示意）。可用 `?year=-2000`、`?lang=ja`、`?engine=svg_mercator`。顶栏可切换中 / 日 / EN。控制台：`atlasAPI.setLang('en')`、`atlasAPI.inspectYear()`、`atlasAPI.gotoYear(1185)`。

疆域色块目前是示意复原，用于联调交互；精确边界后续用数据库几何替换。

## AI 上下文

Cursor 每次对话会自动载入 `.cursor/rules/sequence-of-eras.mdc`（`alwaysApply: true`）。详细字段与约束仍以 `doc/数据库设计.md` 为准。

## 许可

见 `LICENSE`。
