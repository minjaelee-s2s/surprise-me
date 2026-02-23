# 🍳 What's for Dinner Tonight? (오늘 뭐 먹지?)

> **Personal Usage** | **Vibe Coded** | **AI-Powered**

A smart pantry management & recipe recommendation app built for students living alone.
Integrates **Google Sheets** as a serverless database and utilizes **Gemini AI** to analyze food photos for automated recipe logging.

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-Database-34A853?logo=google-sheets&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini%20API-Multimodal%20AI-8E75B2?logo=google-gemini&logoColor=white)

---

## 🇺🇸 Project Overview

### "What do I have in my fridge?"
As a Korean student studying in the U.S., I faced the daily struggle of managing groceries and deciding what to cook. I built this app to solve my own problem—a **"Vibe Coded"** project focusing on practical utility and minimalist design.

*(Note: The app UI is designed in **Korean**, my native language, for personal convenience.)*

### ✨ Key Features
* **🧊 Smart Pantry Inventory:** Manage ingredients and expiration dates with a mobile-first UI, neatly categorized into Fridge and Freezer. (Removed quantity tracking for minimalism—focusing on "In Stock" vs "Out of Stock").
* **🤖 AI Recipe Analysis:** Upload a food photo, and **Gemini 2.5 Flash** extracts the dish name, ingredients, and recipe steps automatically via forced JSON output.
* **☁️ Serverless Database:** Uses **Google Sheets API** for real-time data storage, ensuring data persistence without a dedicated backend server.
* **📱 Responsive Design:** Optimized for mobile view, perfect for checking the fridge status while grocery shopping.

### 🚀 Dev Log: What I Learned
This project was an exercise in understanding the **Full-Cycle of Web Development** with AI assistance.

1.  **Cloud & Database Architecture:** Connected **Google Sheets** as a lightweight relational database using `gspread` and managed authentication securely via **GCP Service Accounts**.
2.  **API Optimization & State Management:** Solved **API Rate Limiting (429 Errors)** and strict quota limits by upgrading to the latest model endpoints and implementing robust **Caching (`@st.cache_data`)**.
3.  **Handling Race Conditions:** Refactored the data entry logic to prevent data loss during concurrent or network-delayed writes.
4.  **Data Integrity:** Implemented robust error handling for `NaT` (Not a Time) and empty header issues to ensure the app remains crash-free.

### 🚧 Limitations
* **Data Automation (Instagram Wall):** Originally intended to automatically scrape saved Instagram Reels. Due to strict anti-scraping policies, the app currently relies on semi-automated AI image parsing from user uploads.
* **Cold Start Problem:** The greedy matching algorithm can become repetitive if the user's initial recipe database is too small.

### 🔮 Future Works
* **Storage Expansion:** Adding a 'Pantry' option for room-temperature items.
* **Smart Expiration Alerts:** Highlighting items expiring in 2-3 days on the main dashboard and adding a "Cook with this" button for immediate recipe filtering.
* **Algorithm Upgrade:** Introducing randomization and 'recently eaten' penalties to prevent repetitive menu recommendations.

---

<br>

## 🇰🇷 프로젝트 소개 (Korean Version)

### "오늘 냉장고에 뭐 남았지?"
미국에서 유학 생활을 하며 매번 식재료 유통기한을 놓치거나 메뉴 선정에 어려움을 겪는 저 자신을 위해 개발한 **자취생 필수 앱**입니다. 복잡한 기능은 빼고, 딱 필요한 기능만 담았습니다.

### ✨ 주요 기능
* **🧊 초간편 냉장고 관리:** 복잡한 수량 입력 없이 '재료명'과 '유통기한'만 심플하게 관리하며, 현재 '냉장고'와 '냉동실' 탭으로 분리하여 관리할 수 있습니다.
* **🤖 AI 요리사 (Gemini):** 요리 사진(인스타 캡처본 등)만 올리면 최신 **Gemini 2.5 Flash** 모델이 자동으로 요리 이름, 재료, 조리법을 분석해서 JSON 형태로 깔끔하게 정리해 줍니다.
* **☁️ 구글 시트 연동:** 앱을 꺼도 데이터가 사라지지 않도록 구글 스프레드시트를 Serverless DB로 활용했습니다.
* **📱 모바일 최적화:** 장보러 갔을 때 폰으로 바로바로 냉장고 상황을 확인할 수 있도록 UI를 구성했습니다.

### 🚀 개발 과정에서 배운 점 (What I Learned)
단순한 토이 프로젝트를 넘어, 실제 사용 가능한 서비스를 배포하며 기술적 문제들을 해결했습니다.

1.  **클라우드 데이터베이스 활용:** 별도의 서버 유지보수 비용 없이 구글 시트 API를 활용해 데이터베이스 환경을 구축했습니다.
2.  **API 에러 대응 및 최적화:** 구글 API의 호출 제한(Quota Limit / 429 에러) 문제를 해결하기 위해 최신 모델로 마이그레이션하고, 데이터를 읽어올 때 **캐싱(Caching)** 기술을 적용하여 API 호출을 획기적으로 줄였습니다.
3.  **데이터 무결성 확보:** 데이터 저장 시 발생할 수 있는 충돌(Race Condition)을 방지하기 위해 저장 로직을 개선하고, 날짜 변환 오류(NaT) 등을 방어하는 예외 처리 코드를 구현했습니다.

### 🚧 한계점 (Limitations)
1. **데이터 수집 자동화의 한계:** 초기 기획은 인스타그램에 저장한 릴스를 링크만으로 불러오는 것이었으나, 인스타그램의 엄격한 스크래핑 차단 정책으로 인해 부득이하게 '사진 캡처 후 AI 분석'이라는 반자동화 방식을 채택했습니다.
2. **초기 데이터 부족(Cold Start) 문제:** 등록된 레시피 풀(Pool)이 적을 경우, 점수 기반 알고리즘 특성상 겹치는 재료가 많은 특정 요리(예: 콩불 등)만 반복적으로 추천되는 현상이 있습니다.

### 🔮 추후 개선 과제 (Future Works)
1. **보관 장소 세분화:** '팬트리(상온 보관)' 옵션을 추가하여 통조림, 면류, 상온 소스 등의 위치를 더욱 정확하게 관리할 예정입니다.
2. **유통기한 임박 식재료 구출 시스템:** 메인 화면에 유통기한이 2~3일 남은 재료를 띄우고, `이 재료로 요리하기` 버튼을 눌러 해당 재료가 포함된 레시피를 우선적으로 뽑아주는 기능을 기획 중입니다.
3. **추천 알고리즘 고도화:** 메뉴 추천의 다양성을 위해 알고리즘에 랜덤성을 부여하거나, 최근에 먹은 요리에는 페널티를 주는 방식으로 로직을 개선할 계획입니다.

---

## 📸 Screenshots
*(여기에 앱 실행 화면을 캡처해서 넣어주세요. ex: 냉장고 관리 탭, 메뉴 추천 탭, AI 레시피 분석 탭 등)*
