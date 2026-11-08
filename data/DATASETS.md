# 公开数据集下载与核验记录

下载日期：2026-11-06  
下载时区：Asia/Shanghai  
目录根路径：`drug-recommender/data/`

本目录当前只保存公开数据及其来源记录，不包含模型、训练代码或患者数据。

## 1. 已下载完整数据

### 1.1 FDA 2026 DailyMed DDI 数据

- 数据名称：Drug-Drug Interaction Dataset Derived from FDA 2026 DailyMed Drug Labels
- 版本：v1，发布日期 2026-04-21
- DOI：[10.5281/zenodo.19685458](https://doi.org/10.5281/zenodo.19685458)
- 记录页：https://zenodo.org/records/19685458
- 许可证：CC BY 4.0
- 下载文件 1：https://zenodo.org/records/19685458/files/ddi_2026.csv?download=1
- 下载文件 2：https://zenodo.org/records/19685458/files/drugs_atc_cid.csv?download=1
- 本地目录：`data/raw/zenodo_19685458/`

核验结果：

| 文件 | 大小 | 行数 | 列 |
|---|---:|---:|---|
| `ddi_2026.csv` | 1,988,266 bytes | 36,889 | `drug 1`, `drug 2`, `interaction` |
| `drugs_atc_cid.csv` | 70,266 bytes | 2,032 | `drug_name`, `cid`, `atc_codes` |

官方 MD5 校验：

| 文件 | 官方 MD5 | 本地结果 |
|---|---|---|
| `ddi_2026.csv` | `f858ae66604fa2e81ab1a0a4894c5d5e` | 一致 |
| `drugs_atc_cid.csv` | `50d7b4e0f0ec04aabc05521c610abefb` | 一致 |

进一步统计：

- `ddi_2026.csv` 涉及 3,760 个不同的原始药物名称字符串。
- 将其视作无向药物对后，共有 23,978 个唯一药物对和 12,911 条由同对多条描述造成的重复行。
- `drugs_atc_cid.csv` 包含 2,030 个唯一名称；1,881 行有 CID，1,760 行有 ATC 编码。
- 记录页摘要中的药物数量与原始 DDI 名称字符串数量并不完全一致，说明需要先进行同义词归一化。

数据用途：

- 药物相互作用存在性。
- DDI 描述文本。
- 药物名称、PubChem CID 和 ATC 分类。
- 可构建 DDI 风险图和药物文本特征。

重要限制：

- 这是从药品标签中抽取的相互作用记录，不包含统一的 `minor/moderate/major/contraindicated` 严重度字段。
- 同一药物对可能存在多条不同描述，使用前需要规范化药物对并合并记录。
- 药物名称尚未与 RxNorm、UNII 或 ChEMBL 完全统一。

### 1.2 NCATS Inxight Drugs FRDB

- 数据名称：Fast Response Database (FRDB)
- 版本：v1.5，2024-12-30
- 下载页：https://drugs.ncats.io/downloads-public
- 下载文件：https://drugs.ncats.io/downloads-public/frdb-v2024-12-30.zip
- 本地压缩包：`data/raw/frdb_v2024-12-30.zip`
- 本地解压目录：`data/raw/frdb_v2024-12-30/frdb/`
- 压缩包大小：3,437,578 bytes

核心表行数：

| 文件 | 行数 | 内容 |
|---|---:|---|
| `frdb-drugs.tsv` | 4,051 | 药物名称、compound ID、UNII |
| `frdb-ddi.tsv` | 34,851 | 药物 DDI 机制、靶点、关系、临床证据字段 |
| `frdb-toxicity.tsv` | 10,369 | 毒性实验、物种、剂量、给药途径等 |
| `frdb-adverseevents.tsv` | 61,045 | 不良反应类型、频率、严重度、DLT 等 |

附带数据：

- `frdb-pk.tsv`：药代动力学参数。
- `frdbmeta-targets.tsv`：DDI 靶点及 ChEMBL、UniProt 标识。
- `frdbmeta-data_model.tsv`：字段模型。
- `frdbmeta-data_dictionary.tsv`：受控词表。
- `readme.txt`：数据说明。

数据用途：

- 毒性、不良反应和药物安全特征。
- DDI 机制、代谢酶/转运体靶点和临床证据字段。
- 药物 UNII 与靶点标识补充。

重要限制：

- `frdb-ddi.tsv` 是单药-靶点/机制关系表，不是完整的“药物 A-药物 B-严重度”边表。
- 不同表通过 `compound_id`、`tox_id` 等内部键关联，使用前必须按数据字典连接。
- NCATS 页面未在本记录中重新声明单一 CC 许可证，引用和再分发时应同时查阅 NCATS/Inxight 的使用条款。

### 1.3 Synthea 合成患者 CSV

- 数据名称：Synthea sample data，CSV 最新版
- 仓库：https://github.com/synthetichealth/synthea-sample-data
- 固定提交：`84f59805d481b9f01f3141ef39e68bdbbeb80132`
- 下载文件：https://github.com/synthetichealth/synthea-sample-data/blob/main/downloads/latest/synthea_sample_data_csv_latest.zip
- 本地压缩包：`data/raw/synthea/synthea_sample_data_csv_latest.zip`
- 本地解压目录：`data/raw/synthea/synthea_sample_data_csv_latest/`
- 压缩包大小：5,446,315 bytes

核心表核验：

| 文件 | 行数 | 关键列 |
|---|---:|---|
| `patients.csv` | 111 | `Id`, `BIRTHDATE`, `GENDER`, `RACE`, `ETHNICITY` |
| `medications.csv` | 3,216 | `START`, `STOP`, `PATIENT`, `CODE`, `DESCRIPTION`, `REASONCODE` |
| `conditions.csv` | 3,387 | `START`, `STOP`, `PATIENT`, `CODE`, `DESCRIPTION` |
| `encounters.csv` | 5,059 | `START`, `STOP`, `PATIENT`, `ENCOUNTERCLASS`, `CODE` |
| `observations.csv` | 53,961 | `DATE`, `PATIENT`, `CODE`, `DESCRIPTION`, `VALUE`, `UNITS` |
| `allergies.csv` | 101 | `PATIENT`, `CODE`, `DESCRIPTION`, `SEVERITY1`, `REACTION1` |

数据用途：

- 无隐私的患者-药物序列。
- CF 的工程验证。
- 时间切分、过敏史和条件特征测试。

重要限制：

- 全部是合成数据，不能用于证明真实临床效果。
- 只有 111 名患者，适合跑通流程，不足以进行稳健的模型结论。
- 药物主要使用 RxNorm 编码；与上述 DDI 数据合并时仍需实体映射。

### 1.4 openFDA 药品标签数据

- 数据名称：openFDA Drug Label
- 下载说明页：https://open.fda.gov/apis/drug/label/download/
- 下载清单：https://api.fda.gov/download.json
- openFDA 导出日期：2026-11-06
- 本地清单：`data/raw/openfda/download_manifest.json`
- 完整标签数据规模：262,907 条记录，14 个分区

本次下载的分区：

- 文件：`drug-label-0001-of-0014.json.zip`
- 下载地址：https://download.open.fda.gov/drug/label/drug-label-0001-of-0014.json.zip
- 分区记录数：20,000
- 压缩包大小：136,776,614 bytes
- 解压文件：`data/raw/openfda/drug-label-0001-of-0014/drug-label-0001-of-0014.json`
- 解压大小：632,124,697 bytes

可用文本字段包括：

- 药品名称和 openFDA 标识。
- `indications_and_usage`。
- `mechanism_of_action`。
- `contraindications`。
- `warnings`。
- `drug_interactions`。
- `adverse_reactions`。

重要限制：

- 本次只下载了固定分区 1/14，不是全部 262,907 条标签。
- 固定分区适合作为公开复现的默认文本子集；若研究需要与 DDI 药物全集完全匹配，应再下载其余 13 个分区。
- 同一药品可能有多个厂家、剂型或标签版本，不能按标签记录直接当成唯一药物。
- openFDA 页面明确提示：数据不应单独用于医疗决策。

## 2. 已确认但本次未完成的数据

### 2.1 RxNorm Current Prescribable Content

- 官方页面：https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html
- 目标版本：`RxNorm_full_prescribe_11022026.zip`
- 目标地址：https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_11022026.zip
- 官方 MD5：`cd240fc9655dcd2cb54b1e185f3d8702`
- 文件大小：75,032,750 bytes
- 下载状态：未完成，未保留部分文件

原因：

- 当前网络下单连接下载速度约为 20–30 KB/s。
- 16 路范围请求仍被服务器明显限速，无法在合理时间内完成。
- 为避免把部分 ZIP 误认为完整数据，已删除全部临时分片。

用途：

- 将 Synthea 的 RxNorm 编码、NCATS 的药物名称/UNII 和 DDI 数据中的药物名称统一。
- 补充 RxCUI、成分、剂型和品牌关系。

该文件可以稍后用支持断点续传的下载器补全，并按上方官方 MD5 校验。

## 3. 当前数据组合能支持什么

| 研究组件 | 当前数据支持情况 |
|---|---|
| DDI 药物对和描述文本 | 支持 |
| 药物安全、毒性、不良反应 | 支持 |
| Synthea 合成患者用药队列 | 支持 |
| TF-IDF/LSA 药品标签文本 | 支持，已有 20,000 条标签固定分区 |
| ATC、PubChem CID | 支持 |
| 药物靶点补充 | 支持部分，来自 NCATS |
| RxNorm 完整实体归一化 | 尚未完成 |
| 真实患者外部验证 | 不支持，需另行申请受限 EHR |

## 4. 文件和校验

压缩包与原始文件均以 SHA-256 记录在：

- `data/manifests/SHA256SUMS.txt`

使用 PowerShell 重新检查：

```powershell
Get-FileHash -Algorithm SHA256 `
  data\raw\zenodo_19685458\ddi_2026.csv, `
  data\raw\zenodo_19685458\drugs_atc_cid.csv, `
  data\raw\frdb_v2024-12-30.zip, `
  data\raw\synthea\synthea_sample_data_csv_latest.zip, `
  data\raw\openfda\download_manifest.json, `
  data\raw\openfda\drug-label-0001-of-0014.json.zip
```

注意：openFDA 是滚动更新的数据源。上述校验值对应 `export_date=2026-11-06` 的快照；以后从同一 URL 更新可能得到不同文件。
