# 药物候选排序与安全约束评估系统

这是一个只使用公开数据的工程验证系统。它对医生给定的适应证和候选药进行排序，并针对当前用药、过敏记录、DDI 和 NCATS 不良反应特征执行安全约束。

系统不是处方系统，输出必须由医生或药师复核。

## 数据

详细来源、字段、校验值和使用限制见 [data/DATASETS.md](data/DATASETS.md)。

当前使用：

- FDA 2026 DailyMed DDI：相互作用药物对和描述。
- openFDA Drug Label 固定分区：适应证、机制、禁忌、警告和不良反应文本。
- NCATS FRDB v2024-12-30：DDI 靶点、毒性和不良反应汇总。
- Synthea 合成患者：用药序列、疾病、观察和过敏记录。

## 环境

项目固定使用：

```text
C:\Users\zfs\.conda\envs\drugrec\python.exe
```

如需重新创建环境：

```bat
conda create -n drugrec python=3.11 pip -y
conda activate drugrec
python -m pip install -r requirements.txt
```

## 一键构建

首次从外部数据源复现时，先下载数据：

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\download_data.py
```

然后在 `drug-recommender` 目录中依次运行：

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\build_data.py
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\train_models.py
```

GitHub 仓库不提交 `data/raw/` 和 `artifacts/`。仓库已经包含
`data/processed/`，因此克隆后如果只重新训练模型，可以跳过原始数据下载和
`build_data.py`，直接运行 `scripts/train_models.py`。

也可以安装为可编辑包：

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" -m pip install -e .
```

## 运行界面

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" -m streamlit run app.py
```

浏览器打开终端中显示的地址。界面支持：

- 选择 Synthea 合成患者并加载当时用药和疾病。
- 自定义目标适应证、患者条件、当前用药和过敏记录。
- 限制候选药名单。
- 查看文本、协同过滤、图传播和流行度分项。
- 查看被安全门阻断的药物及其 DDI 证据。
- 下载完整 JSON 审计结果。

## 命令行排序

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\rank.py `
  --patient-id 007a32fb-33a3-6f75-2161-15a2ea6ed2bf `
  --top-k 10 `
  --output reports\example_rank.json
```

自定义场景：

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\rank.py `
  --patient-id 007a32fb-33a3-6f75-2161-15a2ea6ed2bf `
  --target "viral sinusitis" `
  --medications "warfarin, simvastatin" `
  --allergies "penicillin" `
  --candidates "amoxicillin, doxycycline, naproxen"
```

## 离线评估

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" scripts\evaluate.py
```

评估采用每位 Synthea 患者最后一次用药作为留出目标，比较流行度、文本、协同过滤、混合排序和加入安全门后的结果。输出写入 `reports/`。

## 测试

```powershell
& "C:\Users\zfs\.conda\envs\drugrec\python.exe" -m pytest -q
```

## 方法

1. 药物名称通过 RxNorm、UNII、CID 和名称别名整合到统一目录。
2. openFDA 适应证和机制文本用于 TF-IDF/VSM，并通过 TruncatedSVD 生成 LSA 向量。
3. Synthea 患者-药物矩阵形成隐式反馈，使用 item-item 余弦协同过滤。
4. 药物-ATC 与药物-靶点图使用 Personalized PageRank 传播治疗邻域。
5. DDI 图只用于安全约束，不作为正向推荐边。
6. 高严重度 DDI 或过敏记录直接阻断；缺少映射和证据时转为药师复核。

## 重要限制

- Synthea 是合成数据，不能证明真实临床效果。
- DDI 源数据没有标准严重度标签，本系统使用描述关键词规则推断风险等级，属于工程启发式。
- openFDA 标签只使用了固定的 20,000 条分区，部分药物缺少标签证据。
- 当前未完成 RxNorm 全量下载；药物实体映射仍有名称匹配误差。
- NCATS 的 `frdb-ddi.tsv` 是药物-机制/靶点记录，不等同于 DDI 药对严重度表。
- 系统不提供剂量计算、疗程、疗效保证或自动处方。

