import streamlit as st
import os
import sys
import difflib
import re
import time
import pdfplumber
import textwrap
import asyncio
import edge_tts
import nest_asyncio

# [필수] 비동기 충돌 방지
nest_asyncio.apply()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from logic import extract_script_data, scan_candidates

# --- CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    
    .main-header { font-size: 2.5rem; font-weight: 900; text-align: center; margin-bottom: 0.5rem; }
    .gradient-text {
        background: linear-gradient(90deg, #FF512F 0%, #DD2476 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .step-header { font-size: 1.3rem; font-weight: 700; color: #DD2476; margin-top: 20px; margin-bottom: 10px; }
    .info-box { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .past-msg { opacity: 0.7; }
    div.stButton > button { width: 100%; font-weight: bold; border-radius: 10px; }
    
    div[data-testid="stRadio"] > label { font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 로직 함수들 ---
def clean_text_for_comparison(text):
    text = re.sub(r'\([^)]*\)', '', text) 
    text = re.sub(r'\[[^\]]*\]', '', text) 
    text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
    return text

def check_similarity(original, user_input):
    if not user_input: return 0.0
    clean_org = clean_text_for_comparison(original)
    clean_user = clean_text_for_comparison(user_input)
    if not clean_org and not clean_user: return 100.0 
    if not clean_org or not clean_user: return 0.0
    matcher = difflib.SequenceMatcher(None, clean_org, clean_user)
    return matcher.ratio() * 100

def is_pure_direction(text):
    cleaned = clean_text_for_comparison(text)
    return len(cleaned) == 0 

# [핵심 수정] 파일을 쓰지 않고 메모리에서 바이트 스트림으로 받기
async def get_audio_bytes_stream(text, voice, rate_str):
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    mp3_data = b""
    
    # 스트림으로 데이터를 조각조각 받아서 합침 (파일 생성 X)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]
            
    return mp3_data

# --- 세션 초기화 ---
if 'script_data' not in st.session_state: st.session_state['script_data'] = []
if 'my_role' not in st.session_state: st.session_state['my_role'] = ""
if 'current_index' not in st.session_state: st.session_state['current_index'] = 0
if 'is_practice_started' not in st.session_state: st.session_state['is_practice_started'] = False
if 'prac_file_path' not in st.session_state: st.session_state['prac_file_path'] = None
if 'prac_candidates' not in st.session_state: st.session_state['prac_candidates'] = []
if 'prac_custom_roles' not in st.session_state: st.session_state['prac_custom_roles'] = []
if 'prac_analysis_done' not in st.session_state: st.session_state['prac_analysis_done'] = False
if 'last_played_index' not in st.session_state: st.session_state['last_played_index'] = -1
if 'role_gender_map' not in st.session_state: st.session_state['role_gender_map'] = {}

# --- 콜백 ---
def add_prac_custom_role():
    new_input = st.session_state.widget_prac_custom_role
    if new_input:
        new_roles = [r.strip() for r in new_input.split(',') if r.strip()]
        for role in new_roles:
            if role not in st.session_state['prac_custom_roles']:
                st.session_state['prac_custom_roles'].append(role)
        st.session_state.widget_prac_custom_role = ""

def clear_prac_custom_roles():
    st.session_state['prac_custom_roles'] = []

# ==============================================================================
# VIEW 1: 설정 화면
# ==============================================================================
if not st.session_state['is_practice_started']:
    st.markdown('<div class="main-header">🎭 <span class="gradient-text">Script Practice</span></div>', unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("📂 PDF 파일 업로드", type=['pdf'])

    if uploaded_file is not None:
        if st.session_state['prac_file_path'] is None or st.session_state.get('prac_filename') != uploaded_file.name:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                st.session_state['prac_file_path'] = tmp_file.name
                st.session_state['prac_filename'] = uploaded_file.name
                st.session_state['prac_analysis_done'] = False
                st.session_state['prac_custom_roles'] = []
                st.session_state['role_gender_map'] = {}

        # STEP 1
        st.markdown('<div class="step-header">STEP 1. 대본 형식 설정</div>', unsafe_allow_html=True)
        
        with st.expander("🔍 대본 내용 미리보기 (형식 확인용)", expanded=True):
            if st.session_state['prac_file_path']:
                with pdfplumber.open(st.session_state['prac_file_path']) as pdf:
                    total_pages = len(pdf.pages)
                    preview_page = st.number_input("확인할 페이지", min_value=1, max_value=total_pages, value=1, key="p_preview_1")
                    extracted_txt = pdf.pages[preview_page - 1].extract_text(layout=True)
                    st.text_area("텍스트 내용", extracted_txt, height=200)

        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            name_style = st.radio("이름 스타일", ('없음', '대괄호 []', '소괄호 ()', '꺽쇠 <>'), index=0)
        with col2:
            sep_label = st.radio("구분 기호", ('자동 (공백 2칸/탭)', '콜론 ( : )', '직접 입력'), index=0)
            if '자동' in sep_label: sep_style = 'calc_strict' 
            elif '콜론' in sep_label: sep_style = ':'
            else: sep_style = '직접 입력'
            custom_sep = st.text_input("기호 입력", max_chars=1) if sep_style == '직접 입력' else ""

        if st.button("🔍 등장인물 분석하기", type="primary"):
            with st.spinner("분석 중..."):
                wrapper_regex = None
                if '대괄호' in name_style: wrapper_regex = r'^\s*\[(.+?)\]'
                elif '소괄호' in name_style: wrapper_regex = r'^\s*\((.+?)\)'
                elif '꺽쇠' in name_style: wrapper_regex = r'^\s*<(.+?)>'
                separator = None
                if sep_style == 'calc_strict': separator = None
                elif sep_style == ':': separator = ':'
                elif sep_style == '직접 입력': separator = custom_sep
                
                config = {'wrapper_regex': wrapper_regex, 'separator': separator}
                st.session_state['prac_candidates'] = scan_candidates(st.session_state['prac_file_path'], config)
                st.session_state['prac_analysis_done'] = True
                st.rerun()

        # STEP 2
        if st.session_state['prac_analysis_done']:
            st.markdown('<div class="step-header">STEP 2. 배역 확정</div>', unsafe_allow_html=True)
            c1, c2 = st.columns([2, 1], gap="medium")
            selected_from_list = []
            
            with c1:
                st.markdown("**검출된 후보**")
                if st.session_state['prac_candidates']:
                    with st.container(height=300, border=True):
                        cols = st.columns(2)
                        for i, (name, cnt) in enumerate(st.session_state['prac_candidates']):
                            default_chk = True if i < 5 else False
                            if cols[i % 2].checkbox(f"{name} ({cnt})", value=default_chk, key=f"p_chk_{i}"):
                                selected_from_list.append(name)
                else:
                    st.warning("후보가 없습니다.")

            with c2:
                st.markdown("**직접 추가**")
                st.text_input("입력 (엔터)", key="widget_prac_custom_role", on_change=add_prac_custom_role)
                customs = st.session_state['prac_custom_roles']
                if customs:
                    st.caption(f"추가됨: {', '.join(customs)}")
                    if st.button("초기화", key="p_cls"):
                        clear_prac_custom_roles()
                        st.rerun()

            final_roles = sorted(list(set(selected_from_list) | set(customs)))
            
            st.markdown("<br>", unsafe_allow_html=True)
            if final_roles:
                st.markdown("##### 🚻 배역 성별 설정 (목소리 구분)")
                st.caption("선택한 배역의 성별을 지정하면, 연습 시 목소리가 자동으로 바뀝니다.")
                cols = st.columns(3)
                for i, role in enumerate(final_roles):
                    with cols[i % 3]:
                        gender = st.radio(f"**{role}**", ['여성', '남성'], horizontal=True, key=f"gender_{role}")
                        st.session_state['role_gender_map'][role] = gender
            
            st.markdown("<div class='info-box'>", unsafe_allow_html=True)
            if final_roles:
                st.markdown(f"✅ **최종 선택된 배역 ({len(final_roles)}명):** `{', '.join(final_roles)}`")
            else:
                st.markdown("선택된 배역이 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

            # STEP 3
            st.markdown('<div class="step-header">STEP 3. 연습 범위 설정</div>', unsafe_allow_html=True)
            
            if final_roles:
                my_role = st.selectbox("👤 내가 연기할 배역", final_roles)
            else:
                my_role = st.selectbox("👤 내가 연기할 배역", ["배역을 먼저 확정하세요"])
            
            st.markdown("**어디서부터 연습할까요?**")
            start_option = st.radio("시작 기준", ('처음부터', '페이지 번호로', '특정 대사/문구로'), horizontal=True)
            start_val_page = 1
            start_val_phrase = ""
            if start_option == '페이지 번호로':
                start_val_page = st.number_input("시작 페이지", min_value=1, value=1)
            elif start_option == '특정 대사/문구로':
                start_val_phrase = st.text_input("시작 문구 입력", placeholder="예: 2막 시작, 또는 첫 대사")

            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("🚀 연습 시작하기", type="primary"):
                if not final_roles:
                    st.error("배역을 선택해주세요.")
                elif not my_role or my_role == "배역을 먼저 확정하세요":
                    st.error("내 배역을 선택해주세요.")
                else:
                    with st.spinner("대본을 정리하고 있습니다..."):
                        wrapper_regex = None
                        if '대괄호' in name_style: wrapper_regex = r'^\s*\[(.+?)\]'
                        elif '소괄호' in name_style: wrapper_regex = r'^\s*\((.+?)\)'
                        elif '꺽쇠' in name_style: wrapper_regex = r'^\s*<(.+?)>'
                        separator = None
                        if sep_style == 'calc_strict': separator = None
                        elif sep_style == ':': separator = ':'
                        elif sep_style == '직접 입력': separator = custom_sep
                        
                        config = {'wrapper_regex': wrapper_regex, 'separator': separator}
                        
                        full_script = extract_script_data(
                            st.session_state['prac_file_path'], 
                            my_role, 
                            config, 
                            allowed_roles=final_roles,
                            start_page=start_val_page if start_option == '페이지 번호로' else 1,
                            start_phrase=start_val_phrase if start_option == '특정 대사/문구로' else ""
                        )
                        
                        if full_script:
                            st.session_state['script_data'] = full_script
                            st.session_state['my_role'] = my_role
                            st.session_state['current_index'] = 0
                            st.session_state['is_practice_started'] = True
                            st.rerun()
                        else:
                            st.error("대사를 추출하지 못했습니다. (시작 문구를 확인해보세요)")

# ==============================================================================
# VIEW 2: 연습 화면
# ==============================================================================
else:
    st.markdown(f'<div class="main-header">🎭 <span class="gradient-text">{st.session_state["my_role"]}</span> 연습 중</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("### 🔊 음성 설정")
        tts_enabled = st.toggle("상대 대사 읽어주기 (Edge TTS)", value=True)
        speed_val = st.slider("말하기 속도", -50, 50, 0, 10, format="%d%%")
        rate_str = f"{speed_val:+d}%"
        st.info("💡 배역 성별 설정에 따라\n목소리가 자동 변경됩니다.\n(남: 인준 / 여: 선히)")
    
    script = st.session_state['script_data']
    start_index = st.session_state['current_index']
    my_role = st.session_state['my_role']
    gender_map = st.session_state.get('role_gender_map', {})

    # 1. 과거 내역
    for i in range(start_index):
        line = script[i]
        role = line['role']
        text = line['text']
        display_text = f"**[{i+1}] {role}:** {text}"
        
        if role == my_role:
            with st.chat_message("user", avatar="👤"):
                st.markdown(f"<span class='past-msg'>{display_text}</span>", unsafe_allow_html=True)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(f"<span class='past-msg'>{display_text}</span>", unsafe_allow_html=True)

    st.markdown("---")

    # 2. 현재 & TTS 큐
    target_index = -1
    cue_line_text = ""
    cue_line_role = ""
    
    for i in range(start_index, len(script)):
        line = script[i]
        role = line['role']
        text = line['text']
        
        if role != my_role:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(f"**[{i+1}] {role}:** {text}")
            cue_line_text = text
            cue_line_role = role
        else:
            if is_pure_direction(text):
                with st.chat_message("user", avatar="👤"):
                    st.markdown(f"<span style='color:gray'>**[{i+1}] {role}:** {text} (지문 스킵)</span>", unsafe_allow_html=True)
                continue 
            else:
                target_index = i
                break 
    
    # 3. 입력창
    if target_index != -1:
        current_line = script[target_index]
        st.progress((target_index / len(script)), text=f"No. {target_index+1} / {len(script)}")
        
        st.chat_message("user", avatar="👤").write(f"**[{target_index+1}] {my_role}:** ❓❓❓")
        
        # [핵심] 오디오 재생 (메모리 스트림 방식)
        if tts_enabled and cue_line_text and st.session_state['last_played_index'] != target_index:
            try:
                speaker_gender = gender_map.get(cue_line_role, '여성')
                voice_code = "ko-KR-InJoonNeural" if speaker_gender == '남성' else "ko-KR-SunHiNeural"
                
                # 비동기 함수로 바이트 데이터 가져오기 (파일 생성 X)
                audio_bytes = asyncio.run(get_audio_bytes_stream(cue_line_text, voice_code, rate_str))
                
                # 바이트 데이터 재생
                st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                st.session_state['last_played_index'] = target_index
                
            except Exception as e:
                # 에러 발생 시 화면에 표시해서 확인
                st.error(f"오디오 재생 오류: {e}")

        wrapped_text = textwrap.fill(current_line['text'], width=45)
        with st.expander("💡 힌트 보기"): st.code(wrapped_text, language=None)

        user_input = st.chat_input("대사 입력 (숫자 입력 시 이동)")

        if user_input:
            user_input = user_input.strip()
            if user_input.isdigit():
                jump_idx = int(user_input) - 1
                if 0 <= jump_idx < len(script):
                    st.session_state['current_index'] = jump_idx
                    st.session_state['last_played_index'] = -1 
                    st.rerun()
                else:
                    st.toast(f"❌ {user_input}번 대사 없음", icon="⚠️")
            else:
                score = check_similarity(current_line['text'], user_input)
                if score >= 80:
                    st.toast(f"🎉 정답! ({score:.0f}%)", icon="✅")
                    time.sleep(0.5)
                    st.session_state['current_index'] = target_index + 1
                    st.rerun()
                else:
                    st.toast(f"❌ 땡! ({score:.0f}%)", icon="🚨")

    else:
        st.balloons()
        st.success("🎉 연습 종료!")
        if st.button("처음으로"):
            st.session_state['is_practice_started'] = False
            st.session_state['current_index'] = 0
            st.rerun()

    st.divider()
    if st.button("❌ 종료 및 설정으로"):
        st.session_state['is_practice_started'] = False
        st.rerun()