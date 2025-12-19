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
# 5. [연습] 텍스트 추출 (스마트 독백 감지 적용 🧠)
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

    # [스마트] 지문 판단 로직 개선
    def is_likely_direction(line_text, is_speaking):
        line_text = line_text.strip()
        if not line_text: return False
        
        # 1. 괄호는 무조건 지문 (또는 대사 속 지문)
        if line_text.startswith('(') and line_text.endswith(')'):
            return True
            
        # 2. 독백 보호 (1인칭 주어) -> "나", "내", "우리"로 시작하면 무조건 대사
        first_person_keywords = ["나 ", "나는", "내가", "나의", "내 ", "우리는", "우리가"]
        for kw in first_person_keywords:
            if line_text.startswith(kw):
                return False  # 절대 지문 아님 (대사임)

        # 3. 길이 체크: 문장이 너무 길면(40자 이상) 서술형 대사일 확률 높음
        if len(line_text) > 40:
            return False

        # 4. 한국어 서술형 어미 체크 (~다, ~함, ~음)
        # 단, 누군가 말하고 있는 중(is_speaking=True)이라면 기준을 엄격하게 적용
        clean_end = re.sub(r'[^가-힣]', '', line_text[-5:])
        ends_with_jimum = clean_end.endswith('다') or clean_end.endswith('함') or clean_end.endswith('음') or clean_end.endswith('장') # 퇴장/등장
        
        if ends_with_jimum:
            # 말하고 있는 중이 아니면 -> 지문일 확률 높음
            if not is_speaking:
                return True
            # 말하고 있는 중이면 -> 정말 짧거나(20자 미만), 확실한 행동(입장/퇴장) 아니면 대사로 간주
            else:
                if len(line_text) < 20: 
                    return True # "전화가 울린다" (짧음 -> 지문)
                else:
                    return False # "나는 그렇게 믿고 싶었다." (김 -> 대사)
                    
        return False

    def remove_parentheses(text):
        text = re.sub(r'\(.*?\)', '', text)
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\<.*?\>', '', text)
        return text.strip()

    def flush_buffer():
        nonlocal current_role, buffer_text
        if current_role and buffer_text:
            full_text = " ".join(buffer_text)
            clean_speech = remove_parentheses(full_text)
            if clean_speech:
                script_data.append({
                    'role': current_role,
                    'text': clean_speech,
                    'original_text': full_text,
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
                raw_line = line
                line = line.strip()
                
                # 빈 줄 처리
                if not line:
                    flush_buffer()
                    # 빈 줄이 나와도 역할을 바로 끊지 않고, 다음 줄을 보고 판단하기 위해 
                    # 여기서는 current_role을 None으로 만들지 않습니다.
                    # 다만 문단 구분을 위해 buffer는 비웁니다.
                    continue

                if not found_start_phrase and clean_start_phrase:
                    clean_line = line.replace(" ", "").replace("\t", "")
                    if clean_start_phrase in clean_line:
                        found_start_phrase = True
                    else:
                        continue 

                # 역할 감지 시도
                found_name = None
                content_text = ""
                
                if wrapper_regex:
                    match = re.match(wrapper_regex, line)
                    if match:
                        found_name = match.group(1)
                        content_text = line[match.end():].strip()
                        if separator and content_text.startswith(separator):
                            content_text = content_text[len(separator):].strip()
                elif separator:
                    if separator in line:
                        parts = line.split(separator, 1)
                        found_name = parts[0].strip()
                        content_text = parts[1].strip()
                else: 
                    parts = re.split(r'\s{2,}|\t', line, maxsplit=1)
                    if len(parts) == 2:
                        found_name = parts[0].strip()
                        content_text = parts[1].strip()

                # Case 1: 새로운 역할 발견
                if found_name and (not valid_roles_set or found_name in valid_roles_set) and (1 <= len(found_name) <= 15):
                    flush_buffer()
                    current_role = found_name
                    if content_text:
                        # 역할 옆 텍스트가 지문인지 확인 (말하는 중 아님 False 전달)
                        if is_likely_direction(content_text, is_speaking=False):
                             # 이름 옆에 바로 지문이 붙은 경우 (예: 해리 (일어서며))
                             # 이건 대사 버퍼에 넣지 말고 지문으로 처리할 수도 있지만,
                             # 보통 대사일 확률이 높으므로 일단 대사 버퍼에 넣고 괄호 제거기에 맡김
                             buffer_text.append(content_text)
                        else:
                            buffer_text.append(content_text)
                
                # Case 2: 역할이 아님 (대사 계속 or 지문)
                else:
                    is_speaking = (current_role is not None)
                    
                    if is_likely_direction(line, is_speaking):
                        # 지문으로 판명됨
                        flush_buffer()
                        current_role = None # 지문이 나오면 역할 확실히 끊김
                        script_data.append({
                            'role': '지문', 
                            'text': line, 
                            'original_text': line,
                            'type': 'action'
                        })
                    else:
                        # 대사로 판명됨 (또는 독백)
                        if current_role:
                            buffer_text.append(line)
                        else:
                            # 역할이 없는데 대사 같은 긴 글이 나옴 -> 내레이션일 수 있음
                            # 그냥 지문(Action)으로 처리하되 내용은 보전
                            script_data.append({
                                'role': '지문', 
                                'text': line, 
                                'original_text': line,
                                'type': 'action'
                            })

    flush_buffer()
    return script_data