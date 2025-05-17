import os
import cv2
import numpy as np
from django.conf import settings
import django
import sys

# Đảm bảo Django được khởi tạo
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'invoice_recognition.settings')
    django.setup()

def preprocess_image(image):
    '''Tiền xử lý ảnh để cải thiện chất lượng'''
    # Chuyển sang ảnh xám
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Tăng độ tương phản
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    
    # Khử nhiễu
    gray = cv2.GaussianBlur(gray, (5,5), 0)
    
    return gray

def remove_background(image):
    '''Loại bỏ nền của ảnh'''
    # Chuyển sang ảnh xám
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Áp dụng ngưỡng thích ứng
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                 cv2.THRESH_BINARY, 11, 2)
    
    # Tìm contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Tìm contour lớn nhất (giả định là phiếu)
    if contours:
        max_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(max_contour)
        
        # Cắt ảnh theo contour
        cropped = image[y:y+h, x:x+w]
        return cropped
    return image

def alignImages(im1, template_id=None):
    '''Căn chỉnh ảnh với ảnh mẫu sử dụng ORB'''
    MAX_FEATURES = 5000  # Số lượng đặc trưng
    GOOD_MATCH_PERCENT = 0.15  # Tỉ lệ matches
    
    # Lấy ảnh mẫu từ InvoiceTemplate model
    if template_id:
        try:
            # Import model InvoiceTemplate
            from invoice_ocr.models import InvoiceTemplate
            
            # Lấy template từ id
            template = InvoiceTemplate.objects.get(id=template_id)
            if template.template_image:
                template_path = template.template_image.path
                print(f"Sử dụng ảnh mẫu từ mẫu hóa đơn ID={template_id}: {template_path}")
            else:
                raise ValueError(f"Mẫu hóa đơn ID={template_id} không có ảnh mẫu.")
        except Exception as e:
            print(f"Lỗi khi lấy ảnh mẫu từ model: {str(e)}")
            # Sử dụng ảnh mẫu mặc định nếu có lỗi
            template_path = os.path.join(settings.MEDIA_ROOT, 'invoice_templates', 'default_template.jpg')
            if not os.path.exists(template_path):
                # Nếu không có ảnh mẫu mặc định, sử dụng ảnh cũ
                template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'doc', 'anh_mau.jpg')
            print(f"Sử dụng ảnh mẫu mặc định: {template_path}")
    else:
        # Sử dụng ảnh mẫu mặc định khi không chỉ định template_id
        template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'doc', 'anh_mau.jpg')
        print(f"Không có ID mẫu hóa đơn được chỉ định, sử dụng ảnh mẫu mặc định: {template_path}")

    im2 = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if im2 is None:
        raise ValueError(f"Không thể đọc ảnh mẫu. Vui lòng kiểm tra đường dẫn '{template_path}'")

    # Tiền xử lý cả hai ảnh
    im1Gray = preprocess_image(im1)
    im2Gray = preprocess_image(im2)

    # Phát hiện đặc trưng ORB và tính descriptors
    orb = cv2.ORB_create(MAX_FEATURES)
    keypoints1, descriptors1 = orb.detectAndCompute(im1Gray, None)
    keypoints2, descriptors2 = orb.detectAndCompute(im2Gray, None)

    # So khớp đặc trưng
    matcher = cv2.DescriptorMatcher_create(cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING)
    matches = list(matcher.match(descriptors1, descriptors2, None))

    # Sắp xếp matches theo điểm số
    matches.sort(key=lambda x: x.distance, reverse=False)
    numGoodMatches = int(len(matches) * GOOD_MATCH_PERCENT)
    matches = matches[:numGoodMatches]

    # Vẽ top matches
    imMatches = cv2.drawMatches(im1, keypoints1, im2, keypoints2, matches, None)
    matches_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'doc', 'matches.jpg')
    cv2.imwrite(matches_path, imMatches)

    # Trích xuất vị trí của good matches
    points1 = np.zeros((len(matches), 2), dtype=np.float32)
    points2 = np.zeros((len(matches), 2), dtype=np.float32)
    for i, match in enumerate(matches):
        points1[i, :] = keypoints1[match.queryIdx].pt
        points2[i, :] = keypoints2[match.trainIdx].pt

    # Tìm homography với RANSAC
    h, mask = cv2.findHomography(points1, points2, cv2.RANSAC, 5.0)

    # Sử dụng homography
    height, width, channels = im2.shape
    im1Reg = cv2.warpPerspective(im1, h, (width, height))
    
    # Loại bỏ nền
    im1Reg = remove_background(im1Reg)
    
    return im1Reg, height, width

def process_image(img_path, output_path=None, template_id=None):
    '''Xử lý ảnh chính'''
    # Đọc ảnh đầu vào
    image = cv2.imread(img_path)
    if image is None:
        raise ValueError(f"Không thể đọc ảnh từ đường dẫn: {img_path}")

    # Căn chỉnh ảnh với template_id (nếu có)
    aligned_image, _, _ = alignImages(image, template_id)
    
    # Nếu không có output_path, sử dụng tên file mặc định
    if output_path is None:
        doc_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'doc')
        if not os.path.exists(doc_dir):
            os.makedirs(doc_dir)
        output_path = os.path.join(doc_dir, 'after_alignimage.png')
    
    # Đảm bảo thư mục đích tồn tại
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Ghi đè file nếu đã tồn tại
    cv2.imwrite(output_path, aligned_image)
    print(f"Đã lưu ảnh đã căn chỉnh tại: {output_path}")
    return output_path


