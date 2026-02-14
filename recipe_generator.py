import streamlit as st
import pandas as pd
from datetime import date, timedelta
import random
import os
import re
import google.generativeai as genai
import json
from PIL import Image

# --- 파일 경로 설정 ---
PANTRY_FILE = "pantry.csv"
RECIPE_FILE = "recipes.csv"

# --- 단위 변환 설정 ---
UNIT_MAP = {"판": 30, "반판": 15, "다발": 10, "봉": 1, "개": 1, "인분": 1}


# --- 데이터 로드/저장 함수 ---
def load_data(file_path, columns):
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)


def save_data(df, file_path):
    df.to_csv(file_path, index=False)


def parse_quantity(text_qty):
    if not text_qty or str(text_qty).strip() == "":
        return 1
    numbers = re.findall(r'\d+', str(text_qty))
    number = int(numbers[0]) if numbers else 1
    for unit, value in UNIT_MAP.items():
        if unit in str(text_qty): return number * value
    return int(text_qty) if str(text_qty).isdigit() else number


# --- AI 이미지 분석 함수 ---
def analyze_recipe_image_with_ai(api_key, images):
    genai.configure(api_key=api_key)
    candidate_models = ['gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-flash-latest']

    prompt = """
    당신은 요리 전문가입니다. 제시된 이미지들에는 하나의 요리 레시피가 이어져서 담겨있습니다.
    모든 이미지를 종합하여 [요리 이름], [필수 재료], [조리법]을 추출하고 JSON 형식으로 알려주세요.
    응답 형식(JSON) 예시:
    {
        "name": "요리 이름",
        "ingredients": "재료1, 재료2",
        "steps": "1. 과정1\n2. 과정2"
    }
    만약 이미지에서 레시피 정보를 찾을 수 없다면 모든 필드를 비워주세요.
    """
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            content = [prompt] + images
            response = model.generate_content(content)
            return json.loads(response.text.replace("```json", "").replace("```", ""))
        except Exception:
            continue
    st.error("❌ 분석 실패. API 키 확인 필요.")
    return None


# --- 앱 초기 설정 ---
st.set_page_config(page_title="자취생 요리 마스터", page_icon="👨‍🍳", layout="wide")

if 'current_view' not in st.session_state: st.session_state['current_view'] = '요리하기'
if 'highlight_items' not in st.session_state: st.session_state['highlight_items'] = []
if 'ai_result' not in st.session_state: st.session_state['ai_result'] = {"name": "", "ingredients": "", "steps": ""}

# --- 사이드바 ---
with st.sidebar:
    st.title("👨‍🍳 메뉴")
    menu_options = ["요리하기", "냉장고 관리", "레시피 관리"]
    if st.session_state['current_view'] not in menu_options:
        st.session_state['current_view'] = "요리하기"
    selected = st.radio("이동하기", menu_options, index=menu_options.index(st.session_state['current_view']))
    if selected != st.session_state['current_view']:
        st.session_state['current_view'] = selected
        st.rerun()

    st.divider()
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
        st.success("✅ AI 키 연결됨")
    else:
        api_key_input = st.text_input("Gemini API Key", type="password")
        if api_key_input: os.environ["GEMINI_API_KEY"] = api_key_input

# --- 데이터 불러오기 ---
pantry_df = load_data(PANTRY_FILE, ["재료명", "수량", "유통기한"])
recipe_df = load_data(RECIPE_FILE, ["요리명", "필수재료", "링크", "조리법"])

# 유통기한 날짜 처리
if not pantry_df.empty:
    pantry_df['유통기한'] = pd.to_datetime(pantry_df['유통기한'], errors='coerce').dt.date
    pantry_df['수량'] = pd.to_numeric(pantry_df['수량'], errors='coerce').fillna(1).astype(int)
today = date.today()

st.title(f"👨‍🍳 자취생 요리 마스터")

# ==========================================
# 뷰 1: 요리하기
# ==========================================
if st.session_state['current_view'] == "요리하기":
    st.header("오늘 뭐 먹지?")
    my_ingredients = set(pantry_df['재료명'].str.strip().tolist()) if not pantry_df.empty else set()
    possible_menus = []

    for index, row in recipe_df.iterrows():
        if pd.isna(row['필수재료']): continue
        needed = set([x.strip() for x in str(row['필수재료']).split(',')])
        missing = needed - my_ingredients

        if len(missing) == 0:
            row['부족한재료'] = []
            possible_menus.append(row)
        elif len(missing) <= 2:
            row['부족한재료'] = list(missing)
            possible_menus.append(row)

    if possible_menus:
        if st.button("🎲 랜덤 메뉴 추천받기"):
            st.session_state['selected_menu'] = random.choice(possible_menus)

        if 'selected_menu' in st.session_state:
            menu = st.session_state['selected_menu']
            st.info(f"추천 메뉴: **{menu['요리명']}**")
            if menu['부족한재료']: st.warning(f"⚠️ 부족한 재료: {', '.join(menu['부족한재료'])}")

            with st.expander("📜 조리법", expanded=True):
                st.text(str(menu['조리법']).replace("\\n", "\n"))
                if "http" in str(menu['링크']) and len(str(menu['링크'])) > 8:
                    st.markdown(f"👉 [자세히 보기]({menu['링크']})")

                if st.button("🍽️ 요리 완료!"):
                    st.session_state['highlight_items'] = [x.strip() for x in str(menu['필수재료']).split(',')]
                    st.session_state['current_view'] = "냉장고 관리"
                    st.rerun()
    else:
        st.warning("재료를 더 채워주세요!")

# ==========================================
# 뷰 2: 냉장고 관리 (버튼 분리 완료!)
# ==========================================
elif st.session_state['current_view'] == "냉장고 관리":
    st.header("🧊 냉장고 관리")
    c1, c2 = st.columns([1.5, 1])

    with c1:
        if st.session_state['highlight_items']:
            st.error(f"🔥 방금 쓴 재료: {', '.join(st.session_state['highlight_items'])}")
            if st.button("알림 끄기"):
                st.session_state['highlight_items'] = []
                st.rerun()

        if not pantry_df.empty:
            for idx, row in pantry_df.iterrows():
                icon = "🔴" if row['재료명'] in st.session_state['highlight_items'] else "🟢"

                # 유통기한 없는 경우 처리
                if pd.isna(row['유통기한']):
                    d_day_str = "(소스/조미료)"
                    display_style = "color:gray;"
                else:
                    d_day = (row['유통기한'] - today).days
                    d_day_str = f"({d_day}일 남음)" if d_day >= 0 else "(지남!!)"
                    display_style = "color:red;" if d_day < 3 else "color:gray;"

                with st.container(border=True):
                    sc1, sc2, sc3, sc4 = st.columns([3, 1, 1, 1])
                    sc1.markdown(
                        f"**{icon} {row['재료명']}** : {row['수량']}개 <span style='{display_style} font-size:0.8em'>{d_day_str}</span>",
                        unsafe_allow_html=True)

                    if sc2.button("➕", key=f"p{idx}"):
                        pantry_df.at[idx, '수량'] += 1
                        save_data(pantry_df, PANTRY_FILE);
                        st.rerun()
                    if sc3.button("➖", key=f"m{idx}"):
                        if pantry_df.at[idx, '수량'] > 0: pantry_df.at[idx, '수량'] -= 1
                        save_data(pantry_df, PANTRY_FILE);
                        st.rerun()
                    if sc4.button("🗑️", key=f"d{idx}"):
                        pantry_df = pantry_df.drop(idx)
                        save_data(pantry_df, PANTRY_FILE);
                        st.rerun()

    with c2:
        st.subheader("재료 추가")
        with st.form("add"):
            n = st.text_input("재료명 (필수)")

            # --- [수정됨] 체크박스 2개로 분리 ---
            st.caption("👇 해당되는 경우 체크 (수량·기한 입력 무시)")
            chk_col1, chk_col2 = st.columns(2)
            with chk_col1:
                is_sauce = st.checkbox("🥫 소스")
            with chk_col2:
                is_seasoning = st.checkbox("🧂 조미료")
            # ----------------------------------

            col_q, col_d = st.columns(2)
            with col_q:
                q = st.text_input("수량", placeholder="예: 1판")
            with col_d:
                d = st.date_input("유통기한", value=today + timedelta(days=7))

            if st.form_submit_button("저장"):
                if n:
                    # 소스나 조미료 중 하나라도 체크되면 무제한 모드
                    if is_sauce or is_seasoning:
                        final_q = 1
                        final_d = None
                    else:
                        final_q = parse_quantity(q)
                        final_d = d

                    new_row = pd.DataFrame({"재료명": [n], "수량": [final_q], "유통기한": [final_d]})
                    pantry_df = pd.concat([pantry_df, new_row], ignore_index=True)
                    save_data(pantry_df, PANTRY_FILE)
                    st.rerun()
                else:
                    st.warning("재료 이름은 꼭 적어주세요!")

# ==========================================
# 뷰 3: 레시피 관리
# ==========================================
elif st.session_state['current_view'] == "레시피 관리":
    st.header("📖 레시피 관리센터")
    t1, t2 = st.tabs(["➕ 등록", "📝 목록"])
    with t1:
        with st.expander("🤖 사진으로 자동 입력", expanded=True):
            files = st.file_uploader("이미지", accept_multiple_files=True)
            if files:
                imgs = [Image.open(f) for f in files]
                st.image(imgs, width=100)
                if st.button("🪄 분석 실행"):
                    key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                    if not key:
                        st.error("API 키 필요")
                    else:
                        with st.spinner("AI가 분석 중..."):
                            res = analyze_recipe_image_with_ai(key, imgs)
                            if res:
                                st.session_state['ai_result'] = res
                                st.success("성공!");
                                st.rerun()

        with st.form("rec_form"):
            default = st.session_state['ai_result']
            rn = st.text_input("요리명", value=default.get('name', ''))
            ri = st.text_input("재료", value=default.get('ingredients', ''))
            rs = st.text_area("조리법", value=default.get('steps', ''))
            rl = st.text_input("링크")
            if st.form_submit_button("저장"):
                new_rec = pd.DataFrame({"요리명": [rn], "필수재료": [ri], "링크": [rl], "조리법": [rs]})
                recipe_df = pd.concat([recipe_df, new_rec], ignore_index=True)
                save_data(recipe_df, RECIPE_FILE)
                st.session_state['ai_result'] = {}
                st.success("저장 완료!");
                st.rerun()

    with t2:
        if not recipe_df.empty:
            edited_df = st.data_editor(
                recipe_df, num_rows="dynamic", use_container_width=True, key="recipe_editor",
                column_config={"링크": st.column_config.LinkColumn("링크"),
                               "조리법": st.column_config.TextColumn("조리법", width="large")}
            )
            if st.button("💾 변경사항 저장하기"):
                clean_df = edited_df[edited_df['요리명'].notna() & (edited_df['요리명'] != "")]
                save_data(clean_df, RECIPE_FILE)
                st.success("저장됨 (빈 줄 삭제)");
                st.rerun()