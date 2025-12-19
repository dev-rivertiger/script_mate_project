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
# 5. [연습] 텍스트 추출 (지문 키워드 추가 🎬)
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

    # [지문 판단 로직]
    def is_likely_direction(line_text, is_speaking):
        line_text = line_text.strip()
        if not line_text: return False
        
        # 1. 괄호는 무조건 지문
        if line_text.startswith('(') and line_text.endswith(')'): return True
        
        # 2. [NEW] 지문 전용 키워드 감지 ("사이", "퇴장" 등)
        # 예: "짧은 사이.", "사이.", "암전"
        keywords = ["사이", "퇴장", "등장", "암전", "막", "커튼콜"]
        for kw in keywords:
            if kw in line_text and len(line_text) < 15: # 짧은 문장에 키워드가 있으면 지문
                return True

        # 3. 독백/내레이션 보호 (1인칭 주어)
        first_person_keywords = ["나 ", "나는", "내가", "나의", "내 ", "우리는", "우리가"]
        for kw in first_person_keywords:
            if line_text.startswith(kw): return False

        # 4. 접속사 보호
        conjunctions = ["그리고", "그런데", "하지만", "그렇게", "그래서", "그러자", "또한"]
        for conj in conjunctions:
            if line_text.startswith(conj): return False

        # 5. 길이 및 어미 체크
        if len(line_text) > 35: return False # 길면 대사

        clean_end = re.sub(r'[^가-힣]', '', line_text[-5:])
        ends_with_jimum = clean_end.endswith('다') or clean_end.endswith('함') or clean_end.endswith('음') or clean_end.endswith('장')
        
        if ends_with_jimum:
            if not is_speaking:
                return True
            else:
                # 말하고 있는 중이라도 짧으면 지문 (예: 전화가 울린다)
                if len(line_text) < 20: 
                    return True
                else:
                    return False
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
                line = line.strip()
                if not line: continue # 빈 줄은 무시하되 연결성은 아래 로직에 맡김

                if not found_start_phrase and clean_start_phrase:
                    clean_line = line.replace(" ", "").replace("\t", "")
                    if clean_start_phrase in clean_line: found_start_phrase = True
                    else: continue 

                # 역할 감지
                found_name = None
                content_text = ""
                
                if wrapper_regex:
                    match = re.match(wrapper_regex, line)
                    if match:
                        found_name = match.group(1)
                        content_text = line[match.end():].strip()
                        if separator and content_text.startswith(separator): content_text = content_text[len(separator):].strip()
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

                # Case 1: 새로운 역할
                if found_name and (not valid_roles_set or found_name in valid_roles_set) and (1 <= len(found_name) <= 15):
                    flush_buffer()
                    current_role = found_name
                    if content_text:
                        if is_likely_direction(content_text, is_speaking=False):
                             buffer_text.append(content_text)
                        else:
                            buffer_text.append(content_text)
                
                # Case 2: 역할 아님
                else:
                    is_speaking = (current_role is not None)
                    
                    is_continuation = False
                    if is_speaking and buffer_text:
                        last_line = buffer_text[-1].strip()
                        # 문장이 끝나지 않았으면(마침표 등 없음) 무조건 대사 연장
                        if not last_line.endswith('.') and not last_line.endswith('?') and not last_line.endswith('!'):
                            is_continuation = True
                            
                    if is_continuation:
                        buffer_text.append(line)
                    elif is_likely_direction(line, is_speaking):
                        flush_buffer()
                        current_role = None # 지문이 나오면 역할 끊김
                        script_data.append({
                            'role': '지문', 
                            'text': line, 
                            'original_text': line,
                            'type': 'action'
                        })
                    else:
                        if current_role:
                            buffer_text.append(line)
                        else:
                            script_data.append({
                                'role': '지문', 
                                'text': line, 
                                'original_text': line,
                                'type': 'action'
                            })

    flush_buffer()
    return script_data