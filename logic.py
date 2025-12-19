import pdfplumber
import fitz  # PyMuPDF
import re
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile

# ---------------------------------------------------------
# 1. 공통 유틸
# ---------------------------------------------------------
def register_korean_font():
    font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'NanumGothic.ttf')
    if not os.path.exists(font_path):
        return "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont('NanumGothic', font_path))
        return 'NanumGothic'
    except:
        return "Helvetica"

# ---------------------------------------------------------
# 2. [공통] 등장인물 스캔
# ---------------------------------------------------------
def scan_candidates(pdf_path, config):
    wrapper_regex = config.get('wrapper_regex')
    separator = config.get('separator')
    
    text_content = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text(layout=True)
            if extracted: text_content += extracted + "\n"
    
    lines = text_content.split('\n')
    candidates = {}
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        found_name = None
        
        if wrapper_regex:
            match = re.match(wrapper_regex, line)
            if match: found_name = match.group(1)
        
        elif separator:
            if separator in line:
                parts = line.split(separator, 1)
                found_name = parts[0].strip()
        
        else:
            parts = re.split(r'\s{2,}|\t', line, maxsplit=1)
            if len(parts) == 2:
                found_name = parts[0].strip()

        if found_name:
            if 1 <= len(found_name) <= 15:
                candidates[found_name] = candidates.get(found_name, 0) + 1
            
    return sorted(candidates.items(), key=lambda x: x[1], reverse=True)

# ---------------------------------------------------------
# 3. [넘버링] 좌표 분석
# ---------------------------------------------------------
def analyze_and_get_coordinates(pdf_path, roles, config, start_page=1, start_phrase=""):
    wrapper_regex = config.get('wrapper_regex')
    separator = config.get('separator')
    results = []
    
    start_page_idx = max(0, start_page - 1)
    number_counter = 1
    found_start_phrase = False if start_phrase else True
    clean_start_phrase = start_phrase.replace(" ", "").replace("\t", "").replace("\n", "")
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            if page_idx < start_page_idx: continue
            
            words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=True)
            words.sort(key=lambda w: w['top'])
            
            lines_data = [] 
            if words:
                current_line = [words[0]]
                current_top = words[0]['top']
                for w in words[1:]:
                    if abs(w['top'] - current_top) < 5:
                        current_line.append(w)
                    else:
                        lines_data.append(current_line)
                        current_line = [w]
                        current_top = w['top']
                lines_data.append(current_line)
            
            for line_words in lines_data:
                line_words.sort(key=lambda w: w['x0'])
                line_text = " ".join([w['text'] for w in line_words]).strip()
                
                if not found_start_phrase and clean_start_phrase:
                    clean_line = line_text.replace(" ", "").replace("\t", "")
                    if clean_start_phrase in clean_line:
                        found_start_phrase = True
                    else:
                        continue 

                matched_role = None
                for role in roles:
                    check_pattern = re.escape(role)
                    if wrapper_regex:
                        if '(.+?)' in wrapper_regex:
                            check_pattern = config['wrapper_regex'].replace('(.+?)', re.escape(role))
                            check_pattern = check_pattern.replace('^', '').replace('\\s*', '')
                    
                    if separator:
                        full_regex_str = f"^{check_pattern}\\s*{re.escape(separator)}"
                        if re.match(full_regex_str, line_text):
                             matched_role = role
                             break
                    else:
                        strict_space_pattern = re.compile(f"^{re.escape(role)}" + r'(\s{2,}|\t)')
                        if strict_space_pattern.match(line_text):
                            matched_role = role
                            break
                        if wrapper_regex:
                             full_regex = config['wrapper_regex'].replace('(.+?)', re.escape(role))
                             if re.match(full_regex, line_text):
                                 matched_role = role
                                 break
                
                if matched_role:
                    first_word = line_words[0]
                    results.append({
                        'page': page_idx,
                        'x': first_word['x0'] - 20,
                        'y': page.height - first_word['bottom'] + 2,
                        'number': number_counter
                    })
                    number_counter += 1
    return results

# ---------------------------------------------------------
# 4. [넘버링] PDF 생성
# ---------------------------------------------------------
def create_overlay_pdf(original_pdf_path, output_path, coordinates, font_name):
    doc = fitz.open(original_pdf_path)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_overlay:
        c = canvas.Canvas(tmp_overlay.name, pagesize=A4)
        current_page = -1
        for item in coordinates:
            while current_page < item['page']:
                if current_page != -1: c.showPage()
                current_page += 1
                c.setFont(font_name, 10)
                c.setFillColorRGB(1, 0, 0)
            c.drawString(item['x'], item['y'], str(item['number']))
        c.save()
        tmp_path = tmp_overlay.name

    overlay_doc = fitz.open(tmp_path)
    for i in range(len(doc)):
        if i < len(overlay_doc):
            doc[i].show_pdf_page(doc[i].rect, overlay_doc, i)
    doc.save(output_path)
    overlay_doc.close()
    os.remove(tmp_path)

# ---------------------------------------------------------
# 5. [연습] 텍스트 추출 (지문/괄호 분리 로직 강화 🚀)
# ---------------------------------------------------------
def extract_script_data(pdf_path, my_role, config, allowed_roles=None, start_page=1, start_phrase=""):
    script_data = []
    wrapper_regex = config.get('wrapper_regex')
    separator = config.get('separator')
    current_role = None
    buffer_text = []
    valid_roles_set = set(allowed_roles) if allowed_roles else None

    start_page_idx = max(0, start_page - 1)
    found_start_phrase = False if start_phrase else True
    clean_start_phrase = start_phrase.replace(" ", "").replace("\t", "").replace("\n", "")

    # [NEW] 지문 판단 헬퍼 함수
    def is_direction_line(line_text):
        # 1. 괄호로 감싸진 경우 (예: (퇴장한다))
        if line_text.startswith('(') and line_text.endswith(')'):
            return True
        # 2. 서술형 어미로 끝나는 경우 (한국어 대본 특성)
        # 예: 웃는다, 나간다, 쳐다본다, 있다, 한다, 된다
        if line_text.endswith('다.') or line_text.endswith('다'):
            return True
        return False

    # [NEW] 대사에서 괄호 제거 헬퍼 함수
    def remove_parentheses(text):
        # (지문) 또는 [지문] 또는 <지문> 제거
        text = re.sub(r'\(.*?\)', '', text)
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\<.*?\>', '', text)
        return text.strip()

    # 버퍼 비우기 (대사 저장)
    def flush_buffer():
        nonlocal current_role, buffer_text
        if current_role and buffer_text:
            full_text = " ".join(buffer_text)
            # 괄호 제거한 순수 대사 (TTS용)
            clean_speech = remove_parentheses(full_text)
            
            # 대사가 비어있지 않으면 추가 (괄호만 있는 줄은 대사 아님)
            if clean_speech:
                script_data.append({
                    'role': current_role,
                    'text': clean_speech, # 괄호 제거된 텍스트
                    'original_text': full_text, # 원본 텍스트(화면 표시용 필요시)
                    'type': 'dialogue'
                })
        buffer_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            if page_idx < start_page_idx: continue

            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue

                # 시작 문구 스킵 로직
                if not found_start_phrase and clean_start_phrase:
                    clean_line = line.replace(" ", "").replace("\t", "")
                    if clean_start_phrase in clean_line:
                        found_start_phrase = True
                    else:
                        continue 

                # 1. 역할(이름) 감지 시도
                found_name = None
                content_text = ""
                
                # (1) 정규식
                if wrapper_regex:
                    match = re.match(wrapper_regex, line)
                    if match:
                        found_name = match.group(1)
                        content_text = line[match.end():].strip()
                        if separator and content_text.startswith(separator):
                            content_text = content_text[len(separator):].strip()
                
                # (2) 구분자
                elif separator:
                    if separator in line:
                        parts = line.split(separator, 1)
                        found_name = parts[0].strip()
                        content_text = parts[1].strip()
                
                # (3) 자동 (공백 2칸)
                else: 
                    parts = re.split(r'\s{2,}|\t', line, maxsplit=1)
                    if len(parts) == 2:
                        found_name = parts[0].strip()
                        content_text = parts[1].strip()

                # 역할이 감지됨!
                if found_name and (not valid_roles_set or found_name in valid_roles_set) and (1 <= len(found_name) <= 15):
                    flush_buffer() # 이전 사람 대사 저장
                    current_role = found_name
                    if content_text:
                        # 역할 옆에 붙은 텍스트가 지문인지 확인 (드물지만)
                        if is_direction_line(content_text):
                             # 역할은 잡혔는데 내용은 지문? -> 대사가 아닐 수도 있음. 일단은 대사로 침.
                             buffer_text.append(content_text)
                        else:
                            buffer_text.append(content_text)
                
                # 역할이 아님 (대사가 이어지거나, 지문임)
                else:
                    # [핵심 로직] 이게 지문(Action)인가 대사(Dialogue)인가?
                    if is_direction_line(line):
                        # 지문이면 이전 대사 끊고, 지문으로 따로 저장 (또는 무시)
                        flush_buffer()
                        current_role = None # 역할 초기화 (지문 구간 진입)
                        
                        # 지문 데이터로 저장 (화면에 보여주기 위함)
                        script_data.append({
                            'role': '지문', 
                            'text': line, 
                            'original_text': line,
                            'type': 'action'
                        })
                    else:
                        # 지문이 아니면 -> 현재 말하는 사람의 계속되는 대사
                        if current_role:
                            buffer_text.append(line)
                        else:
                            # 말하는 사람이 없는데 텍스트가 나옴 -> 이것도 지문으로 처리
                            script_data.append({
                                'role': '지문', 
                                'text': line, 
                                'original_text': line,
                                'type': 'action'
                            })

    flush_buffer() # 마지막 대사 저장
    return script_data