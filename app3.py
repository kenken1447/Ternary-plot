import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import os
from io import BytesIO
import base64
import tempfile
import subprocess
import platform
import shutil

st.title("三角相図ジェネレーター")
st.markdown("アップロードしたExcelファイルを元に三角相図を描きます。")

# --- 元素名入力 ---
col1, col2, col3 = st.columns(3)
with col1:
    elem_A = st.text_input("元素A", value="Sr")
with col2:
    elem_B = st.text_input("元素B", value="Mo")
with col3:
    elem_C = st.text_input("元素C", value="O")

uploaded_file = st.file_uploader("Excelファイルをアップロード（列順：ラベル, A, B, C）", type=["xlsx"])
st.image("Excelファイル記述例.png", caption="Excelファイル記述例", use_container_width=True)

# --- Ghostscript のパスを確認する関数 ---
def get_gs_executable():
    if platform.system() == "Windows":
        # Windowsでは通常 gswin64c.exe または gswin32c.exe
        possible_names = ["gswin64c", "gswin32c"]
    else:
        # macOS / Linux
        possible_names = ["gs"]
    for name in possible_names:
        path = shutil.which(name)
        if path:
            return path
    return None

# --- 図形をEPS形式で保存 ---
def convert_to_eps(fig, filename):
    gs_executable = get_gs_executable()
    if not gs_executable:
        st.error("Ghostscriptが見つかりませんでした。システムにインストールされているか確認してください。")
        return None

    with tempfile.TemporaryDirectory() as tmpdirname:
        pdf_path = os.path.join(tmpdirname, "temp.pdf")
        eps_path = os.path.join(tmpdirname, f"{filename}.eps")

        try:
            fig.write_image(pdf_path, format="pdf")
            subprocess.run(
                [gs_executable, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=eps2write",
                 f"-sOutputFile={eps_path}", pdf_path],
                check=True
            )
            with open(eps_path, "rb") as f:
                return f.read()
        except subprocess.CalledProcessError:
            st.error("EPSへの変換に失敗しました。Ghostscriptの実行に問題がある可能性があります。")
            return None
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            return None

# ダウンロードリンクを作成する関数
def get_download_link(binary_data, filename, format_type):
    b64 = base64.b64encode(binary_data).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}.{format_type}">図を{format_type.upper()}形式でダウンロード</a>'
    return href

# --- 三角相図描画用関数（color_mapを外部から渡す） ---
def draw_ternary(df, labels, coords, title, axis_names, color_map):
    fig = go.Figure()
    seen_labels = set()  # 凡例に表示済みのラベルを記録

    for i in range(len(coords)):
        label = labels.iloc[i]
        show_legend = label not in seen_labels
        seen_labels.add(label)

        fig.add_trace(go.Scatterternary(
            a=[coords[i, 0]],
            b=[coords[i, 1]],
            c=[coords[i, 2]],
            mode='markers',
            marker=dict(
                symbol='circle',
                size=10,
                color=color_map[label],
                line=dict(width=2, color='black')
            ),
            name=label,
            cliponaxis=False,
            showlegend=show_legend  # 最初の1回だけTrue
        ))

    fig.update_layout(
        title=title,
        ternary=dict(
            sum=1,
            aaxis=dict(title=axis_names[0]),
            baxis=dict(title=axis_names[1]),
            caxis=dict(title=axis_names[2])
        ),
        font=dict(size=14),
        legend=dict(itemsizing="trace", title="化合物")
    )
    return fig

if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        labels = df.iloc[:, 0]
        comp_A = df.iloc[:, 1]
        comp_B = df.iloc[:, 2]
        comp_C = df.iloc[:, 3]
        compositions = np.vstack([comp_A, comp_B, comp_C]).T
        normalized = compositions / compositions.sum(axis=1, keepdims=True)

        # --- カラーマップを1回だけ作成 ---
        unique_labels = labels.unique()
        colors = px.colors.qualitative.Vivid
        color_map = {label: colors[i % len(colors)] for i, label in enumerate(unique_labels)}

        # --- 通常三角相図 ---
        st.subheader(f"① {elem_A}-{elem_B}-{elem_C} 基本の三角相図")
        fig_default = draw_ternary(df, labels, normalized, f"{elem_A}-{elem_B}-{elem_C} 三角相図", [elem_A, elem_B, elem_C], color_map)
        st.plotly_chart(fig_default, use_container_width=True)
        
        # EPS保存ボタンを追加
        col1, col2 = st.columns(2)
        with col1:
            if st.button("基本の三角相図をEPS形式で保存", key="save_default_eps"):
                eps_data = convert_to_eps(fig_default, f"{elem_A}_{elem_B}_{elem_C}_triangular")
                if eps_data:
                    st.markdown(get_download_link(eps_data, f"{elem_A}_{elem_B}_{elem_C}_triangular", "eps"), unsafe_allow_html=True)
        
        with col2:
            if st.button("基本の三角相図をPDF形式で保存", key="save_default_pdf"):
                pdf_buffer = BytesIO()
                fig_default.write_image(pdf_buffer, format="pdf")
                pdf_data = pdf_buffer.getvalue()
                st.markdown(get_download_link(pdf_data, f"{elem_A}_{elem_B}_{elem_C}_triangular", "pdf"), unsafe_allow_html=True)

        # --- カスタム基底 ---
        st.subheader("② 頂点を変換した三角相図")

        compound_names = df.iloc[:, 0].unique().tolist()

        def get_composition_by_label(label):
            match = df[df.iloc[:, 0] == label]
            if not match.empty:
                return match.iloc[0, 1:4].tolist()
            return [None, None, None]

        name_a = st.selectbox("基底化合物1を選択", compound_names, key="a")
        name_b = st.selectbox("基底化合物2を選択", compound_names, key="b")
        name_c = st.selectbox("基底化合物3を選択", compound_names, key="c")

        compound_A = get_composition_by_label(name_a)
        compound_B = get_composition_by_label(name_b)
        compound_C = get_composition_by_label(name_c)

        if None in (compound_A + compound_B + compound_C):
            st.info("すべての化合物を正しく選択してください。")
        else:
            basis_matrix = np.array([compound_A, compound_B, compound_C]).T
            if np.linalg.matrix_rank(basis_matrix) < 3:
                st.error("選択した化合物が重複しており相図を作ることができません。別の組み合わせを選んでください。")
            else:
                inv_basis = np.linalg.inv(basis_matrix)
                new_coords = compositions @ inv_basis.T
                valid = np.all(new_coords >= 0, axis=1) & (np.sum(new_coords, axis=1) > 0)
                new_coords = new_coords[valid]
                labels_valid = labels[valid]
                new_coords /= new_coords.sum(axis=1, keepdims=True)
                fig_custom = draw_ternary(df, labels_valid, new_coords, "変換三角相図", [name_a, name_b, name_c], color_map)
                st.plotly_chart(fig_custom, use_container_width=True)
                
                # 変換三角相図のEPS保存ボタンを追加
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("変換三角相図をEPS形式で保存", key="save_custom_eps"):
                        eps_data = convert_to_eps(fig_custom, f"custom_triangular_{name_a}_{name_b}_{name_c}")
                        if eps_data:
                            st.markdown(get_download_link(eps_data, f"custom_triangular_{name_a}_{name_b}_{name_c}", "eps"), unsafe_allow_html=True)
                
                with col2:
                    if st.button("変換三角相図をPDF形式で保存", key="save_custom_pdf"):
                        pdf_buffer = BytesIO()
                        fig_custom.write_image(pdf_buffer, format="pdf")
                        pdf_data = pdf_buffer.getvalue()
                        st.markdown(get_download_link(pdf_data, f"custom_triangular_{name_a}_{name_b}_{name_c}", "pdf"), unsafe_allow_html=True)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# Ghostscriptに関する注意書き
st.markdown("---")
st.markdown("""
### 注意事項
EPS形式で保存するには、システムにGhostscriptがインストールされている必要があります。

- **Windowsの場合**: [Ghostscriptのダウンロードページ](https://www.ghostscript.com/download/gsdnld.html)からインストーラーを入手してください。
- **Macの場合**: `brew install ghostscript`でインストールできます。
- **Linuxの場合**: `sudo apt-get install ghostscript`（Ubuntuの場合）でインストールできます。
""")
