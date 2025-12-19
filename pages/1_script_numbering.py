import streamlit as st
import os
import tempfile
import sys
import pdfplumber

# 상위 폴더의 logic.py 경로 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from logic import scan_candidates, analyze_and_get_coordinates, create_overlay_pdf, register_korean_font

# --- CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    
    /* 타이틀 스타일 복구 */
    .main-header { font-size: 2.5rem; font-weight: 900; text-align: center; margin-bottom: 0.5rem; }
    .gradient-text {
        background: linear-gradient(90deg, #4A90E2 0%, #0077B6 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    
    .step-header { font-size: 1.3rem; font-weight: 700; color: #0077B6; margin-top: 20px; margin-bottom: 10px; }
    .info-box { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    div.stButton > button { width: 100%; font-weight: bold; border-radius: 10px; min-height: 50px; }
    </style>
""", unsafe_allow_html=True)

# --- 세션 초기화 ---
if 'file_path' not in st.session_state: st.session_state['file_path'] = None
if 'candidates' not in st.session_state: st.session_state['candidates'] = []
if 'custom_roles' not in st.session_state: st.session_state['custom_roles'] = []
if 'analysis_done' not in st.session_state: st.session_state['analysis_done'] = False 

# --- 콜백 함수 ---
def add_custom_role():
    new_input = st.session_state.widget_custom_role
    if new_input:
        new_roles = [r.strip() for r in new_input.split(',') if r.strip()]
        for role in new_roles:
            if role not in st.session_state['custom_roles']:
                st.session_state['custom_roles'].append(role)
        st.session_state.widget_custom_role = ""

def clear_custom_roles():
    st.session_state['custom_roles'] = []

# --- UI 시작 ---
# [수정] 타이틀에 gradient-text 클래스 적용
st.markdown('<div class="main-header">📝 <span class="gradient-text">Script Numbering</span></div>', unsafe_allow_html=True)

# 1. 파일 업로드
uploaded_file = st.file_uploader("📂 PDF 파일 업로드", type=['pdf'])

if uploaded_file is not None:
    if st.session_state['file_path'] is None or st.session_state.get('uploaded_name') != uploaded_file.name:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            st.session_state['file_path'] = tmp_file.name
            st.session_state['uploaded_name'] = uploaded_file.name
            st.session_state['analysis_done'] = False 
            st.session_state['custom_roles'] = []

    # STEP 1: 설정 (미리보기 포함)
    st.markdown('<div class="step-header">STEP 1. 대본 형식 설정</div>', unsafe_allow_html=True)
    
    with st.expander("🔍 대본 내용 미리보기 (형식 확인용)", expanded=True):
        if st.session_state['file_path']:
            with pdfplumber.open(st.session_state['file_path']) as pdf:
                total_pages = len(pdf.pages)
                preview_page = st.number_input("확인할 페이지", min_value=1, max_value=total_pages, value=1, key='preview_p_1')
                extracted_txt = pdf.pages[preview_page - 1].extract_text(layout=True)
                st.text_area("텍스트 내용 (실제 인식 공백)", extracted_txt, height=200, help="이 내용을 보고 아래 설정을 선택하세요.")

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        name_style = st.radio("이름 스타일", ('없음 (예: 철수)', '대괄호 [철수]', '소괄호 (철수)', '꺽쇠 <철수>'), index=0)
    with col2:
        sep_label = st.radio("구분 기호", ('자동 (공백 2칸/탭 - 권장)', '콜론 ( : )', '직접 입력'), index=0)
        custom_sep = st.text_input("기호 입력", max_chars=1) if sep_label == '직접 입력' else ""

    if st.button("🔍 등장인물 분석하기", type="primary"):
        with st.spinner("설정된 규칙으로 대본을 분석 중입니다..."):
            wrapper_regex = None
            if '대괄호' in name_style: wrapper_regex = r'^\s*\[(.+?)\]'
            elif '소괄호' in name_style: wrapper_regex = r'^\s*\((.+?)\)'
            elif '꺽쇠' in name_style: wrapper_regex = r'^\s*<(.+?)>'
            
            separator = None
            if '콜론' in sep_label: separator = ':'
            elif '직접' in sep_label: separator = custom_sep
            
            config = {'wrapper_regex': wrapper_regex, 'separator': separator}
            
            st.session_state['candidates'] = scan_candidates(st.session_state['file_path'], config)
            st.session_state['analysis_done'] = True
            st.rerun()

    # STEP 2: 배역 확정
    if st.session_state['analysis_done']:
        st.markdown('<div class="step-header">STEP 2. 배역 확정</div>', unsafe_allow_html=True)
        
        candidate_list = st.session_state['candidates']
        selected_from_list = []
        
        if not candidate_list:
            st.warning("⚠️ 설정된 규칙으로 찾은 배역이 없습니다. (자동 모드는 2칸 이상 공백이 필요합니다)")
        
        c1, c2 = st.columns([2, 1], gap="medium")
        
        with c1:
            st.markdown("**검출된 후보**")
            if candidate_list:
                with st.container(height=300, border=True):
                    cols = st.columns(2)
                    for i, (name, cnt) in enumerate(candidate_list):
                        default_chk = True if i < 5 else False
                        if cols[i % 2].checkbox(f"{name} ({cnt})", value=default_chk, key=f"chk_{i}"):
                            selected_from_list.append(name)
        
        with c2:
            st.markdown("**직접 추가**")
            st.text_input("입력 (엔터로 추가)", key="widget_custom_role", on_change=add_custom_role)
            customs = st.session_state['custom_roles']
            if customs:
                st.caption(f"추가됨: {', '.join(customs)}")
                if st.button("초기화", key="cls_btn"):
                    clear_custom_roles()
                    st.rerun()
        
        final_roles = sorted(list(set(selected_from_list) | set(customs)))
        
        st.markdown("<div class='info-box'>", unsafe_allow_html=True)
        if final_roles:
            st.markdown(f"✅ **최종 선택된 배역 ({len(final_roles)}명):** `{', '.join(final_roles)}`")
        else:
            st.markdown("선택된 배역이 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

        # STEP 3: 넘버링 실행
        st.markdown('<div class="step-header">STEP 3. 넘버링 시작</div>', unsafe_allow_html=True)
        
        start_option = st.radio("시작 기준", ('처음부터', '페이지 번호로', '특정 문구로'), horizontal=True)
        start_val_page = 1
        start_val_phrase = ""
        
        if start_option == '페이지 번호로':
            start_val_page = st.number_input("시작 페이지", min_value=1, value=1)
        elif start_option == '특정 문구로':
            start_val_phrase = st.text_input("시작 문구")

        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("✨ 넘버링 실행", type="primary"):
            if not final_roles:
                st.error("배역을 최소 1명 이상 선택해야 합니다.")
            else:
                with st.spinner("작업 중..."):
                    wrapper_regex = None
                    if '대괄호' in name_style: wrapper_regex = r'^\s*\[(.+?)\]'
                    elif '소괄호' in name_style: wrapper_regex = r'^\s*\((.+?)\)'
                    elif '꺽쇠' in name_style: wrapper_regex = r'^\s*<(.+?)>'
                    
                    separator = None
                    if '콜론' in sep_label: separator = ':'
                    elif '직접' in sep_label: separator = custom_sep
                    
                    style_config = {'wrapper_regex': wrapper_regex, 'separator': separator}
                    font_name = register_korean_font()
                    
                    coords = analyze_and_get_coordinates(
                        st.session_state['file_path'],
                        final_roles,
                        style_config,
                        start_page=start_val_page,
                        start_phrase=start_val_phrase
                    )
                    
                    out_path = st.session_state['file_path'].replace(".pdf", "_numbered.pdf")
                    create_overlay_pdf(st.session_state['file_path'], out_path, coords, font_name)
                    
                    st.success("완료!")
                    with open(out_path, "rb") as f:
                        st.download_button("📥 다운로드", f.read(), f"{st.session_state['uploaded_name']}_넘버링.pdf", "application/pdf")