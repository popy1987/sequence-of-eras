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
```

当前种子包含：默认情景、地图图层、列岛通史时代骨架、日本/中国纪年轨、近代日本年号样例、中国主体王朝骨架、以及四条争议地区（北方四岛、竹岛/独岛、尖阁/钓鱼岛、琉球）。详细历史几何与全量年号事件仍待后续录入。

## 许可

见 `LICENSE`。
