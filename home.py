import streamlit as st

# 페이지 설정
# st.set_page_config(
#     page_title="Script Mate",
#     page_icon="🎬",
#     layout="wide"
# )

# 제목 및 스타일
st.title("🎬 Script Mate")
st.subheader("당신의 대본 작업을 완벽하게 서포트합니다.")
st.markdown("---")

# CSS 스타일 (카드 디자인)
st.markdown("""
    <style>
    .card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        height: 200px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .card:hover {
        transform: scale(1.02);
        transition: 0.3s;
        background-color: #e8ebf0;
    }
    .icon { font-size: 3rem; margin-bottom: 10px; }
    .card-title { font-size: 1.2rem; font-weight: bold; margin-bottom: 5px; color: #333;}
    .card-desc { font-size: 0.9rem; color: #666; }
    </style>
""", unsafe_allow_html=True)

# 메인 메뉴 2개 배치
col1, col2 = st.columns(2)

with col1:
    st.markdown("""
        <div class="card">
            <div class="icon">📝</div>
            <div class="card-title">Script Numbering</div>
            <div class="card-desc">PDF 대본을 업로드하면<br>자동으로 번호를 매겨드립니다.</div>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # [수정됨] 파일명: 1_script_numbering.py
    if st.button("🚀 넘버링 하러 가기", use_container_width=True):
        st.switch_page("pages/1_script_numbering.py")

with col2:
    st.markdown("""
        <div class="card">
            <div class="icon">🎭</div>
            <div class="card-title">Script Practice</div>
            <div class="card-desc">AI 파트너와 함께<br>실전처럼 대사를 주고받으세요.</div>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    # [수정됨] 파일명: 2_script_practice.py
    if st.button("🎤 연습 하러 가기", use_container_width=True):
        st.switch_page("pages/2_script_practice.py")

st.markdown("---")
st.info("👈 왼쪽 사이드바 메뉴를 통해서도 이동할 수 있습니다.")