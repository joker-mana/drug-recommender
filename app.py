from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from drugrec.service import RecommendationService  # noqa: E402


st.set_page_config(
    page_title="药物候选排序与安全约束评估",
    page_icon="🩺",
    layout="wide",
)


@st.cache_resource
def load_service() -> RecommendationService:
    return RecommendationService()


def split_lines(value: str) -> list[str]:
    return [
        line.strip()
        for line in value.replace("，", "\n").replace(",", "\n").splitlines()
        if line.strip()
    ]


def status_label(status: str) -> str:
    return {
        "eligible_for_review": "可进入人工复核",
        "pharmacist_review": "药师重点复核",
        "blocked": "已阻断",
    }.get(status, status)


st.title("药物候选排序与安全约束评估")
st.caption(
    "公开药物知识 + Synthea 合成患者序列 | "
    "TF-IDF/LSA + 协同过滤 + Personalized PageRank + DDI 安全门"
)

try:
    service = load_service()
except Exception as exc:
    st.error(
        "模型或处理后的数据尚未准备完成。请先依次运行：\n\n"
        "`python scripts/build_data.py`\n\n"
        "`python scripts/train_models.py`"
    )
    st.exception(exc)
    st.stop()

patients = service.system.patient_options()
patients = patients[patients["medication_count"].fillna(0).gt(0)]

with st.sidebar:
    st.header("场景设置")
    patient_labels = {
        row.PATIENT: (
            f"{row.PATIENT[:8]} | {row.GENDER or '未知'} | "
            f"{int(row.medication_count)} 条用药"
        )
        for row in patients.itertuples(index=False)
    }
    patient_id = st.selectbox(
        "Synthea 合成患者",
        options=patient_labels,
        format_func=lambda value: patient_labels[value],
    )
    context = service.system.patient_context(patient_id)
    top_k = st.slider("返回候选数", min_value=3, max_value=20, value=10)
    st.info(
        "合成患者仅用于工程验证。切换到空白场景时，可清空患者用药并自行输入。"
    )

if "last_result" not in st.session_state:
    st.session_state.last_result = None

with st.form("ranking_form"):
    left, right = st.columns([1.2, 1])
    with left:
        target_indication = st.text_area(
            "目标适应证 / 临床问题",
            value=context["target_indication"],
            height=100,
            help="可以是疾病名称、症状或本次希望满足的临床问题。",
        )
        conditions_text = st.text_area(
            "患者条件",
            value="\n".join(context["conditions"]),
            height=120,
            help="每行一个疾病、症状或关键状态。",
        )
    with right:
        current_med_text = st.text_area(
            "当前用药",
            value="\n".join(context["current_medications"]),
            height=120,
            help="每行一个药名。无法映射的名称会在安全结果中明确标记。",
        )
        allergy_text = st.text_area(
            "过敏记录",
            value="\n".join(context["allergies"]),
            height=80,
        )
    candidate_text = st.text_area(
        "候选药限制（可选）",
        value="",
        height=80,
        help="留空时在全部可排序药物中检索；填写后只在这些药物中排序。",
    )
    submitted = st.form_submit_button("生成候选并评估安全约束", type="primary")

if submitted:
    result = service.system.rank(
        target_indication=target_indication,
        conditions=split_lines(conditions_text),
        current_medications=split_lines(current_med_text),
        allergies=split_lines(allergy_text),
        candidate_drugs=split_lines(candidate_text) or None,
        top_k=top_k,
    ).payload
    st.session_state.last_result = result

result = st.session_state.last_result
if result is not None:
    meta = result["meta"]
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("参与排序", meta["candidate_count"])
    metric_b.metric("安全阻断", meta["blocked_count"])
    metric_c.metric("需药师复核", meta["review_count"])
    metric_d.metric("未映射当前用药", len(meta["unresolved_medications"]))

    if meta["unresolved_medications"]:
        st.warning(
            "以下当前用药未能映射，DDI 检查不完整："
            + "、".join(meta["unresolved_medications"])
        )
    if meta["unresolved_allergies"]:
        st.warning(
            "以下过敏记录未能映射到候选药目录："
            + "、".join(meta["unresolved_allergies"])
        )
    if meta["unresolved_candidates"]:
        st.warning(
            "以下候选药无法识别，未加入排序："
            + "、".join(meta["unresolved_candidates"])
        )

    rows = []
    for item in result["results"]:
        rows.append(
            {
                "排名": item["rank"],
                "候选药": item["name"],
                "状态": status_label(item["status"]),
                "总分": item["score"],
                "风险分": item["risk_score"],
                "文本相关": item["scores"]["text"],
                "协同过滤": item["scores"]["collaborative"],
                "图传播": item["scores"]["graph"],
                "证据完整": item["evidence_score"],
                "主要理由": "；".join(item["reasons"]),
            }
        )
    st.subheader("候选药排序")
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "总分": st.column_config.NumberColumn(format="%.3f"),
            "风险分": st.column_config.NumberColumn(format="%.3f"),
            "文本相关": st.column_config.NumberColumn(format="%.3f"),
            "协同过滤": st.column_config.NumberColumn(format="%.3f"),
            "图传播": st.column_config.NumberColumn(format="%.3f"),
            "证据完整": st.column_config.NumberColumn(format="%.3f"),
        },
    )

    with st.expander("查看被安全门阻断的候选药", expanded=bool(result["blocked_preview"])):
        if not result["blocked_preview"]:
            st.write("本次没有发现由明确高严重度规则触发的阻断。")
        for item in result["blocked_preview"]:
            st.error(f"{item['name']}：{'；'.join(item['reasons'])}")

    with st.expander("查看完整可审计结果"):
        st.download_button(
            "下载 JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="drug_candidate_assessment.json",
            mime="application/json",
        )
        st.json(result)

st.divider()
st.caption(result["meta"]["disclaimer"] if result else service.system.disclaimer())

