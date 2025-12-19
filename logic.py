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
            lines_dict = {}
            
            # Y좌표 그룹핑 (Tolerance 5)
            words.sort(key=lambda w: w['top'])
            if words:
                current_line = [words[0]]
                current_top = words[0]['top']
                for w in words[1:]:
                    if abs(w['top'] - current_top) < 5:
                        current_line.append(w)
                    else:
                        lines_data_list = lines_dict.get('list', []) 
                        # 딕셔너리가 아니라 리스트로 관리 필요하지만, 
                        # 기존 로직 유지를 위해 아래 반복문에서 처리
                        pass
            
            # (위의 analyze_and_get_coordinates 로직은 이전 답변과 동일하게 유지 - 생략 없이 전체 코드 제공)
            # --- 수정된 라인 그룹핑 로직 ---
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
# 5. [연습] 텍스트 추출 (시작 위치 필터링 추가 🚀)
# ---------------------------------------------------------
def extract_script_data(pdf_path, my_role, config, allowed_roles=None, start_page=1, start_phrase=""):
    script_data = []
    wrapper_regex = config.get('wrapper_regex')
    separator = config.get('separator')
    current_role = None
    buffer_text = []
    valid_roles_set = set(allowed_roles) if allowed_roles else None

    # 시작 페이지 인덱스 (0부터 시작하므로 -1)
    start_page_idx = max(0, start_page - 1)
    
    # 시작 문구 처리
    found_start_phrase = False if start_phrase else True
    clean_start_phrase = start_phrase.replace(" ", "").replace("\t", "").replace("\n", "")

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            # 1. 페이지 스킵
            if page_idx < start_page_idx: continue

            text = page.extract_text(layout=True)
            if not text: continue
            
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue

                # 2. 시작 문구 스킵 로직 (넘버링과 동일하게 공백 무시 비교)
                if not found_start_phrase and clean_start_phrase:
                    clean_line = line.replace(" ", "").replace("\t", "")
                    if clean_start_phrase in clean_line:
                        found_start_phrase = True
                    else:
                        continue # 문구 찾기 전까지 모든 텍스트 무시

                # 이하 로직은 찾은 이후에만 실행됨
                found_name = None
                content_text = ""
                is_valid_role = False

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

                if found_name:
                    if 1 <= len(found_name) <= 15:
                        if valid_roles_set:
                            if found_name in valid_roles_set:
                                is_valid_role = True
                        else:
                            is_valid_role = True

                if is_valid_role:
                    if current_role and buffer_text:
                        script_data.append({'role': current_role, 'text': " ".join(buffer_text)})
                        buffer_text = []
                    current_role = found_name
                    if content_text:
                        buffer_text.append(content_text)
                else:
                    # 시작 문구를 찾은 이후라면 지문도 수집
                    if current_role:
                        buffer_text.append(line)
                    else:
                        script_data.append({'role': '지문', 'text': line})

    if current_role and buffer_text:
        script_data.append({'role': current_role, 'text': " ".join(buffer_text)})
        
    return script_data