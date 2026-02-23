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
# 🔥 재료 분류 및 텍스트 정리 도구
# ===============================

IGNORABLE_INGREDIENTS = {
    "대파", "쪽파", "파", "양파", "마늘", "다진마늘",
    "청양고추", "고추", "당근", "홍고추",
    "고춧가루", "후추", "참깨", "깨",
    "간장", "진간장", "국간장", "고추장", "된장", "쌈장",
    "설탕", "올리고당", "물엿", "맛술", "미림",
    "참기름", "들기름", "식용유", "소금", "물", "육수", "치킨스톡", "굴소스"
}

PORK_EQUIVALENTS = {"목살", "삼겹살", "앞다리살", "뒷다리살", "대패삼겹살", "돼지고기", "다짐육"}

def clean_ingredient_text(text):
    text = str(text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\d+(?:g|kg|ml|L|l|개|스푼|큰술|작은술|컵|마리|모|봉|인분|t|T)?', '', text)
    text = re.sub(r'\d+/\d+(?:스푼|컵|큰술)?', '', text) 
    text = re.sub(r'(?:한|두|세|네|반)\s*(?:바퀴|줌|꼬집|스푼|큰술|컵)', '', text) 
    text = re.sub(r'[^\w\s]', '', text) 
    return text.strip()

def normalize_pantry(pantry_list):
    pantry = set(pantry_list)
    if any(meat in pantry for meat in PORK_EQUIVALENTS):
        pantry.add("돼지고기")
    return pantry

def check_is_present(recipe_ing, pantry_set):
    cleaned_ing = clean_ingredient_text(recipe_ing)
    for ignore in IGNORABLE_INGREDIENTS:
        if ignore in cleaned_ing: return True
    if any(pork in cleaned_ing for pork in PORK_EQUIVALENTS):
        if "돼지고기" in pantry_set: return True
    for p_item in pantry_set:
        if p_item in cleaned_ing: return True
    return False

def score_recipe(pantry_set, recipe_row):
    ingredients = [x.strip() for x in str(recipe_row["필수재료"]).split(",")]
    match_count = sum(1 for ing in ingredients if check_is_present(ing, pantry_set))
    return match_count

def format_steps(text):
    text = str(text).strip()
    text = re.sub(r'(\d+[\.\)])', r'\n\1', text)
    if not re.search(r'\d+[\.\)]', text):
        steps = text.split('.')
        formatted = []
        idx = 1
        for step in steps:
            if step.strip():
                formatted.append(f"{idx}. {step.strip()}.")
                idx += 1
        return "\n".join(formatted)
    return text

# --- 구글 시트 설정 ---
SHEET_NAME = "cooking_db"
PANTRY_TAB = "pantry"
RECIPE_TAB = "recipes"

# --- [스타일] ---
def apply_cute_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');
        .stApp { background-color: #FFF9C4 !important; }
        h1, h2, h3, p, label, div[data-testid="stMarkdownContainer"], div[data-baseweb="select"], li {
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
        /* 탭 스타일링 */
        button[data-baseweb="tab"] { font-family: 'Gowun Dodum', sans-serif !important; font-size: 1.1rem !important; }
        </style>
    """, unsafe_allow_html=True)

# --- 구글 시트 연결 ---
def get_gsheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 데이터 로드 (보관장소 컬럼 추가) ---
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

# --- 데이터 저장 ---
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

# --- 데이터 추가 ---
def add_row_to_sheet(row_data, tab_name):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        sheet.append_row(row_data)
        load_data.clear()
        time.sleep(0.5)
    except Exception as e:
        st.error(f"추가 실패: {e}")

# --- AI 이미지 분석 (강력한 추출기로 업그레이드) ---
# --- AI 이미지 분석 (JSON 강제 모드 + 에러 원인 추적기 탑재) ---
def analyze_recipe_image_with_ai(api_key, images):
    genai.configure(api_key=api_key)
    models = ['gemini-2.5-flash']
    prompt = """
    이 음식 사진들을 분석해서 [요리 이름], [필수 재료], [조리법]을 추출해.
    절대 다른 설명이나 인사말은 하지 말고, 오직 아래 JSON 형식으로만 응답해.
    {"name": "요리명", "ingredients": "재료1, 재료2", "steps": "조리법"}
    """
    
    last_error = ""
    for m in models:
        try:
            # 🔥 [핵심] 최신 기능: AI가 무조건 JSON 형식으로만 대답하도록 시스템 강제
            model = genai.GenerativeModel(m, generation_config={"response_mime_type": "application/json"})
            response = model.generate_content([prompt] + images)
            
            text = response.text.replace("```json", "").replace("```", "").strip()
            
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # 혹시라도 파싱 에러가 나면 정규식으로 알맹이만 구출 시도
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                else:
                    raise ValueError(f"JSON 파싱 실패 (응답 일부): {text[:50]}...")
                    
        except Exception as e:
            # 에러가 나면 조용히 넘어가지 않고, last_error 변수에 내용을 적어둡니다.
            last_error = str(e)
            continue
            
    # 🔥 [핵심] 모든 모델이 실패했다면, 진짜 실패 원인을 화면에 띄워줍니다.
    st.error(f"🚨 [AI 통신/분석 실패] 상세 원인: {last_error}")
    return None
    
# --- AI 메뉴 추천 ---
def get_ai_recommendations(api_key, pantry_list, recipe_list, excluded_list):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    pantry_set = normalize_pantry(pantry_list)
    filtered_recipes = [r for r in recipe_list if r["요리명"] not in excluded_list]

    scored = []
    for r in filtered_recipes:
        score = score_recipe(pantry_set, r)
        if score > 0: scored.append((r, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    if not scored and filtered_recipes: scored = [(filtered_recipes[0], 0)]
    elif not scored and not filtered_recipes: return {"recommendations": []}

    top_recipe = scored[0][0]
    
    raw_ingredients = [x.strip() for x in str(top_recipe['필수재료']).split(",")]
    missing_items = [raw_ing for raw_ing in raw_ingredients if not check_is_present(raw_ing, pantry_set)]
    missing_text = ", ".join(missing_items) if missing_items else "없음 (완벽해요!)"

    prompt = f"""
    너는 긍정적인 요리 친구야.
    추천 메뉴: {top_recipe['요리명']}
    부족한 재료: {missing_text}
    이 요리를 추천하는 이유를 한 문장으로 긍정적으로 말해줘.
    출력 형식(JSON):
    {{ "recommendations": [ {{ "name": "{top_recipe['요리명']}", "reason": "AI의 추천 멘트", "missing": "{missing_text}" }} ] }}
    """
    try:
        response = model.generate_content(prompt)
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match: return json.loads(match.group(0))
        else: raise ValueError("No JSON")
    except:
        return {
            "recommendations": [
                {
                    "name": top_recipe["요리명"],
                    "reason": "재료 조합상 현재 가장 해먹기 좋은 메뉴입니다! 😋",
                    "missing": missing_text
                }
            ]
        }

# --- [수정됨] 콜백 함수 (보관장소 처리 추가) ---
def handle_add_pantry():
    n = st.session_state.get('input_name', "").strip()
    d = st.session_state.get('input_date', date.today())
    is_sauce = st.session_state.get('chk_sauce', False)
    is_seasoning = st.session_state.get('chk_season', False)
    storage_raw = st.session_state.get('input_storage', '🧊 냉장고')
    storage = "냉동실" if "냉동실" in storage_raw else "냉장고"

    if n:
        final_d = "" if (is_sauce or is_seasoning) else str(d)
        current_df = load_data(PANTRY_TAB, ["재료명", "유통기한", "보관장소"]) # 컬럼 추가
        
        if n in current_df['재료명'].values:
            current_df.loc[current_df['재료명'] == n, '유통기한'] = final_d
            current_df.loc[current_df['재료명'] == n, '보관장소'] = storage
            save_data_overwrite(current_df, PANTRY_TAB)
            st.session_state['toast_msg'] = f"🔄 '{n}' 정보 업데이트!"
        else:
            add_row_to_sheet([n, final_d, storage], PANTRY_TAB)
            st.session_state['toast_msg'] = f"{storage_raw[:2]} '{n}' {storage}에 쏙!"
        
        st.session_state['input_name'] = ""
        st.session_state['chk_sauce'] = False
        st.session_state['chk_season'] = False
    else:
        st.session_state['warning_msg'] = "재료 이름을 적어주세요!"

# --- 앱 초기 설정 ---
st.set_page_config(page_title="오늘 뭐 먹지?", page_icon="🍳", layout="wide") 
apply_cute_style() 

if 'toast_msg' not in st.session_state: st.session_state['toast_msg'] = None
if 'warning_msg' not in st.session_state: st.session_state['warning_msg'] = None
if st.session_state['toast_msg']: st.toast(st.session_state['toast_msg'], icon="✅"); st.session_state['toast_msg'] = None
if st.session_state['warning_msg']: st.warning(st.session_state['warning_msg']); st.session_state['warning_msg'] = None

if 'current_view' not in st.session_state: st.session_state['current_view'] = '요리하기'
if 'highlight_items' not in st.session_state: st.session_state['highlight_items'] = []
if 'ai_result' not in st.session_state: st.session_state['ai_result'] = {"name": "", "ingredients": "", "steps": ""}
if 'ai_recommendation' not in st.session_state: st.session_state['ai_recommendation'] = None
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

# [수정됨] 보관장소 데이터 로드 및 결측치 처리 (기존 데이터 호환)
pantry_df = load_data(PANTRY_TAB, ["재료명", "유통기한", "보관장소"])
if not pantry_df.empty:
    pantry_df['유통기한'] = pd.to_datetime(pantry_df['유통기한'], errors='coerce').dt.date
    pantry_df['보관장소'] = pantry_df['보관장소'].replace("", "냉장고").fillna("냉장고")

recipe_df = load_data(RECIPE_TAB, ["요리명", "필수재료", "링크", "조리법"])
today = date.today()

st.markdown('<div class="main-title">🍳 오늘 뭐 먹지?</div>', unsafe_allow_html=True)

# ==========================================
# 뷰 1: 요리하기
# ==========================================
if st.session_state['current_view'] == "요리하기":
    st.header("👨‍🍳 AI 셰프의 추천")
    
    if pantry_df.empty or recipe_df.empty:
         st.warning("냉장고가 비었거나 레시피북이 비어있어요! 데이터를 먼저 채워주세요.")
    else:
        st.info("💡 파이썬과 AI가 협동해서 최적의 메뉴를 골라줍니다.")
        btn_text = "🎲 다음 메뉴 추천해줘!" if st.session_state['shown_recipes'] else "🧑‍🍳 AI! 첫 번째 메뉴 추천해줘"
        
        if st.button(btn_text, use_container_width=True):
            with st.spinner("메뉴 선정 중... 🧐"):
                key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                if key:
                    pantry_list = pantry_df['재료명'].tolist()
                    recipe_list = recipe_df[['요리명', '필수재료', '링크', '조리법']].to_dict('records')
                    
                    result = get_ai_recommendations(key, pantry_list, recipe_list, st.session_state['shown_recipes'])
                    new_recs = result.get('recommendations', [])
                    
                    if not new_recs and st.session_state['shown_recipes']:
                        st.toast("🔄 한 바퀴 다 돌았네요! 처음부터 다시 추천합니다.")
                        st.session_state['shown_recipes'] = []
                        result = get_ai_recommendations(key, pantry_list, recipe_list, [])
                        new_recs = result.get('recommendations', [])

                    st.session_state['ai_recommendation'] = new_recs
                    
                    for r in new_recs:
                        if r['name'] not in st.session_state['shown_recipes']:
                            st.session_state['shown_recipes'].append(r['name'])
                else:
                    st.error("API 키가 없어요!")

        if st.session_state['ai_recommendation'] is not None:
            recs = st.session_state['ai_recommendation']
            if len(recs) == 0:
                st.warning("🥲 추천할 메뉴가 정말 없어요.")
            else:
                for rec in recs:
                    with st.expander(f"🍽️ **{rec['name']}** (추천!)", expanded=True):
                        st.markdown(f"**🗣️ AI 의견:** {rec['reason']}")
                        
                        missing_info = rec.get('missing', '없음')
                        if missing_info and missing_info != '없음 (완벽해요!)':
                             st.markdown(f"""
                            <div style="background-color:#FFF3E0; padding:10px; border-radius:10px; margin-bottom:10px; border:1px solid #FFCC80;">
                                ⚠️ <b>부족한 재료:</b> {missing_info} <br>
                                <span style="font-size:0.8em; color:#666;">(기본 양념이나 부재료는 생략/대체 가능해요!)</span>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.success("✨ 모든 재료가 완벽하게 준비되어 있어요!")

                        original_data = recipe_df[recipe_df['요리명'] == rec['name']]
                        if not original_data.empty:
                            original = original_data.iloc[0]
                            st.divider()
                            
                            formatted_steps = format_steps(original['조리법'])
                            st.text(formatted_steps)
                            
                            if original['링크']: st.markdown(f"👉 [레시피 링크]({original['링크']})")
                            
                            if st.button(f"😋 {rec['name']} 요리 완료! (재료 소진 알림)", key=f"cook_{rec['name']}"):
                                 st.session_state['highlight_items'] = [x.strip() for x in str(original['필수재료']).split(',')]
                                 st.session_state['current_view'] = "냉장고 관리"
                                 st.rerun()

# ==========================================
# 뷰 2: 냉장고 관리 (냉장고/냉동실 분리)
# ==========================================
elif st.session_state['current_view'] == "냉장고 관리":
    st.header("🧊 우리집 냉장고")
    c1, c2 = st.columns([1.5, 1])
    
    with c1:
        if st.session_state['highlight_items']:
            st.error(f"🔥 방금 사용한 재료 (정리 필요): {', '.join(st.session_state['highlight_items'])}")
            if st.button("알림 끄기"): st.session_state['highlight_items'] = []; st.rerun()
            
        # [NEW] 냉장고 / 냉동실 탭 생성
        tab_fridge, tab_freezer = st.tabs(["🧊 냉장고", "❄️ 냉동실"])
        
        # 탭별 재료 렌더링을 위한 반복문
        for storage_val, current_tab in zip(["냉장고", "냉동실"], [tab_fridge, tab_freezer]):
            with current_tab:
                if not pantry_df.empty:
                    sub_df = pantry_df[pantry_df['보관장소'] == storage_val]
                    if sub_df.empty:
                        st.info("비어있습니다! 재료를 채워주세요.")
                    else:
                        for idx, row in sub_df.iterrows():
                            icon = "🔴" if row['재료명'] in st.session_state['highlight_items'] else "🟢"
                            
                            if pd.isna(row['유통기한']) or str(row['유통기한']).strip() == "": 
                                d_day_str = "(소스/조미료)"
                                display_style = "color:#8D6E63;" 
                            else:
                                days_left = (row['유통기한'] - today).days
                                d_day_str = f"({days_left}일 남음)" if days_left >= 0 else "(지남!!)"
                                display_style = "color:#FF7043;" if days_left < 3 else "color:#8D6E63;"

                            with st.container(border=True):
                                sc1, sc2 = st.columns([5, 1])
                                sc1.markdown(f"**{icon} {row['재료명']}** <span style='{display_style} font-size:0.9em; margin-left:10px;'>{d_day_str}</span>", unsafe_allow_html=True)
                                with sc2: 
                                    if st.button("🗑️", key=f"d_{idx}"): 
                                        pantry_df = pantry_df.drop(idx)
                                        save_data_overwrite(pantry_df, PANTRY_TAB)
                                        st.rerun()

    with c2:
        st.subheader("🛒 재료 채우기")
        db1, db2 = st.columns([1, 1])
        if db1.button("📅 +1주"): st.session_state['input_date'] = today + timedelta(weeks=1); st.rerun()
        if db2.button("📅 +1달"): st.session_state['input_date'] = today + timedelta(days=30); st.rerun()
        
        st.text_input("재료명 (필수!)", key="input_name")
        
        # [NEW] 보관 장소 선택 (라디오 버튼)
        st.radio("보관 장소", ["🧊 냉장고", "❄️ 냉동실"], horizontal=True, key="input_storage")
        
        c1, c2 = st.columns(2)
        with c1: st.checkbox("🥫 소스", key="chk_sauce")
        with c2: st.checkbox("🧂 조미료", key="chk_season")
        st.date_input("유통기한", key="input_date")
        
        st.write("")
        st.button("✨ 보관함에 넣기", use_container_width=True, on_click=handle_add_pantry)

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
                if not key: 
                    st.error("API 키가 필요합니다!")
                else:
                    with st.spinner("AI가 사진을 뚫어져라 분석 중입니다... 🧐"):
                        imgs = [Image.open(f) for f in files]
                        res = analyze_recipe_image_with_ai(key, imgs)
                        
                        # 🔥 실패했을 때도 사용자에게 알려주기
                        if res: 
                            st.session_state['ai_result'] = res
                            st.success("사진 분석 성공! 아래 폼을 확인해주세요 ✨")
                            st.rerun()
                        else:
                            st.error("😭 AI가 사진에서 레시피를 추출하지 못했어요. 다른 사진으로 시도하거나 직접 입력해주세요!")

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
            edited = st.data_editor(recipe_df, num_rows="dynamic", use_container_width=True, key="recipe_editor")
            if st.button("💾 저장"):
                clean = edited[edited['요리명'].notna() & (edited['요리명'] != "")].drop_duplicates(subset=['요리명', '링크'])
                save_data_overwrite(clean, RECIPE_TAB); st.session_state['toast_msg'] = "저장 완료!"; st.rerun()


