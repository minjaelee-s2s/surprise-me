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
* **🧊 Smart Pantry Inventory:** Manage ingredients and expiration dates with a mobile-first UI. (Removed quantity tracking for minimalism—focusing on "In Stock" vs "Out of Stock").
* **🤖 AI Recipe Analysis:** Upload a food photo, and **Gemini 2.0 Flash** extracts the dish name, ingredients, and recipe steps automatically.
* **☁️ Serverless Database:** Uses **Google Sheets API** for real-time data storage, ensuring data persistence without a dedicated backend server.
* **📱 Responsive Design:** Optimized for mobile view, perfect for checking the fridge status while grocery shopping.

### 🚀 Dev Log: What I Learned
This project was an exercise in understanding the **Full-Cycle of Web Development** with AI assistance.

1.  **Cloud & Database Architecture:**
    * Connected **Google Sheets** as a lightweight relational database using `gspread`.
    * Managed authentication securely via **GCP Service Accounts** and Streamlit Secrets.
2.  **API Optimization & State Management:**
    * Solved **API Rate Limiting (429 Errors)** by implementing **Caching (`@st.cache_data`)**.
    * Designed a cache-invalidation logic that only refreshes data upon updates (CRUD operations), significantly reducing API calls.
3.  **Handling Race Conditions:**
    * Refactored the data entry logic from `clear()` & `update()` to `append_row()` to prevent data loss during concurrent or network-delayed writes.
4.  **Data Integrity:**
    * Implemented robust error handling for `NaT` (Not a Time) and empty header issues to ensure the app remains crash-free.

---

<br>

## 🇰🇷 프로젝트 소개 (Korean Version)

### "오늘 냉장고에 뭐 남았지?"
미국에서 유학 생활을 하며 매번 식재료 유통기한을 놓치거나 메뉴 선정에 어려움을 겪는 저 자신을 위해 개발한 **자취생 필수 앱**입니다. 복잡한 기능은 빼고, 딱 필요한 기능만 담았습니다.

### ✨ 주요 기능
* **🧊 초간편 냉장고 관리:** 복잡한 수량 입력 없이 '재료명'과 '유통기한'만 심플하게 관리합니다.
* **🤖 AI 요리사 (Gemini):** 요리 사진만 올리면 AI가 자동으로 요리 이름, 재료, 레시피를 분석해서 정리해 줍니다.
* **☁️ 구글 시트 연동:** 앱을 꺼도 데이터가 사라지지 않도록 구글 스프레드시트를 DB로 활용했습니다.
* **📱 모바일 최적화:** 장보러 갔을 때 폰으로 바로바로 냉장고 상황을 확인할 수 있습니다.

### 🚀 개발 과정에서 배운 점 (What I Learned)
단순한 토이 프로젝트를 넘어, 실제 사용 가능한 서비스를 배포하며 기술적 문제들을 해결했습니다.

1.  **클라우드 데이터베이스 활용:** 별도의 서버 비용 없이 구글 시트 API를 활용해 **Serverless DB** 환경을 구축했습니다.
2.  **API 최적화 및 캐싱:** 구글 API의 호출 제한(Quota Limit) 문제를 해결하기 위해, 데이터를 읽어올 때 **캐싱(Caching)** 기술을 적용하여 속도를 높이고 오류를 없애는 최적화 작업을 수행했습니다.
3.  **데이터 무결성 확보:** 데이터 저장 시 발생할 수 있는 충돌(Race Condition)을 방지하기 위해 저장 로직을 개선하고, 날짜 오류(NaT) 등을 방어하는 코드를 구현했습니다.

---

## 📸 Screenshots
*(Add your app screenshots here / 여기에 앱 실행 화면을 캡처해서 넣어주세요)*
