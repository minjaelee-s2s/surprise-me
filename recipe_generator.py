import streamlit as st
import pandas as pd
from datetime import date, timedelta
import random
import os
import re
import google.generativeai as genai
import json
from PIL import Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# ===============================
# 🔥 [NEW] 추천 엔진용 재료 분류 규칙 (파이썬 로직)
# ===============================

# 1. 없어도 되는 재료 (향신채, 양념 등)
IGNORABLE_INGREDIENTS = {
    "대파", "쪽파", "파", "양파", "마늘", "다진마늘",
    "청양고추", "고추", "당근", "홍고추",
    "고춧가루", "후추", "참깨", "깨",
    "간장", "진간장", "국간장", "고추장", "된장", "쌈장",
    "설탕", "올리고당", "물엿", "맛술", "미림",
    "참기름", "들기름", "식용유", "소금", "물", "육수"
}

# 2. 고기류 통합 (부위 상관없이 '돼지고기'로 퉁침)
PORK_EQUIVALENTS = {"목살", "삼겹살", "앞다리살", "뒷다리살", "대패삼겹살", "돼지고기"}

def normalize_pantry(pantry_list):
    """냉장고 재료를 정규화 (예: 삼겹살 있으면 '돼지고기'도 있는 걸로 침)"""
    pantry = set(pantry_list)
    # 돼지고기 아류작이 하나라도 있으면 '돼지고기'라는 마스터 키 획득
    if any(meat in pantry for meat in PORK_EQUIVALENTS):
        pantry.add("돼지고기")
    return pantry

def split_ingredients(ingredient_string):
    """레시피 재료를 메인(Main)과 서브(Sub)로 분리"""
    ingredients = [x.strip() for x in str(ingredient_string).split(",")]
    main, sub = [], []

    for ing in ingredients:
        # 1. 무시해도 되는 재료면 Sub로
        if ing in IGNORABLE_INGREDIENTS:
            sub.append(ing)
        # 2. 돼지고기류면 Main에 넣되 '돼지고기'로 통일
        elif ing in PORK_EQUIVALENTS:
            main.append("돼지고기")
        # 3. 그 외(콩나물, 김치 등)는 Main
        else:
            main.append(ing)

    return list(set(main)), sub

def score_recipe(pantry_set, recipe_row):
    """점수 계산: 메인 재료가 냉장고에 얼마나 있는지 카운트"""
    main, _ = split_ingredients(recipe_row["필수재료"])
    # 교집합 개수 반환 (예: 콩불의 Main이 [콩나물, 돼지고기]면 2점)
    return len(pantry_set & set(main))

# --- 구글 시트 설정 ---
SHEET_NAME = "cooking_db"
PANTRY_TAB = "pantry"
RECIPE_TAB = "recipes"

# --- [스타일] 귀염 & 깔끔 테마 ---
def apply_cute_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');
        .stApp { background-color: #FFF9C4 !important; }
        h1, h2, h3, p, label, div[data-testid="stMarkdownContainer"], div[data-baseweb="select"] {
            font-family: 'Gowun Dodum', sans-serif !important;
            color: #5D4037 !important;
        }
        .main-title {
            font-weight: bold; color: #5D4037; margin-bottom: 20px;
            font-family: 'Gowun Dodum', sans-serif !important; word-break: keep-all;
        }
        @media (min-width: 601px) { .main-title { font-size: 3rem; } }
        @media (max-width: 600px) { .main-title { font-size: 1.8rem; } h2 { font-size: 1.5rem !important; } }
        div.stButton > button {
            border-radius: 20px !important; background: linear-gradient(to bottom right, #FFAB91, #FFCCBC) !important;
            color: white !important; border: none !important; box-shadow: 2px 2px 5px rgba(0,0,0,0.1) !important;
            font-family: 'Gowun Dodum', sans-serif !important; font-size: 1.1rem !important; font-weight: bold !important;
            padding-top: 10px !important; padding-bottom: 10px !important; transition: all 0.2s ease-in-out !important;
        }
        div.stButton > button:hover { transform: scale(1.02) !important; background: linear-gradient(to bottom right, #FF8A65, #FFAB91) !important; color: white !important; }
        div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div {
            border-radius: 15px !important; border: 2px solid #FFE082 !important; background-color: #FFFDE7 !important;
        }
        section[data-testid="stSidebar"] { background-color: #FFF59D !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 15px !important; border: 2px solid #AED581 !important; background-color: #F1F8E9 !important; padding: 15px !important;
        }
        div[data-baseweb="radio"] label, div[data-baseweb="checkbox"] label { font-family: 'Gowun Dodum', sans-serif !important; }
        </style>
    """, unsafe_allow_html=True)

# --- 구글 시트 연결 ---
def get_gsheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 데이터 로드 (캐싱) ---
@st.cache_data(ttl=10)
def load_data(tab_name, columns):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=columns)
        for col in columns:
            if col not in df.columns: df[col] = ""
        return df[columns]
    except Exception as e:
        return pd.DataFrame(columns=columns)

# --- 데이터 저장 (덮어쓰기) ---
def save_data_overwrite(df, tab_name):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        df_save = df.copy().fillna("")
        if '유통기한' in df_save.columns:
            df_save['유통기한'] = df_save['유통기한'].apply(lambda x: "" if pd.isna(x) or str(x) == "NaT" else str(x))
        sheet.clear() 
        sheet.update([df_save.columns.values.tolist()] + df_save.values.tolist())
        load_data.clear()
        time.sleep(0.5) 
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- 데이터 추가 (append) ---
def add_row_to_sheet(row_data, tab_name):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        sheet.append_row(row_data)
        load_data.clear()
        time.sleep(0.5)
    except Exception as e:
        st.error(f"추가 실패: {e}")

# --- AI 이미지 분석 (레시피 등록용) ---
def analyze_recipe_image_with_ai(api_key, images):
    genai.configure(api_key=api_key)
    models = ['gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro']
    prompt = """
    이 음식 사진들을 분석해서 [요리 이름], [필수 재료], [조리법]을 추출해 JSON으로 반환해.
    형식: {"name": "...", "ingredients": "재료1, 재료2", "steps": "..."}
    """
    for m in models:
        try:
            model = genai.GenerativeModel(m)
            response = model.generate_content([prompt] + images)
            return json.loads(response.text.replace("```json", "").replace("```", ""))
        except: continue
    return None

# --- [완전 교체] AI 메뉴 추천 (파이썬 로직 기반) ---
def get_ai_recommendations(api_key, pantry_list, recipe_list, excluded_list):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # 1. 내 냉장고 재료 정규화 (돼지고기 통합)
    pantry_set = normalize_pantry(pantry_list)

    # 2. 이미 본 레시피 제외
    filtered_recipes = [
        r for r in recipe_list
        if r["요리명"] not in excluded_list
    ]

    # 3. 🔥 Python에서 점수 계산 (AI에게 안 맡김!)
    scored = []
    for r in filtered_recipes:
        score = score_recipe(pantry_set, r)
        # 메인 재료가 하나라도 맞으면 일단 후보 (점수가 높을수록 좋음)
        if score > 0:
            scored.append((r, score))

    # 4. 점수 높은 순 정렬
    scored.sort(key=lambda x: x[1], reverse=True)

    # 5. [안전장치] 만약 매칭되는 게 하나도 없다? -> 그냥 필터된 것 중 아무거나 1개 가져옴
    if not scored and filtered_recipes:
        scored = [(filtered_recipes[0], 0)]
    elif not scored and not filtered_recipes:
        # 필터링까지 다 거쳤는데 진짜 남은 게 없다 (한 바퀴 돔) -> 빈 리스트 반환 (앱에서 리셋 처리)
        return {"recommendations": []}

    # 상위 1개만 뽑아서 AI에게 멘트 요청
    top_recipe = scored[0][0] 

    # 🔥 이제 Gemini는 "판단"이 아니라 "말빨(멘트)"만 생성
    prompt = f"""
    너는 긍정적인 자취생 요리 친구다.
    
    사용자 냉장고: {pantry_list}
    추천할 요리: {json.dumps(top_recipe, ensure_ascii=False)}

    위 요리를 추천하는 이유를 작성해줘.
    - 재료가 조금 부족해도 "응용 가능해요!", "없어도 괜찮아요!"라고 긍정적으로 말해.
    - 특히 파, 양파 같은 부재료가 없어도 절대 안 된다고 하지 마.
    
    출력 형식(JSON만 반환):
    {{
      "recommendations": [
        {{
          "name": "{top_recipe['요리명']}",
          "reason": "긍정적인 추천 멘트",
          "missing": "없지만 생략 가능한 재료들"
        }}
      ]
    }}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except:
        # AI가 멘트 생성 실패해도 추천은 띄움 (파이썬이 골라놨으니까!)
        return {
            "recommendations": [
                {
                    "name": top_recipe["요리명"],
                    "reason": "재료 조합상 가장 적절한 메뉴입니다! (AI 응답 지연, 자동 추천)",
                    "missing": "일부 부재료"
                }
            ]
        }

# --- 콜백 함수 (재료 추가) ---
def handle_add_pantry():
    n = st.session_state.get('input_name', "").strip()
    d = st.session_state.get('input_date', date.today())
    is_sauce = st.session_state.get('chk_sauce', False)
    is_seasoning = st.session_state.get('chk_season', False)

    if n:
        final_d = "" if (is_sauce or is_seasoning) else str(d)
        
        current_df = load_data(PANTRY_TAB, ["재료명", "유통기한"])
        if n in current_df['재료명'].values:
            current_df.loc[current_df['재료명'] == n, '유통기한'] = final_d
            save_data_overwrite(current_df, PANTRY_TAB)
            st.session_state['toast_msg'] = f"🔄 '{n}' 날짜 업데이트!"
        else:
            add_row_to_sheet([n, final_d], PANTRY_TAB)
            st.session_state['toast_msg'] = f"🧊 '{n}' 냉장고에 쏙!"
        
        st.session_state['input_name'] = ""
        st.session_state['input_date'] = date.today() + timedelta(days=7)
        st.session_state['chk_sauce'] = False
        st.session_state['chk_season'] = False
    else:
        st.session_state['warning_msg'] = "재료 이름을 적어주세요!"

# --- 앱 초기 설정 ---
st.set_page_config(page_title="오늘 뭐 먹지?", page_icon="🍳", layout="wide") 
apply_cute_style() 

if 'toast_msg' not in st.session_state: st.session_state['toast_msg'] = None
if 'warning_msg' not in st.session_state: st.session_state['warning_msg'] = None

if st.session_state['toast_msg']:
    st.toast(st.session_state['toast_msg'], icon="✅")
    st.session_state['toast_msg'] = None
if st.session_state['warning_msg']:
    st.warning(st.session_state['warning_msg'])
    st.session_state['warning_msg'] = None

if 'current_view' not in st.session_state: st.session_state['current_view'] = '요리하기'
if 'highlight_items' not in st.session_state: st.session_state['highlight_items'] = []
if 'ai_result' not in st.session_state: st.session_state['ai_result'] = {"name": "", "ingredients": "", "steps": ""}
if 'ai_recommendation' not in st.session_state: st.session_state['ai_recommendation'] = None

# 추천 기록 (새로고침 전까지 유지)
if 'shown_recipes' not in st.session_state: st.session_state['shown_recipes'] = []

if 'input_name' not in st.session_state: st.session_state['input_name'] = ""
if 'input_date' not in st.session_state: st.session_state['input_date'] = date.today() + timedelta(days=7)

# --- 사이드바 ---
with st.sidebar:
    st.title("🧸 메뉴") 
    menu_options = ["🍳 요리하기", "🧊 냉장고 관리", "📖 레시피 관리"]
    view_map = {"🍳 요리하기": "요리하기", "🧊 냉장고 관리": "냉장고 관리", "📖 레시피 관리": "레시피 관리"}
    current_label = [k for k, v in view_map.items() if v == st.session_state['current_view']][0]
    selected_label = st.radio("이동하기", menu_options, index=menu_options.index(current_label))
    if view_map[selected_label] != st.session_state['current_view']:
        st.session_state['current_view'] = view_map[selected_label]
        st.rerun()

    st.divider()
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
        st.success("✨ AI 연결됨")
    else:
        api_key_input = st.text_input("🔑 Gemini API Key", type="password")
        if api_key_input: os.environ["GEMINI_API_KEY"] = api_key_input

    st.write("")
    if st.button("🔄 추천 순서 리셋"):
        st.session_state['shown_recipes'] = []
        st.session_state['ai_recommendation'] = None
        st.success("처음부터 다시 추천합니다!")
        st.rerun()

pantry_df = load_data(PANTRY_TAB, ["재료명", "유통기한"])
recipe_df = load_data(RECIPE_TAB, ["요리명", "필수재료", "링크", "조리법"])
today = date.today()
if not pantry_df.empty: pantry_df['유통기한'] = pd.to_datetime(pantry_df['유통기한'], errors='coerce').dt.date

st.markdown('<div class="main-title">🍳 오늘 뭐 먹지?</div>', unsafe_allow_html=True)

# ==========================================
# 뷰 1: 요리하기 (하이브리드 엔진 장착)
# ==========================================
if st.session_state['current_view'] == "요리하기":
    st.header("👨‍🍳 AI 셰프의 추천")
    
    if pantry_df.empty or recipe_df.empty:
         st.warning("냉장고가 비었거나 레시피북이 비어있어요! 데이터를 먼저 채워주세요.")
    else:
        st.info("💡 파이썬과 AI가 협동해서 최적의 메뉴를 골라줍니다.")
        
        btn_text = "🎲 다음 메뉴 추천해줘!" if st.session_state['shown_recipes'] else "🧑‍🍳 AI! 첫 번째 메뉴 추천해줘"
        
        if st.button(btn_text, use_container_width=True):
            with st.spinner("메뉴 선정 중... (Python 연산 + AI 멘트 생성 🧐)"):
                key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                if key:
                    pantry_list = pantry_df['재료명'].tolist()
                    recipe_list = recipe_df[['요리명', '필수재료', '링크', '조리법']].to_dict('records')
                    
                    # 1. 추천 받기
                    result = get_ai_recommendations(key, pantry_list, recipe_list, st.session_state['shown_recipes'])
                    new_recs = result.get('recommendations', [])
                    
                    # 2. [자동 리셋 로직] 다 떨어졌으면 초기화 후 다시 요청
                    if not new_recs and st.session_state['shown_recipes']:
                        st.toast("🔄 한 바퀴 다 돌았네요! 처음부터 다시 추천합니다.")
                        st.session_state['shown_recipes'] = [] # 리셋
                        # 초기화된 상태로 다시 물어봄
                        result = get_ai_recommendations(key, pantry_list, recipe_list, [])
                        new_recs = result.get('recommendations', [])

                    st.session_state['ai_recommendation'] = new_recs
                    
                    # 3. 기록 추가
                    for r in new_recs:
                        if r['name'] not in st.session_state['shown_recipes']:
                            st.session_state['shown_recipes'].append(r['name'])
                else:
                    st.error("API 키가 없어요!")

        if st.session_state['ai_recommendation'] is not None:
            recs = st.session_state['ai_recommendation']
            
            if len(recs) == 0:
                st.warning("🥲 추천할 메뉴가 정말 없어요. (레시피 데이터가 없는 것 같아요)")
            else:
                for rec in recs:
                    with st.expander(f"🍽️ **{rec['name']}** (추천!)", expanded=True):
                        st.markdown(f"**🗣️ AI 의견:** {rec['reason']}")
                        if rec.get('missing'):
                            st.caption(f"⚠️ 참고: {rec['missing']}")
                        
                        original_data = recipe_df[recipe_df['요리명'] == rec['name']]
                        if not original_data.empty:
                            original = original_data.iloc[0]
                            st.divider()
                            st.text(str(original['조리법']).replace("\\n", "\n"))
                            if original['링크']: st.markdown(f"👉 [레시피 링크]({original['링크']})")
                            
                            if st.button(f"😋 {rec['name']} 요리 완료! (재료 소진)", key=f"cook_{rec['name']}"):
                                 st.session_state['highlight_items'] = [x.strip() for x in str(original['필수재료']).split(',')]
                                 st.session_state['current_view'] = "냉장고 관리"
                                 st.rerun()

# ==========================================
# 뷰 2: 냉장고 관리
# ==========================================
elif st.session_state['current_view'] == "냉장고 관리":
    st.header("🧊 우리집 냉장고")
    c1, c2 = st.columns([1.5, 1])
    with c1:
        if st.session_state['highlight_items']:
            st.error(f"🔥 방금 사용한 재료: {', '.join(st.session_state['highlight_items'])}")
            if st.button("알림 끄기"): st.session_state['highlight_items'] = []; st.rerun()
        if not pantry_df.empty:
            for idx, row in pantry_df.iterrows():
                icon = "🔴" if row['재료명'] in st.session_state['highlight_items'] else "🟢"
                d_day_str = ""
                display_style = ""
                
                if pd.isna(row['유통기한']): 
                    d_day_str = "(소스/조미료)"
                    display_style = "color:#8D6E63;" 
                else:
                    try:
                        d_day = (row['유통기한'] - today).days
                        d_day_str = f"({d_day}일 남음)" if d_day >= 0 else "(지남!!)"
                        display_style = "color:#FF7043;" if d_day < 3 else "color:#8D6E63;"
                    except: pass

                with st.container(border=True):
                    sc1, sc2 = st.columns([5, 1])
                    sc1.markdown(f"**{icon} {row['재료명']}** <span style='{display_style} font-size:0.9em; margin-left:10px;'>{d_day_str}</span>", unsafe_allow_html=True)
                    with sc2: 
                        if st.button("🗑️", key=f"d{idx}"): 
                            pantry_df = pantry_df.drop(idx)
                            save_data_overwrite(pantry_df, PANTRY_TAB); st.rerun()

    with c2:
        st.subheader("🛒 재료 채우기")
        db1, db2 = st.columns([1, 1])
        if db1.button("📅 +1주"):
            st.session_state['input_date'] = today + timedelta(weeks=1)
            st.rerun()
        if db2.button("📅 +1달"):
            st.session_state['input_date'] = today + timedelta(days=30)
            st.rerun()

        st.text_input("재료명 (필수!)", key="input_name")
        c_sauce, c_season = st.columns(2)
        with c_sauce: st.checkbox("🥫 소스", key="chk_sauce")
        with c_season: st.checkbox("🧂 조미료", key="chk_season")
        st.date_input("유통기한", key="input_date")
        
        st.write("") 
        st.button("✨ 냉장고에 넣기", use_container_width=True, on_click=handle_add_pantry)

# ==========================================
# 뷰 3: 레시피 관리
# ==========================================
elif st.session_state['current_view'] == "레시피 관리":
    st.header("📖 나만의 레시피북")
    t1, t2 = st.tabs(["➕ 레시피 등록", "📝 목록 보기"])
    with t1:
        with st.expander("🤖 사진으로 찰칵! 자동 입력", expanded=True):
            files = st.file_uploader("요리 사진", accept_multiple_files=True)
            if files and st.button("🪄 AI 분석"):
                key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                if not key: st.error("API 키 필요")
                else:
                    with st.spinner("분석 중..."):
                        imgs = [Image.open(f) for f in files]
                        res = analyze_recipe_image_with_ai(key, imgs)
                        if res: st.session_state['ai_result'] = res; st.success("성공!"); st.rerun()

        with st.form("rec_form"):
            default = st.session_state['ai_result']
            rn = st.text_input("요리 이름", value=default.get('name', ''))
            ri = st.text_input("필수 재료", value=default.get('ingredients', ''))
            rs = st.text_area("조리법", value=default.get('steps', ''), height=150)
            rl = st.text_input("참고 링크")
            st.write("")
            if st.form_submit_button("✨ 저장"):
                add_row_to_sheet([rn, ri, rl, rs], RECIPE_TAB)
                st.session_state['ai_result'] = {}
                st.session_state['toast_msg'] = "레시피 저장 완료!"
                st.rerun()
    with t2:
        if not recipe_df.empty:
            edited_df = st.data_editor(recipe_df, num_rows="dynamic", use_container_width=True, key="recipe_editor")
            if st.button("💾 저장"):
                clean = edited_df[edited_df['요리명'].notna() & (edited_df['요리명'] != "")].drop_duplicates(subset=['요리명', '링크'])
                save_data_overwrite(clean, RECIPE_TAB)
                st.session_state['toast_msg'] = "변경사항 저장 완료!"
                st.rerun()
