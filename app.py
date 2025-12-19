import streamlit as st

# --- 1. 페이지 정의 (파일명과 메뉴명 매핑) ---
# st.Page("실제파일경로", title="보여질 메뉴명", icon="아이콘")

# (1) 메인 (아까 새로 만든 home.py)
main_page = st.Page("home.py", title="메인", icon="🏠")

# (2) 대본 넘버링 (기존 파일)
numbering_page = st.Page("pages/1_script_numbering.py", title="대본 넘버링", icon="📝")

# (3) 대본 연습 (기존 파일)
practice_page = st.Page("pages/2_script_practice.py", title="대본 연습", icon="🎭")


# --- 2. 네비게이션 설정 ---
# 목록에 페이지들을 담습니다.
pg = st.navigation([main_page, numbering_page, practice_page])


# --- 3. 공통 상단 헤더 (Top Navbar) 함수 ---
def draw_top_nav():
    st.markdown("""
        <style>
        /* 상단 버튼 스타일 조정 */
        div[data-testid="stColumn"] {
            text-align: center;
        }
        /* 모바일에서 버튼이 너무 꽉 차 보이면 간격 조정 가능 */
        [data-testid="stPageLink-NavLink"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # 3개의 컬럼으로 메뉴 배치
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.page_link(main_page, label="메인", icon="🏠", use_container_width=True)
    with col2:
        st.page_link(numbering_page, label="대본 넘버링", icon="📝", use_container_width=True)
    with col3:
        st.page_link(practice_page, label="대본 연습", icon="🎭", use_container_width=True)
    
    st.divider() # 구분선

# --- 4. 실행 (여기가 질문하신 부분!) ---
st.set_page_config(
    page_title="Script Mate", 
    layout="centered",
    initial_sidebar_state="collapsed" # 👈 모바일 배려 (여기서 한 번만 선언)
)

# 모든 페이지에 상단 네비게이션 그리기
draw_top_nav()

# 선택된 페이지 실행
pg.run()