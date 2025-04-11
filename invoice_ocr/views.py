from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os
from datetime import datetime
import json
from django.conf import settings
from .services.third import detect_text, process_image, set_detect_img_path
from .services.image_processing import alignImages

# Create your views here.
def index(request):
    return render(request, 'camera.html')

@csrf_exempt
def save_image(request):
    if request.method == 'POST':
        try:
            # Lấy file ảnh từ request
            image_file = request.FILES['image']
            
            # Sử dụng tên cố định cho các file
            captured_filename = 'captured_image.jpg'
            aligned_filename = 'after_alignimage.png'
            
            # Tạo đường dẫn lưu file
            captured_path = os.path.join(settings.MEDIA_ROOT, captured_filename)
            aligned_path = os.path.join(settings.MEDIA_ROOT, aligned_filename)
            
            # Đảm bảo thư mục tồn tại
            os.makedirs(os.path.dirname(captured_path), exist_ok=True)
            
            # Lưu file gốc (ghi đè nếu đã tồn tại)
            with open(captured_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)
            
            # Xử lý căn chỉnh ảnh (ghi đè file aligned nếu đã tồn tại)
            process_image(captured_path, aligned_path)
            
            # Set đường dẫn ảnh đã căn chỉnh cho detect_text
            set_detect_img_path(aligned_path)
            
            # Nhận dạng văn bản
            result = detect_text()
            
            if result:
                # Chuẩn bị dữ liệu trả về
                extracted_data = {
                    'ma_ncc': result.get('ma_ncc', ''),
                    'so_don_hang': result.get('so_don_hang', ''),
                    'ten_ncc': '',
                    'data_matrix': []
                }
                
                # Xử lý dữ liệu sản phẩm
                for row in result.get('data_matrix', []):
                    if row[0] or row[1]:  # Chỉ thêm hàng có dữ liệu
                        product = {
                            'ma_hang': row[0] if row[0] else '',
                            'ten_hang': '',
                            'dvt': '',
                            'so_luong': row[1] if row[1] else '0'
                        }
                        extracted_data['data_matrix'].append(product)
                
                return JsonResponse({
                    'success': True,
                    'image_path': aligned_path,
                    'extracted_data': extracted_data
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể trích xuất dữ liệu từ ảnh'
                })
                
        except Exception as e:
            print(f"Lỗi xử lý ảnh: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'message': f'Lỗi xử lý ảnh: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Phương thức không được hỗ trợ'})

@csrf_exempt
def extract_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_path = data.get('image_path')
            
            if not image_path or not os.path.exists(image_path):
                return JsonResponse({
                    'success': False,
                    'message': 'Không tìm thấy ảnh'
                })
            
            # Set đường dẫn ảnh cho detect_text
            set_detect_img_path(image_path)
            
            # Nhận dạng văn bản
            result = detect_text()
            
            if result:
                # Chuẩn bị dữ liệu trả về
                extracted_data = {
                    'ma_ncc': result.get('ma_ncc', ''),
                    'so_don_hang': result.get('so_don_hang', ''),
                    'ten_ncc': '',  # Có thể thêm logic để trích xuất tên NCC
                    'data_matrix': []
                }
                
                # Xử lý dữ liệu sản phẩm
                for row in result.get('data_matrix', []):
                    if row[0] or row[1]:  # Chỉ thêm hàng có dữ liệu
                        product = {
                            'ma_hang': row[0] if row[0] else '',
                            'ten_hang': '',  # Có thể thêm logic để trích xuất tên hàng
                            'dvt': '',  # Có thể thêm logic để trích xuất đơn vị tính
                            'so_luong': row[1] if row[1] else '0'
                        }
                        extracted_data['data_matrix'].append(product)
                
                return JsonResponse({
                    'success': True,
                    'extracted_data': extracted_data
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể trích xuất dữ liệu từ ảnh'
                })
                
        except Exception as e:
            print(f"Lỗi xử lý ảnh: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'message': f'Lỗi xử lý ảnh: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Phương thức không được hỗ trợ'})

def camera(request):
    return render(request, 'camera.html')