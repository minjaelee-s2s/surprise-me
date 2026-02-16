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
# 🔥 [UPDATED] 재료 분류 및 텍스트 정리 도구
# ===============================

IGNORABLE_INGREDIENTS = {
    "대파", "쪽파", "파", "양파", "마늘", "다진마늘",
    "청양고추", "고추", "당근", "홍고추",
    "고춧가루", "후추", "참깨", "깨",
    "간장", "진간장", "국간장", "고추장", "된장", "쌈장",
    "설탕", "올리고당", "물엿", "맛술", "미림",
    "참기름", "들기름", "식용유", "소금", "물", "육수", "치킨스톡", "굴소스"
}

PORK_EQUIVALENTS = {"목살", "삼겹살", "앞다리살", "뒷다리살", "대패삼겹살", "돼지고기"}

def normalize_pantry(pantry_list):
    pantry = set(pantry_list)
    if any(meat in pantry for meat in PORK_EQUIVALENTS):
        pantry.add("돼지고기")
    return pantry

def split_ingredients(ingredient_string):
    """재료를 Main과 Sub로 분리하고, 리스트로 반환"""
    ingredients = [x.strip() for x in str(ingredient_string).split(",")]
    main, sub = [], []
    for ing in ingredients:
        if ing in IGNORABLE_INGREDIENTS:
            sub.append(ing)
        elif ing in PORK_EQUIVALENTS:
            main.append("돼지고기")
        else:
            main.append(ing)
    return list(set(main)), sub, ingredients # 전체 리스트도 반환

def score_recipe(pantry_set, recipe_row):
    main, _, _ = split_ingredients(recipe_row["필수재료"])
    return len(pantry_set & set(main))

def format_steps(text):
    """
    줄글로 된 레시피를 번호 매겨진 깔끔한 형태로 변환
    """
    text = str(text).strip()
    # 이미 번호가 있는 경우 (1. 또는 1)) 줄바꿈만 확실하게
    text = re.sub(r'(\d+[\.\)])', r'\n\1', text)
    
    # 번호가 전혀 없는 줄글인 경우, 마침표 기준으로 나눔
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
        </style>
    """, unsafe_allow_html=True)

# --- 구글 시트 연결 ---
def get_gsheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 데이터 로드 ---
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

# --- AI 이미지 분석 ---
def analyze_recipe_image_with_ai(api_key, images):
    genai.configure(api_key=api_key)
    models = ['gemini-1.5-flash', 'gemini-2.0-flash']
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

# --- AI 메뉴 추천 (파이썬이 재료 분석 -> AI는 멘트만) ---
def get_ai_recommendations(api_key, pantry_list, recipe_list, excluded_list):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    pantry_set = normalize_pantry(pantry_list)

    # 1. 제외 레시피 필터링
    filtered_recipes = [r for r in recipe_list if r["요리명"] not in excluded_list]

    # 2. Python 점수 계산
    scored = []
    for r in filtered_recipes:
        score = score_recipe(pantry_set, r)
        if score > 0:
            scored.append((r, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    # 3. 추천 대상 없으면 빈 리스트 반환 (리셋 유도)
    if not scored and filtered_recipes:
        scored = [(filtered_recipes[0], 0)]
    elif not scored and not filtered_recipes:
        return {"recommendations": []}

    top_recipe = scored[0][0]
    
    # 🔥 [핵심 개선] 파이썬이 '부족한 재료'를 직접 계산! (AI한테 안 물어봄)
    _, _, all_ingredients = split_ingredients(top_recipe['필수재료'])
    
    # 냉장고에 없는 재료 찾기 (이름 매칭)
    # 단순화를 위해 정확히 일치하지 않는 것들을 찾음
    # (고기류는 이미 로직상 통과했으니, 여기서는 표시용으로 단순 비교)
    missing_items = [
        ing for ing in all_ingredients 
        if ing not in pantry_list and ing not in IGNORABLE_INGREDIENTS
        # 돼지고기류는 냉장고에 고기가 하나라도 있으면 missing 아님 처리
        and not (ing in PORK_EQUIVALENTS and any(p in PORK_EQUIVALENTS for p in pantry_list))
    ]
    
    missing_text = ", ".join(missing_items) if missing_items else "없음 (완벽해요!)"

    # AI에게 멘트 요청
    prompt = f"""
    너는 긍정적인 요리 친구야.
    
    추천 메뉴: {top_recipe['요리명']}
    내 상황: {missing_text} 재료가 조금 부족할 수도 있어.
    
    이 요리를 추천하는 이유를 한 문장으로 긍정적으로 말해줘.
    부족한 재료가 있어도 "괜찮아요, 응용해서 만들면 돼요!"라고 격려해줘.

    출력 형식(JSON):
    {{
      "recommendations": [
        {{
          "name": "{top_recipe['요리명']}",
          "reason": "AI의 추천 멘트",
          "missing": "{missing_text}"
        }}
      ]
    }}
    """

    try:
        response = model.generate_content(prompt)
        # JSON 파싱 강화 (regex로 JSON 블록만 추출)
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        else:
            raise ValueError("No JSON found")
    except:
        # AI 응답 실패 시, 파이썬이 계산한 정확한 데이터로 대체
        return {
            "recommendations": [
                {
                    "name": top_recipe["요리명"],
                    "reason": "파이썬 분석 결과: 현재 재료로 가장 적합한 메뉴입니다! (AI 응답 지연)",
                    "missing": missing_text
                }
            ]
        }

# --- 콜백 함수 ---
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
            st.session_state['toast_msg'] = f"🔄 '{n}' 업데이트!"
        else:
            add_row_to_sheet([n, final_d], PANTRY_TAB)
            st.session_state['toast_msg'] = f"🧊 '{n}' 냉장고에 쏙!"
        
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
# 뷰 1: 요리하기
# ==========================================
if st.session_state['current_view'] == "요리하기":
    st.header("👨‍🍳 AI 셰프의 추천")
    
    if pantry_df.empty or recipe_df.empty:
         st.warning("냉장고가 비었거나 레시피북이 비어있어요! 데이터를 먼저 채워주세요.")
    else:
        st.info("💡 AI가 냉장고 속 재료와 대체 가능성을 분석해서 메뉴를 골라줍니다.")
        
        btn_text = "🎲 다음 메뉴 추천해줘!" if st.session_state['shown_recipes'] else "🧑‍🍳 AI! 첫 번째 메뉴 추천해줘"
        
        if st.button(btn_text, use_container_width=True):
            with st.spinner("메뉴 선정 중... (Python 분석 + AI 멘트 🧐)"):
                key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                if key:
                    pantry_list = pantry_df['재료명'].tolist()
                    recipe_list = recipe_df[['요리명', '필수재료', '링크', '조리법']].to_dict('records')
                    
                    # 1. 추천 받기
                    result = get_ai_recommendations(key, pantry_list, recipe_list, st.session_state['shown_recipes'])
                    new_recs = result.get('recommendations', [])
                    
                    # 2. 리셋 로직
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
                        
                        # [개선] 부족한 재료를 명확하게 표시
                        missing_info = rec.get('missing', '없음')
                        if missing_info and missing_info != '없음':
                             st.markdown(f"""
                            <div style="background-color:#FFF3E0; padding:10px; border-radius:10px; margin-bottom:10px; border:1px solid #FFCC80;">
                                ⚠️ <b>부족한 재료:</b> {missing_info} <br>
                                <span style="font-size:0.8em; color:#666;">(파, 양파 등은 없어도 맛낼 수 있어요!)</span>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.success("✨ 모든 재료가 완벽하게 준비되어 있어요!")

                        original_data = recipe_df[recipe_df['요리명'] == rec['name']]
                        if not original_data.empty:
                            original = original_data.iloc[0]
                            st.divider()
                            
                            # [개선] 레시피 텍스트 포맷팅 (번호 매기기)
                            formatted_steps = format_steps(original['조리법'])
                            st.text(formatted_steps)
                            
                            if original['링크']: st.markdown(f"👉 [레시피 링크]({original['링크']})")
                            
                            if st.button(f"😋 {rec['name']} 요리 완료! (재료 소진)", key=f"cook_{rec['name']}"):
                                 st.session_state['highlight_items'] = [x.strip() for x in str(original['필수재료']).split(',')]
                                 st.session_state['current_view'] = "냉장고 관리"
                                 st.rerun()

# ==========================================
# 뷰 2: 냉장고 관리 & 뷰 3: 레시피 관리 (기존 유지)
# ==========================================
elif st.session_state['current_view'] == "냉장고 관리":
    # (기존 코드와 동일)
    st.header("🧊 우리집 냉장고")
    c1, c2 = st.columns([1.5, 1])
    with c1:
        if st.session_state['highlight_items']:
            st.error(f"🔥 방금 사용한 재료: {', '.join(st.session_state['highlight_items'])}")
            if st.button("알림 끄기"): st.session_state['highlight_items'] = []; st.rerun()
        if not pantry_df.empty:
            for idx, row in pantry_df.iterrows():
                icon = "🔴" if row['재료명'] in st.session_state['highlight_items'] else "🟢"
                d_day_str = "(소스/조미료)" if pd.isna(row['유통기한']) else (f"({(row['유통기한'] - today).days}일 남음)" if (row['유통기한'] - today).days >= 0 else "(지남!!)")
                display_style = "color:#8D6E63;" if pd.isna(row['유통기한']) or (row['유통기한'] - today).days >= 3 else "color:#FF7043;"
                
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
        if db1.button("📅 +1주"): st.session_state['input_date'] = today + timedelta(weeks=1); st.rerun()
        if db2.button("📅 +1달"): st.session_state['input_date'] = today + timedelta(days=30); st.rerun()
        st.text_input("재료명 (필수!)", key="input_name")
        c1, c2 = st.columns(2)
        with c1: st.checkbox("🥫 소스", key="chk_sauce")
        with c2: st.checkbox("🧂 조미료", key="chk_season")
        st.date_input("유통기한", key="input_date")
        st.write(""); st.button("✨ 냉장고에 넣기", use_container_width=True, on_click=handle_add_pantry)

elif st.session_state['current_view'] == "레시피 관리":
    # (기존 코드와 동일)
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
            st.write(""); st.form_submit_button("✨ 저장", on_click=lambda: (add_row_to_sheet([rn, ri, rl, rs], RECIPE_TAB), st.session_state.update({'toast_msg': "저장 완료!", 'ai_result': {}})))
    with t2:
        if not recipe_df.empty:
            edited = st.data_editor(recipe_df, num_rows="dynamic", use_container_width=True, key="recipe_editor")
            if st.button("💾 저장"):
                clean = edited[edited['요리명'].notna() & (edited['요리명'] != "")].drop_duplicates(subset=['요리명', '링크'])
                save_data_overwrite(clean, RECIPE_TAB); st.session_state['toast_msg'] = "저장 완료!"; st.rerun()
