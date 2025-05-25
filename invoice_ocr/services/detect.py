import os
import cv2
import numpy as np
import re
import matplotlib.pyplot as plt
from google.cloud import vision
from unidecode import unidecode
from datetime import datetime
# import connectdb as conn
# lib for view
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from .image_processing import alignImages, process_image
from django.conf import settings

# Khởi tạo các đường dẫn
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # Thư mục services
INVOICE_OCR_DIR = os.path.dirname(CURRENT_DIR)  # Thư mục invoice_ocr
DOC_DIR = os.path.join(INVOICE_OCR_DIR, 'doc')  # Thư mục doc trong invoice_ocr
CROPTABLE_DIR = os.path.join(DOC_DIR, 'croptable')  # Thư mục croptable trong doc

# Đảm bảo các thư mục tồn tại
for directory in [DOC_DIR, CROPTABLE_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Biến khởi tạo Google Vision
api_path = None
client = None

# Biến toàn cục để lưu đường dẫn ảnh và template_id
detect_img_path = None
current_template_id = None

def get_api_path():
    '''Get API path location'''
    api_path = os.path.join(CURRENT_DIR, 'VisionAPI_Service_Account.json')
    return api_path

def config_google_vision(api_path):
    '''Google Vision API config function (file containing API info)'''
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = api_path
    return vision.ImageAnnotatorClient()

def set_detect_img_path(path, template_id=None):
    '''Set đường dẫn ảnh cần xử lý và template_id (nếu có)'''
    global detect_img_path
    global current_template_id
    detect_img_path = path
    current_template_id = template_id
    print(f"Đã set đường dẫn ảnh: {detect_img_path}")
    if current_template_id:
        print(f"Đã set mẫu hóa đơn ID: {current_template_id}")

def read_and_preprocess_image(image_path):
    '''Reads and converts images to grayscale'''
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image, gray

def apply_binary_filter(gray_image, threshold_value=150):
    '''Applies a binary filter to highlight the lines'''
    _, binary = cv2.threshold(gray_image, threshold_value, 255, cv2.THRESH_BINARY_INV)
    return binary

# detect table ------------------------------------------------------------------------- 

def detect_table_lines(binary_image):
    '''Creates horizontal and vertical lines using expansion and contraction'''
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
    horizontal_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, vertical_kernel)
    table_lines = cv2.add(horizontal_lines, vertical_lines)
    return table_lines

def extract_table_from_image(image, table_lines):
    '''Find and cut table'''
    contours, _ = cv2.findContours(table_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        table_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(table_contour)
        cropped_table = image[y:y+h, x:x+w]
        return cropped_table, (x, y, w, h)
    return None, None

def detect_and_filter_columns(cropped_table, min_line_length=50, max_line_gap=10):
    '''Detect and filter the positions of columns'''
    gray_cropped = cv2.cvtColor(cropped_table, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray_cropped, 50, 150, apertureSize=3)
    
    # Tăng độ dài tối thiểu của đường thẳng để loại bỏ nhiễu
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, 
                           minLineLength=cropped_table.shape[0] * 0.25,  # Ít nhất 25% chiều cao bảng
                           maxLineGap=10)

    # Thu thập tất cả các đường thẳng dọc
    vertical_lines = []
    threshold_angle_error = 25
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Chỉ lấy các đường thẳng gần như thẳng đứng
            if abs(x1 - x2) < threshold_angle_error:
                vertical_lines.append((x1 + x2) / 2)  # Lấy tọa độ x trung bình

    # Gom nhóm các đường thẳng gần nhau
    vertical_lines = sorted(vertical_lines)
    merged_lines = []
    if vertical_lines:
        current_group = [vertical_lines[0]]
        
        for x in vertical_lines[1:]:
            if x - current_group[-1] < 15:  # Khoảng cách để gom nhóm
                current_group.append(x)
            else:
                merged_lines.append(sum(current_group) / len(current_group))
                current_group = [x]
        
        if current_group:
            merged_lines.append(sum(current_group) / len(current_group))

    # Thêm điểm đầu và điểm cuối
    filtered_positions = [0] + merged_lines
    if cropped_table is not None:
        filtered_positions.append(cropped_table.shape[1])

    # Đảm bảo khoảng cách tối thiểu giữa các cột
    min_distance = 30  # Khoảng cách tối thiểu giữa các cột
    final_positions = [filtered_positions[0]]

    for i in range(1, len(filtered_positions)):
        if filtered_positions[i] - final_positions[-1] >= min_distance:
            final_positions.append(filtered_positions[i])
    print('======== Vị trí cột =========')
    print(final_positions)
    print("=============================\n")

    return final_positions

def process_text_data(text_elements, ma_hang_pos, so_luong_pos):
    '''Xử lý và phân loại dữ liệu theo cột'''
    ma_hang_data = []
    so_luong_data = []
    stt_width = 30  # Độ rộng cột STT (có thể điều chỉnh)

    # Sắp xếp theo chiều dọc (từ trên xuống)
    sorted_elements = sorted(text_elements, key=lambda x: x['center_y'])

    # Phân loại dữ liệu vào các cột dựa trên tọa độ
    for elem in sorted_elements:
        x = elem['center_x']
        text = elem['text'].strip()
        
        # Bỏ qua các tiêu đề
        if text in ["Mã hàng", "Số lượng", "STT"]:
            continue
            
        # Làm sạch dữ liệu
        cleaned_text = text
        if text.strip():  # Chỉ xử lý text không rỗng
            # Kiểm tra tọa độ nằm trong phạm vi cột
            if (ma_hang_pos - stt_width <= x <= ma_hang_pos + stt_width):
                ma_hang_data.append(cleaned_text)
            elif (so_luong_pos - stt_width <= x <= so_luong_pos + stt_width):
                so_luong_data.append(cleaned_text)

    # In kết quả
    print("\n=== DỮ LIỆU THEO CỘT ===")
    print("Cột Mã hàng:")
    for item in ma_hang_data:
        print(f"  {item}")
    print("\nCột Số lượng:")
    for item in so_luong_data:
        print(f"  {item}")

    return ma_hang_data, so_luong_data

def save_cropped_columns(cropped_table, filtered_positions, output_dir=None):
    '''Lưu từng cột đã cắt vào thư mục'''
    if output_dir is None:
        # Sử dụng đường dẫn tương đối từ thư mục invoice_ocr/doc/croptable
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'doc', 'croptable')
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Thêm padding để tránh cắt sát quá
    padding = 1
    
    for i in range(len(filtered_positions) - 1):
        col_start = max(int(filtered_positions[i]) - padding, 0)
        col_end = min(int(filtered_positions[i + 1]) + padding, cropped_table.shape[1])
        column = cropped_table[:, col_start:col_end]
        
        # Lưu ảnh cột
        output_path = os.path.join(output_dir, f'column_{i+1}.png')
        cv2.imwrite(output_path, column)
        print(f"Đã lưu cột {i+1} tại: {output_path}")

def detect_text(supplier_keywords=None, invoice_keywords=None, product_code_keywords=None, quantity_keywords=None, num_columns=0):
    '''Thực hiện nhận dạng văn bản tệp đã chọn và hiển thị kết quả'''
    global client
    global detect_img_path
    
    print(f"Bắt đầu xử lý ảnh: {detect_img_path}")
    
    # Khởi tạo các biến
    ma_hang_pos = None
    so_luong_pos = None
    stt_width = 30  # Giá trị mặc định
    ma_ncc = None
    so_don_hang = None
    data_matrix = []
    
    # In thông tin mẫu hóa đơn nếu có
    if supplier_keywords:
        print(f"Từ khóa nhận dạng mã nhà cung cấp: {supplier_keywords}")
    if invoice_keywords:
        print(f"Từ khóa nhận dạng số hóa đơn: {invoice_keywords}")
    if product_code_keywords:
        print(f"Từ khóa nhận dạng cột mã hàng: {product_code_keywords}")
    if quantity_keywords:
        print(f"Từ khóa nhận dạng cột số lượng: {quantity_keywords}")
    if num_columns:
        print(f"Số cột trong bảng: {num_columns}")
        
    # Mặc định từ khóa nếu không được cung cấp
    if not supplier_keywords:
        supplier_keywords = ['ma', 'nha', 'cung', 'cap']
    if not invoice_keywords:
        invoice_keywords = ['so', 'don dat hang']
    if not product_code_keywords:
        product_code_keywords = ['ma', 'hang']
    if not quantity_keywords:
        quantity_keywords = ['so', 'luong']
    
    # Kiểm tra và khởi tạo client nếu cần
    if client is None:
        api_path = get_api_path()
        if not os.path.exists(api_path):
            print(f"File credentials không tồn tại: {api_path}")
            return None
        client = config_google_vision(api_path)
        print("Đã khởi tạo Google Vision client")
    
    # Đọc và tiền xử lý ảnh
    image = cv2.imread(detect_img_path)
    if image is None:
        print(f"Không thể đọc ảnh từ đường dẫn: {detect_img_path}")
        return None
    print(f"Đã đọc ảnh thành công, kích thước: {image.shape}")
        
    try:
        # Tiền xử lý ảnh để cải thiện chất lượng
        # Tăng độ tương phản
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl,a,b))
        enhanced_image = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        print("Đã tăng độ tương phản ảnh")
        
        # Chuyển sang ảnh xám và áp dụng bộ lọc
        gray = cv2.cvtColor(enhanced_image, cv2.COLOR_BGR2GRAY)
        binary = apply_binary_filter(gray)
        print("Đã chuyển sang ảnh xám và áp dụng bộ lọc nhị phân")

        # Tìm vị trí bảng
        table_lines = detect_table_lines(binary)
        print("Đã phát hiện các đường bảng")
        
        result = extract_table_from_image(enhanced_image, table_lines)
        if result[0] is None:
            print("Nhận dạng bảng không thành công")
            return None
        
        cropped_table, (table_x, table_y, table_w, table_h) = result
        print(f"Đã cắt bảng thành công, kích thước: {cropped_table.shape}")
        
        # Lưu ảnh bảng đã cắt
        table_path = os.path.join(CROPTABLE_DIR, 'table.png')
        cv2.imwrite(table_path, cropped_table)
        print(f"Đã lưu bảng đã cắt tại: {table_path}")
        
        # Tìm và lưu các cột
        filtered_positions = detect_and_filter_columns(cropped_table)
        
        # Nếu có số cột được chỉ định từ mẫu hóa đơn, kiểm tra và điều chỉnh
        if num_columns > 0 and len(filtered_positions) != num_columns + 1:
            print(f"Số cột phát hiện ({len(filtered_positions) - 1}) khác với số cột trong mẫu ({num_columns}).")
            # Thay vì điều chỉnh, trả về thông báo lỗi
            return {
                'error': 'column_mismatch',
                'message': f"Số cột phát hiện ({len(filtered_positions) - 1}) khác với số cột trong mẫu ({num_columns}). Vui lòng chụp lại hóa đơn."
            }
        
        print(f"Đã phát hiện {len(filtered_positions)-1} cột")
        save_cropped_columns(cropped_table, filtered_positions)
        print("Đã lưu các cột đã cắt")

        # Gọi Google Vision API một lần
        print("Đang gọi Google Vision API...")
        _, encoded_image = cv2.imencode('.png', image)
        content = encoded_image.tobytes()
        vision_image = vision.Image(content=content)
        response = client.document_text_detection(image=vision_image)
        print("Đã nhận kết quả từ Google Vision API")

        # In toàn bộ dữ liệu từ Google Vision để debug
        print("\n=== DỮ LIỆU TỪ GOOGLE VISION ===")
        print("Text đầy đủ:")
        print(response.full_text_annotation.text)
        
        print("\nChi tiết từng text block:")
        text_elements = []
        all_text_elements = []  # Thêm list mới để lưu tất cả text
        
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        text = ''.join([symbol.text for symbol in word.symbols])
                        vertices = [(vertex.x, vertex.y) for vertex in word.bounding_box.vertices]
                        center_x = sum(x for x, _ in vertices) / 4
                        center_y = sum(y for _, y in vertices) / 4
                        
                        elem = {
                            'text': text.strip(),
                            'center_x': center_x,
                            'center_y': center_y,
                            'vertices': vertices
                        }
                        
                        # Thêm vào danh sách tất cả text
                        all_text_elements.append(elem)
                        
                        # Cập nhật stt_width nếu tìm thấy text "STT"
                        if text.strip() == "STT":
                            stt_width = abs(vertices[1][0] - vertices[0][0])
                            print(f"Tìm thấy cột STT, độ rộng: {stt_width}")
                        
                        # Thêm text vào elements nếu nằm trong bảng
                        if (table_x <= center_x <= table_x + table_w and 
                            table_y <= center_y <= table_y + table_h):
                            text_elements.append(elem)
        
        print(f"Tổng số text elements: {len(all_text_elements)}")
        print(f"Số text elements trong bảng: {len(text_elements)}")

        # Tìm header columns trước
        header_y = None
        header_texts = []
        
        # Bước 1: Tìm dòng header
        for elem in text_elements:
            text = elem['text'].strip()
            text_lower = unidecode(text.lower())
            
            # Sử dụng hàm kiểm tra linh hoạt để tìm từ khóa
            has_product_keyword = check_keywords_flexible(text_lower, product_code_keywords)
            has_quantity_keyword = check_keywords_flexible(text_lower, quantity_keywords)
            
            # In thông tin debug cho các từ khóa tìm thấy
            if has_product_keyword or has_quantity_keyword:
                print(f"Tìm thấy từ khóa trong text: '{text}', mã hàng: {has_product_keyword}, số lượng: {has_quantity_keyword}")
                
            if has_product_keyword or has_quantity_keyword:
                if header_y is None:
                    header_y = elem['center_y']
                if abs(elem['center_y'] - header_y) < 10:  # Cùng dòng header
                    header_texts.append({
                        'text': text,
                        'x': elem['center_x'],
                        'y': elem['center_y'],
                        'normalized': text_lower,
                        'is_product': has_product_keyword,
                        'is_quantity': has_quantity_keyword
                    })

        print(f"Tìm thấy {len(header_texts)} text trong header")

        # Bước 2: Tìm vị trí cột từ header
        if header_texts:
            header_texts.sort(key=lambda x: x['x'])  # Sắp xếp theo tọa độ x
            print("\n=== HEADER TEXTS ===")
            for h in header_texts:
                product_flag = '(Mã hàng)' if h['is_product'] else ''
                quantity_flag = '(Số lượng)' if h['is_quantity'] else ''
                print(f"{h['text']} at x={h['x']} {product_flag} {quantity_flag}")
            
            # Tìm vị trí chính xác của cột mã hàng và số lượng
            product_code_headers = [h for h in header_texts if h['is_product']]
            quantity_headers = [h for h in header_texts if h['is_quantity']]
            
            # Tìm cột mã hàng (thường là cột thứ 2)
            if product_code_headers:
                # Sắp xếp các header mã hàng theo x
                product_code_headers.sort(key=lambda x: x['x'])
                
                # Lấy vị trí cột mã hàng (thường là header thứ 2 hoặc 3)
                if len(product_code_headers) >= 2:
                    # Thường là 2 từ "Mã" và "hàng" nằm cạnh nhau
                    for i in range(len(product_code_headers) - 1):
                        if abs(product_code_headers[i]['x'] - product_code_headers[i+1]['x']) < 50:
                            # Lấy giá trị trung bình của 2 từ gần nhau
                            ma_hang_pos = (product_code_headers[i]['x'] + product_code_headers[i+1]['x']) / 2
                            print(f"✓ Cột 'Mã hàng' xác định từ 2 từ gần nhau tại x = {ma_hang_pos}")
                            break
                    else:
                        # Nếu không tìm thấy 2 từ gần nhau, lấy header đầu tiên
                        ma_hang_pos = product_code_headers[0]['x']
                        print(f"✓ Cột 'Mã hàng' xác định từ header đầu tiên tại x = {ma_hang_pos}")
                else:
                    # Chỉ có 1 header
                    ma_hang_pos = product_code_headers[0]['x']
                    print(f"✓ Cột 'Mã hàng' xác định từ header duy nhất tại x = {ma_hang_pos}")
            
            # Tìm cột số lượng (thường là một trong các cột cuối)
            if quantity_headers:
                # Sắp xếp các header số lượng theo x
                quantity_headers.sort(key=lambda x: x['x'])
                
                # Lấy vị trí cột số lượng (thường là header cuối cùng hoặc gần cuối)
                if len(quantity_headers) >= 2:
                    # Thường là 2 từ "Số" và "lượng" nằm cạnh nhau
                    for i in range(len(quantity_headers) - 1):
                        if abs(quantity_headers[i]['x'] - quantity_headers[i+1]['x']) < 50:
                            # Lấy giá trị trung bình của 2 từ gần nhau
                            so_luong_pos = (quantity_headers[i]['x'] + quantity_headers[i+1]['x']) / 2
                            print(f"✓ Cột 'Số lượng' xác định từ 2 từ gần nhau tại x = {so_luong_pos}")
                            break
                    else:
                        # Nếu không tìm thấy 2 từ gần nhau, lấy header cuối cùng
                        so_luong_pos = quantity_headers[-1]['x']
                        print(f"✓ Cột 'Số lượng' xác định từ header cuối cùng tại x = {so_luong_pos}")
                else:
                    # Chỉ có 1 header
                    so_luong_pos = quantity_headers[0]['x']
                    print(f"✓ Cột 'Số lượng' xác định từ header duy nhất tại x = {so_luong_pos}")
        
        if not ma_hang_pos or not so_luong_pos:
            print("⚠ Không tìm thấy cột Mã hàng hoặc Số lượng")
            return None

        # Lấy tọa độ 4 đường tạo thành 2 cột
        product_code_lcol = None
        product_code_rcol = None
        quantity_lcol = None
        quantity_rcol = None
        
        # Tìm cột chứa vị trí mã hàng trong filtered_positions
        best_product_col_idx = 0
        best_product_col_dist = float('inf')
        for i in range(1, len(filtered_positions)):
            # Tìm cột gần nhất với ma_hang_pos
            col_center = (filtered_positions[i-1] + filtered_positions[i]) / 2
            dist = abs(col_center - ma_hang_pos)
            if dist < best_product_col_dist:
                best_product_col_dist = dist
                best_product_col_idx = i
                product_code_lcol = filtered_positions[i-1]
                product_code_rcol = filtered_positions[i]
        
        print(f"Tìm thấy cột Mã hàng nằm giữa x={product_code_lcol} và x={product_code_rcol}")
        
        # Tìm cột chứa vị trí số lượng trong filtered_positions
        best_quantity_col_idx = 0
        best_quantity_col_dist = float('inf')
        for i in range(1, len(filtered_positions)):
            # Tìm cột gần nhất với so_luong_pos
            col_center = (filtered_positions[i-1] + filtered_positions[i]) / 2
            dist = abs(col_center - so_luong_pos)
            if dist < best_quantity_col_dist:
                best_quantity_col_dist = dist
                best_quantity_col_idx = i
                quantity_lcol = filtered_positions[i-1]
                quantity_rcol = filtered_positions[i]
        
        print(f"Tìm thấy cột Số lượng nằm giữa x={quantity_lcol} và x={quantity_rcol}")
        
        # Kiểm tra xem đã tìm thấy cả hai cột chưa
        if not all([product_code_lcol, product_code_rcol, quantity_lcol, quantity_rcol]):
            print("⚠ Không thể xác định chính xác vị trí của cột Mã hàng hoặc Số lượng")
            return None
        
        # Bước 3: Thu thập tất cả text với tọa độ
        # Tạo cấu trúc để lưu tất cả dữ liệu với tọa độ đầy đủ
        all_data_elements = []
        
        # Tìm vị trí cột STT
        stt_pos = None
        for elem in text_elements:
            if elem['text'].strip() == "STT":
                stt_pos = elem['center_x']
                print(f"Tìm thấy vị trí cột STT: {stt_pos}")
                break
        
        # Lọc và sắp xếp các text không phải header
        data_elements = [elem for elem in text_elements 
                        if abs(elem['center_y'] - header_y) > 10]  # Tolerance = 10
        data_elements.sort(key=lambda x: (x['center_y'], x['center_x']))
        print(f"Số text elements dữ liệu: {len(data_elements)}")
        
        # Thu thập tất cả dữ liệu có liên quan với tọa độ đầy đủ
        for elem in data_elements:
            y = elem['center_y']
            x = elem['center_x']
            text = elem['text'].strip()
            
            # Bỏ qua text trong cột STT
            if stt_pos and abs(x - stt_pos) < stt_width:
                continue
                
            elem_type = None
            
            # Phân loại dữ liệu dựa vào tọa độ x
            if product_code_lcol <= x <= product_code_rcol:
                elem_type = "product_code"
                print(f"Text trong cột mã hàng: '{text}' tại x={x}, y={y}")
            elif quantity_lcol <= x <= quantity_rcol:
                elem_type = "quantity"
                print(f"Text trong cột số lượng: '{text}' tại x={x}, y={y}")
            
            # Thêm vào danh sách dữ liệu với loại và tọa độ
            if elem_type:
                all_data_elements.append({
                    'text': text,
                    'type': elem_type,
                    'x': x,
                    'y': y,
                    'vertices': elem['vertices']
                })
        
        print(f"Tổng số phần tử dữ liệu đã phân loại: {len(all_data_elements)}")
        
        # Bước 4: Xử lý dữ liệu thông minh
        # Sắp xếp theo y để xác định các dòng
        all_data_elements.sort(key=lambda x: (x['y'], x['x']))
        
        # Gom nhóm các phần tử theo dòng
        rows = []
        current_row = []
        current_y = None
        tolerance = 10  # Dung sai cho cùng dòng
        
        for elem in all_data_elements:
            if current_y is None:
                current_y = elem['y']
                current_row.append(elem)
            elif abs(elem['y'] - current_y) <= tolerance:
                # Cùng dòng
                current_row.append(elem)
            else:
                # Dòng mới
                if current_row:
                    rows.append(current_row)
                current_row = [elem]
                current_y = elem['y']
        
        # Thêm dòng cuối
        if current_row:
            rows.append(current_row)
        
        print(f"Phân tích được {len(rows)} dòng dữ liệu")
        
        # Bước 5: Xử lý từng dòng để trích xuất mã hàng và số lượng
        data_matrix = []
        
        for row_idx, row_data in enumerate(rows):
            product_code_parts = []
            quantity = None
            
            # Lấy tất cả phần tử mã hàng trong dòng
            for elem in row_data:
                if elem['type'] == 'product_code':
                    product_code_parts.append(elem)
                elif elem['type'] == 'quantity':
                    # Đối với số lượng, lấy giá trị cuối cùng
                    quantity = elem['text']
            
            # Nếu có các phần mã hàng, xử lý ghép
            if product_code_parts:
                # Sắp xếp các phần mã hàng theo tọa độ x
                product_code_parts.sort(key=lambda x: x['x'])
                
                # Ghép mã hàng
                product_code = ''
                for part in product_code_parts:
                    product_code += part['text'].replace(" ", "")
                
                # Thêm vào ma trận kết quả
                data_matrix.append([product_code, quantity])
                print(f"Dòng {row_idx+1}: Mã hàng = '{product_code}', Số lượng = '{quantity}'")
        
        # Bước 6: Xử lý trường hợp mã hàng bị tách giữa các dòng
        # Xử lý mã hàng bị tách (ví dụ: "GD" trên dòng 1, "03" trên dòng 2)
        merged_matrix = []
        skip_next = False
        
        for i in range(len(data_matrix)):
            if skip_next:
                skip_next = False
                continue
                
            current_row = data_matrix[i]
            product_code, quantity = current_row
            
            # Nếu chưa phải dòng cuối và có hàng tiếp theo
            if i < len(data_matrix) - 1:
                next_row = data_matrix[i + 1]
                next_product_code, next_quantity = next_row
                
                # Kiểm tra nếu mã hiện tại là chữ và mã tiếp theo là số
                if (product_code and next_product_code and 
                    product_code.strip().isalpha() and next_product_code.strip().isdigit()):
                    # Đây là trường hợp mã hàng bị tách (ví dụ: "GD" và "03")
                    merged_code = product_code.strip() + next_product_code.strip()
                    print(f"Ghép mã hàng bị tách giữa các dòng: '{product_code}' + '{next_product_code}' -> '{merged_code}'")
                    
                    # Ưu tiên sử dụng số lượng từ dòng thứ 2
                    merged_quantity = next_quantity if next_quantity else quantity
                    
                    # Thêm mã đã ghép vào kết quả
                    merged_matrix.append([merged_code, merged_quantity])
                    skip_next = True  # Bỏ qua dòng tiếp theo vì đã xử lý
                else:
                    # Không phải trường hợp ghép, giữ nguyên
                    merged_matrix.append(current_row)
            else:
                # Dòng cuối không cần xử lý ghép
                merged_matrix.append(current_row)
        
        # Tạo danh sách các text elements phía trên bảng
        header_elements = []
        
        # Sử dụng all_text_elements thay vì text_elements
        for elem in all_text_elements:
            if elem['center_y'] < table_y:  # Lấy tất cả text phía trên bảng
                header_elements.append(elem)
        
        print(f"Số text elements phía trên bảng: {len(header_elements)}")
        
        # Sắp xếp theo thứ tự từ trên xuống và trái sang phải
        header_elements.sort(key=lambda x: (x['center_y'], x['center_x']))
        
        # Tìm mã nhà cung cấp
        for i, elem in enumerate(header_elements):
            text = elem['text'].strip().lower()
            
            # Kiểm tra từ khóa nhà cung cấp với phương pháp linh hoạt
            if check_keywords_flexible(text, supplier_keywords):
                # Tìm số trong cùng dòng (có center_y gần nhau)
                current_y = elem['center_y']
                current_x = elem['center_x']
                for next_elem in header_elements[i:]:
                    if abs(next_elem['center_y'] - current_y) < 20:  # Cùng dòng
                        next_text = next_elem['text'].strip()
                        # Kiểm tra nếu text là số và nằm trong khoảng cách cho phép
                        if next_text.isdigit():
                            # Kiểm tra khoảng cách ngang giữa từ khóa và số
                            if abs(next_elem['center_x'] - current_x) < 200:  # Giới hạn khoảng cách 200 pixel
                                ma_ncc = next_text
                                print(f"Tìm thấy mã nhà cung cấp: {ma_ncc}")
                                break
                if ma_ncc:  # Nếu đã tìm thấy thì dừng
                    break
        
        # Tìm số đơn đặt hàng
        for i, elem in enumerate(header_elements):
            text = elem['text'].strip().lower()
            
            # Kiểm tra từ khóa đơn hàng với phương pháp linh hoạt
            if check_keywords_flexible(text, invoice_keywords):
                # Tìm số trong cùng dòng
                current_y = elem['center_y']
                current_x = elem['center_x']
                # Lấy tất cả text elements trên cùng một dòng
                same_line_elements = [e for e in header_elements 
                                    if abs(e['center_y'] - current_y) < 20]
                # Sắp xếp theo tọa độ x để đảm bảo đọc từ trái sang phải
                same_line_elements.sort(key=lambda x: x['center_x'])
                
                # Tìm vị trí của phần tử hiện tại trong dòng
                current_index = same_line_elements.index(elem)
                
                # Kiểm tra các phần tử phía sau trong cùng dòng
                for next_elem in same_line_elements[current_index:]:
                    next_text = next_elem['text'].strip()
                    # Kiểm tra nếu text là số và nằm trong khoảng cách cho phép
                    if next_text.isdigit():
                        # Kiểm tra khoảng cách ngang giữa từ khóa và số
                        if abs(next_elem['center_x'] - current_x) < 200:  # Giới hạn khoảng cách 200 pixel
                            so_don_hang = next_text
                            print(f"Tìm thấy số đơn hàng: {so_don_hang}")
                            break
                if so_don_hang:  # Nếu đã tìm thấy thì dừng
                    break

        # In thông tin nhà cung cấp và đơn hàng
        print("\n=== THÔNG TIN ĐƠN HÀNG ===")
        print(f"Mã nhà cung cấp: {ma_ncc if ma_ncc else 'Không tìm thấy'}")
        print(f"Số đơn đặt hàng: {so_don_hang if so_don_hang else 'Không tìm thấy'}")
        print("-" * 40)

        # Thêm thông tin vào kết quả trả về
        result = {
            'ma_ncc': ma_ncc,
            'so_don_hang': so_don_hang,
            'data_matrix': merged_matrix  # Sử dụng ma trận đã được xử lý ghép
        }
        
        # Xử lý hậu kỳ trước khi trả về kết quả
        result = post_process_data(result)
        
        print("Kết quả trích xuất:", result)
        return result
    except Exception as e:
        print(f"Lỗi xử lý ảnh: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def check_keywords_flexible(text, keywords_list):
    """
    Kiểm tra linh hoạt nếu text có chứa bất kỳ từ khóa nào từ danh sách
    Cho phép khớp một phần và nhiều cách viết khác nhau
    """
    # Chuẩn hóa text thành chữ thường và không dấu
    text = unidecode(text.lower())
    
    # Loại bỏ khoảng trắng để tìm kiếm từ liền nhau
    text_no_space = text.replace(" ", "")
    
    # 1. Kiểm tra từng từ khóa đơn lẻ
    for keyword in keywords_list:
        keyword_lower = unidecode(keyword.lower())
        
        # Kiểm tra từ khóa trong text ban đầu
        if keyword_lower in text:
            return True
        
        # Kiểm tra từ khóa trong text đã loại bỏ khoảng trắng
        if keyword_lower.replace(" ", "") in text_no_space:
            return True
    
    # 2. Kiểm tra kết hợp các từ khóa (cho trường hợp 2 từ liên tiếp)
    if len(keywords_list) >= 2:
        # Kết hợp các từ khóa trong danh sách
        combined_keywords = []
        for i in range(len(keywords_list) - 1):
            for j in range(i + 1, len(keywords_list)):
                combined = unidecode(keywords_list[i].lower()) + unidecode(keywords_list[j].lower())
                combined_no_space = combined.replace(" ", "")
                combined_keywords.append(combined_no_space)
        
        # Kiểm tra từng từ khóa kết hợp
        for combined in combined_keywords:
            if combined in text_no_space:
                return True
    
    return False

def post_process_data(result):
    """
    Xử lý hậu kỳ dữ liệu trước khi trả về
    - Ghép các phần của mã hàng (loại bỏ khoảng trắng)
    - Xử lý dữ liệu số lượng (chuyển O/Q thành 0)
    """
    if not result or 'data_matrix' not in result:
        return result
    
    data_matrix = result['data_matrix']
    processed_matrix = []
    
    # Xử lý từng dòng dữ liệu
    for row in data_matrix:
        if len(row) != 2:
            continue
            
        product_code, quantity = row
        
        # Bỏ qua hàng không có dữ liệu
        if not product_code and not quantity:
            continue
            
        # Xử lý mã hàng: loại bỏ khoảng trắng
        if product_code:
            product_code = product_code.replace(" ", "")
        
        # Xử lý số lượng: chuyển O/Q thành 0
        if quantity:
            # Thay thế các ký tự O/Q/o/q bằng số 0
            quantity = quantity.replace('O', '0').replace('o', '0').replace('Q', '0').replace('q', '0')
            # Thay thế các ký tự S/s bằng số 5 (thường bị OCR nhầm)
            quantity = quantity.replace('S', '5').replace('s', '5')
            # Thay thế các ký tự I/l/| bằng số 1
            quantity = quantity.replace('I', '1').replace('l', '1').replace('|', '1')
            
            # Loại bỏ các ký tự không phải số hoặc dấu thập phân
            quantity = ''.join(c for c in quantity if c.isdigit() or c == '.')
        
        # Thêm dòng đã xử lý vào kết quả cuối cùng
        if product_code or quantity:
            processed_matrix.append([product_code, quantity])
    
    # Cập nhật ma trận dữ liệu
    result['data_matrix'] = processed_matrix
    
    print("\n=== MA TRẬN DỮ LIỆU SAU XỬ LÝ ===")
    print("Mã hàng\t\tSố lượng")
    print("-" * 40)
    for row in processed_matrix:
        ma_hang = row[0] if row[0] else "N/A"
        so_luong = row[1] if row[1] else "N/A"
        print(f"{ma_hang}\t\t{so_luong}")
    
    return result

def main():
    global api_path
    global client
    global current_template_id
    
    # Kiểm tra các file và thư mục cần thiết
    if not os.path.exists(DOC_DIR):
        raise ValueError(f"Không tìm thấy thư mục doc tại: {DOC_DIR}")
    
    if not os.path.exists(detect_img_path):
        raise ValueError(f"Không tìm thấy file ảnh đã căn chỉnh tại: {detect_img_path}")
    
    api_path = get_api_path()
    if not os.path.exists(api_path):
        raise ValueError(f"Không tìm thấy file API key tại: {api_path}")
    
    client = config_google_vision(api_path)
    
    try:
        # Xử lý ảnh và căn chỉnh với template_id (nếu có)
        process_image(detect_img_path, template_id=current_template_id)
        print("Xử lý ảnh thành công!")
        
        # Nhận dạng hóa đơn
        result = detect_text()
        
        if result:
            print("\n=== KẾT QUẢ CUỐI CÙNG ===")
            print(f"Mã nhà cung cấp: {result['ma_ncc']}")
            print(f"Số đơn đặt hàng: {result['so_don_hang']}")
            print("\nDữ liệu bảng sản phẩm:")
            for row in result['data_matrix']:
                if row[0] or row[1]:  # Chỉ in các hàng có ít nhất một giá trị
                    ma_hang = row[0] if row[0] else "N/A"
                    so_luong = row[1] if row[1] else "N/A"
                    print(f"{ma_hang}\t\t{so_luong}")
    except Exception as e:
        print(f"Lỗi: {str(e)}")

if __name__ == "__main__":
    main()
