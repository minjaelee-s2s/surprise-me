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

# --- 구글 시트 설정 ---
SHEET_NAME = "cooking_db"
PANTRY_TAB = "pantry"
RECIPE_TAB = "recipes"

# --- 단위 변환 설정 (계란 1판 = 18개) ---
UNIT_MAP = {"판": 18, "다발": 10, "봉": 1, "개": 1, "인분": 1}

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

# --- 구글 시트 연결 함수 ---
def get_gsheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- 데이터 로드 ---
def load_data(tab_name, columns):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=columns)
        return df
    except Exception as e:
        return pd.DataFrame(columns=columns)

# --- 데이터 저장 (수정/삭제용 - 덮어쓰기) ---
def save_data_overwrite(df, tab_name):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        sheet.clear() 
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"저장 실패: {e}")

# --- 데이터 추가 (추가용 - 안전하게 한 줄 붙이기) ---
def add_row_to_sheet(row_data, tab_name):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).worksheet(tab_name)
        sheet.append_row(row_data)
    except Exception as e:
        st.error(f"추가 실패: {e}")

def parse_quantity(text_qty):
    if not text_qty or str(text_qty).strip() == "": return 1
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
    응답 형식(JSON) 예시: {"name": "요리명", "ingredients": "재료1, 재료2", "steps": "1. 과정"}
    만약 이미지에서 레시피 정보를 찾을 수 없다면 모든 필드를 비워주세요.
    """
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            content = [prompt] + images
            response = model.generate_content(content)
            return json.loads(response.text.replace("```json", "").replace("```", ""))
        except Exception: continue
    st.error("❌ 분석 실패. API 키 확인 필요.")
    return None

# --- 앱 초기 설정 ---
st.set_page_config(page_title="오늘 뭐 먹지?", page_icon="🍳", layout="wide") 
apply_cute_style() 

# [NEW] 토스트 메시지 처리 (새로고침 후에도 메시지가 뜨도록 세션 상태 활용)
if 'toast_msg' not in st.session_state: st.session_state['toast_msg'] = None
if st.session_state['toast_msg']:
    st.toast(st.session_state['toast_msg'], icon="✅") # 화면에 알림 띄우기
    st.session_state['toast_msg'] = None # 알림 띄웠으니 초기화

if 'current_view' not in st.session_state: st.session_state['current_view'] = '요리하기'
if 'highlight_items' not in st.session_state: st.session_state['highlight_items'] = []
if 'ai_result' not in st.session_state: st.session_state['ai_result'] = {"name": "", "ingredients": "", "steps": ""}

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
        st.success("✨ AI 키 연결됨!")
    else:
        api_key_input = st.text_input("🔑 Gemini API Key", type="password")
        if api_key_input: os.environ["GEMINI_API_KEY"] = api_key_input

# --- 데이터 불러오기 ---
pantry_df = load_data(PANTRY_TAB, ["재료명", "수량", "유통기한"])
recipe_df = load_data(RECIPE_TAB, ["요리명", "필수재료", "링크", "조리법"])
today = date.today()

if not pantry_df.empty:
    pantry_df['유통기한'] = pd.to_datetime(pantry_df['유통기한'], errors='coerce').dt.date
    pantry_df['수량'] = pd.to_numeric(pantry_df['수량'], errors='coerce').fillna(1).astype(int)

st.markdown('<div class="main-title">🍳 오늘 뭐 먹지?</div>', unsafe_allow_html=True)

# ==========================================
# 뷰 1: 요리하기
# ==========================================
if st.session_state['current_view'] == "요리하기":
    st.header("😋 추천 메뉴")
    my_ingredients = set(pantry_df['재료명'].str.strip().tolist()) if not pantry_df.empty else set()
    possible_menus = []
    
    if not recipe_df.empty:
        for index, row in recipe_df.iterrows():
            if pd.isna(row['필수재료']) or str(row['필수재료']).strip() == "": continue
            needed = set([x.strip() for x in str(row['필수재료']).split(',')])
            missing = needed - my_ingredients
            if len(missing) == 0: row['부족한재료'] = []; possible_menus.append(row)
            elif len(missing) <= 2: row['부족한재료'] = list(missing); possible_menus.append(row)

    if possible_menus:
        st.write("")
        if st.button("🎲 랜덤 메뉴 추천받기!", use_container_width=True): 
            st.session_state['selected_menu'] = random.choice(possible_menus)
        st.write("")

        if 'selected_menu' in st.session_state:
            menu = st.session_state['selected_menu']
            st.info(f"✨ 추천 메뉴: **{menu['요리명']}** ✨")
            if menu['부족한재료']: st.warning(f"⚠️ 부족한 재료: {', '.join(menu['부족한재료'])}")
            with st.expander("📜 조리법 펼쳐보기", expanded=True):
                st.text(str(menu['조리법']).replace("\\n", "\n"))
                if "http" in str(menu['링크']) and len(str(menu['링크'])) > 8:
                    st.markdown(f"👉 [더 자세히 보기]({menu['링크']})")
                st.write("")
                if st.button("😋 요리 완료! (재료 쓰기)", use_container_width=True):
                    st.session_state['highlight_items'] = [x.strip() for x in str(menu['필수재료']).split(',')]
                    st.session_state['current_view'] = "냉장고 관리"
                    st.rerun()
    else: st.warning("냉장고가 텅 비었거나 레시피가 부족해요! 🛒")

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
                if pd.isna(row['유통기한']): d_day_str = "(소스/조미료)"; display_style = "color:#8D6E63;" 
                else:
                    try:
                        d_day = (row['유통기한'] - today).days
                        d_day_str = f"({d_day}일 남음)" if d_day >= 0 else "(지남!!)"
                        display_style = "color:#FF7043;" if d_day < 3 else "color:#8D6E63;"
                    except: d_day_str = ""; display_style = ""

                with st.container(border=True):
                    sc1, sc2, sc3, sc4 = st.columns([3, 1, 1, 1])
                    sc1.markdown(f"**{icon} {row['재료명']}** : {row['수량']}개 <span style='{display_style} font-size:0.8em'>{d_day_str}</span>", unsafe_allow_html=True)
                    
                    with sc2: 
                        if st.button("➕", key=f"p{idx}"): 
                            pantry_df.at[idx, '수량'] += 1
                            save_data_overwrite(pantry_df, PANTRY_TAB); st.rerun()
                    with sc3: 
                        if st.button("➖", key=f"m{idx}"):
                             if pantry_df.at[idx, '수량'] > 0: pantry_df.at[idx, '수량'] -= 1
                             save_data_overwrite(pantry_df, PANTRY_TAB); st.rerun()
                    with sc4: 
                        if st.button("🗑️", key=f"d{idx}"): 
                            pantry_df = pantry_df.drop(idx)
                            save_data_overwrite(pantry_df, PANTRY_TAB); st.rerun()

    with c2:
        st.subheader("🛒 재료 채우기")
        with st.form("add"):
            n = st.text_input("재료명 (필수!)")
            st.caption("👇 소스나 조미료면 체크! (날짜 신경 안 써도 돼요)")
            chk_col1, chk_col2 = st.columns(2)
            with chk_col1: is_sauce = st.checkbox("🥫 소스")
            with chk_col2: is_seasoning = st.checkbox("🧂 조미료")
            col_q, col_d = st.columns(2)
            with col_q: q = st.text_input("수량", placeholder="예: 1판 (18개)")
            with col_d: d = st.date_input("유통기한", value=today + timedelta(days=7))
            
            st.write("") 
            if st.form_submit_button("✨ 냉장고에 넣기", use_container_width=True):
                if n:
                    if is_sauce or is_seasoning: final_q = 1; final_d = "" 
                    else: final_q = parse_quantity(q); final_d = str(d)
                    
                    add_row_to_sheet([n, final_q, final_d], PANTRY_TAB)
                    # [NEW] 저장 성공 메시지 설정
                    st.session_state['toast_msg'] = f"🧊 '{n}' 저장 완료! 냉장고로 슝~"
                    st.rerun()
                else: st.warning("재료 이름은 꼭 적어주세요! 🥺")

# ==========================================
# 뷰 3: 레시피 관리
# ==========================================
elif st.session_state['current_view'] == "레시피 관리":
    st.header("📖 나만의 레시피북")
    t1, t2 = st.tabs(["➕ 레시피 등록", "📝 목록 보기"])
    with t1:
        with st.expander("🤖 사진으로 찰칵! 자동 입력", expanded=True):
            files = st.file_uploader("요리 사진을 올려주세요!", accept_multiple_files=True)
            if files:
                imgs = [Image.open(f) for f in files]
                st.image(imgs, width=100)
                st.write("")
                if st.button("🪄 AI, 분석해줘!", use_container_width=True):
                    key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
                    if not key: st.error("API 키가 필요해요 💦")
                    else:
                        with st.spinner("AI가 열심히 분석 중... 🧐"):
                            res = analyze_recipe_image_with_ai(key, imgs)
                            if res: st.session_state['ai_result'] = res; st.success("분석 성공! 아래 내용을 확인해주세요 🎉"); st.rerun()

        with st.form("rec_form"):
            default = st.session_state['ai_result']
            rn = st.text_input("요리 이름", value=default.get('name', ''))
            ri = st.text_input("필수 재료 (쉼표로 구분)", value=default.get('ingredients', ''))
            rs = st.text_area("조리법", value=default.get('steps', ''), height=150)
            rl = st.text_input("참고 링크 (선택)")
            st.write("")
            if st.form_submit_button("✨ 레시피북에 저장", use_container_width=True):
                add_row_to_sheet([rn, ri, rl, rs], RECIPE_TAB)
                st.session_state['ai_result'] = {}
                # [NEW] 저장 성공 메시지 설정
                st.session_state['toast_msg'] = f"📖 '{rn}' 레시피북에 저장 완료!"
                st.rerun()
    with t2:
        if not recipe_df.empty:
            edited_df = st.data_editor(recipe_df, num_rows="dynamic", use_container_width=True, key="recipe_editor", column_config={"링크": st.column_config.LinkColumn("링크"), "조리법": st.column_config.TextColumn("조리법", width="large")})
            st.write("")
            if st.button("💾 변경사항 저장하기", use_container_width=True):
                # 1. 빈 줄 제거
                clean_df = edited_df[edited_df['요리명'].notna() & (edited_df['요리명'] != "")]
                # 2. 중복 제거
                deduplicated_df = clean_df.drop_duplicates(subset=['요리명', '링크'], keep='first')
                
                # 3. 저장
                save_data_overwrite(deduplicated_df, RECIPE_TAB)
                st.session_state['toast_msg'] = "💾 변경사항 저장 완료! (중복도 정리했어요)"
                st.rerun()
