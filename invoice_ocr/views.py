from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import logout_then_login
from django.db.models import Q, Count, Sum
import os
from datetime import datetime
import json
from django.conf import settings
from .services.third import detect_text, process_image, set_detect_img_path
from .services.image_processing import alignImages
from .models import Product, Supplier, WarehouseReceipt, Inventory, process_invoice_data, ReceiptDetail
from dateutil.relativedelta import relativedelta

def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            next_page = request.GET.get('next', 'index')
            return redirect(next_page)
        else:
            return render(request, 'login.html', {'error': 'Tên đăng nhập hoặc mật khẩu không đúng'})
    
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required(login_url='login')
def index(request):
    return render(request, 'index.html')

@login_required(login_url='login')
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
                # Lấy thông tin nhà cung cấp từ database
                supplier = None
                if result.get('ma_ncc'):
                    supplier = Supplier.objects.filter(supplier_id=result.get('ma_ncc')).first()
                
                # Chuẩn bị dữ liệu trả về
                extracted_data = {
                    'ma_ncc': result.get('ma_ncc', ''),
                    'so_don_hang': result.get('so_don_hang', ''),
                    'ten_ncc': supplier.supplier_name if supplier else '',
                    'data_matrix': []
                }
                
                # Xử lý dữ liệu sản phẩm
                for row in result.get('data_matrix', []):
                    if row[0] or row[1]:  # Chỉ thêm hàng có dữ liệu
                        # Lấy thông tin sản phẩm từ database
                        product = None
                        if row[0]:  # Nếu có mã sản phẩm
                            product = Product.objects.filter(product_id=row[0]).first()
                        
                        product_data = {
                            'ma_hang': row[0] if row[0] else '',
                            'ten_hang': product.product_name if product else '',
                            'dvt': product.unit if product else '',
                            'so_luong': row[1] if row[1] else '0'
                        }
                        extracted_data['data_matrix'].append(product_data)
                
                # Thêm dữ liệu vào database nếu có đủ thông tin
                if result.get('ma_ncc') and result.get('so_don_hang') and result.get('data_matrix'):
                    process_result = process_invoice_data(
                        supplier_id=result.get('ma_ncc'),
                        order_number=result.get('so_don_hang'),
                        receipt_date=datetime.now().date(),
                        product_data_list=[[row[0], row[1]] for row in result.get('data_matrix') if row[0] and row[1]]
                    )
                    
                    if process_result['success']:
                        extracted_data['process_message'] = process_result['message']
                        extracted_data['processed_products'] = process_result['details']['processed_products']
                        extracted_data['skipped_products'] = process_result['details']['skipped_products']
                    else:
                        extracted_data['process_message'] = process_result['message']
                
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
                # Lấy thông tin nhà cung cấp từ database
                supplier = None
                if result.get('ma_ncc'):
                    supplier = Supplier.objects.filter(supplier_id=result.get('ma_ncc')).first()
                
                # Chuẩn bị dữ liệu trả về
                extracted_data = {
                    'ma_ncc': result.get('ma_ncc', ''),
                    'so_don_hang': result.get('so_don_hang', ''),
                    'ten_ncc': supplier.supplier_name if supplier else '',
                    'data_matrix': []
                }
                
                # Xử lý dữ liệu sản phẩm
                for row in result.get('data_matrix', []):
                    if row[0] or row[1]:  # Chỉ thêm hàng có dữ liệu
                        # Lấy thông tin sản phẩm từ database
                        product = None
                        if row[0]:  # Nếu có mã sản phẩm
                            product = Product.objects.filter(product_id=row[0]).first()
                        
                        product_data = {
                            'ma_hang': row[0] if row[0] else '',
                            'ten_hang': product.product_name if product else '',
                            'dvt': product.unit if product else '',
                            'so_luong': row[1] if row[1] else '0'
                        }
                        extracted_data['data_matrix'].append(product_data)
                
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

@login_required(login_url='login')
def search(request):
    search_type = request.GET.get('type')
    results = []
    
    if search_type == 'product':
        product_id = request.GET.get('product_id', '')
        product_name = request.GET.get('product_name', '')
        
        query = Q()
        if product_id:
            query |= Q(product_id__icontains=product_id)
        if product_name:
            query |= Q(product_name__icontains=product_name)
            
        if query:
            results = Product.objects.filter(query).select_related('supplier', 'inventory')
            
    elif search_type == 'supplier':
        supplier_id = request.GET.get('supplier_id', '')
        supplier_name = request.GET.get('supplier_name', '')
        
        query = Q()
        if supplier_id:
            query |= Q(supplier_id__icontains=supplier_id)
        if supplier_name:
            query |= Q(supplier_name__icontains=supplier_name)
            
        if query:
            results = Supplier.objects.filter(query).annotate(
                product_count=Count('product')
            )
            
    elif search_type == 'receipt':
        # Tìm kiếm theo số hóa đơn
        order_number = request.GET.get('order_number')
        if order_number:
            results = WarehouseReceipt.objects.filter(
                order_number=order_number
            ).select_related('supplier').prefetch_related(
                'receiptdetail_set',
                'receiptdetail_set__product'
            )
            print("Found receipt:", results.first())  # Debug
            if results.first():
                print("Receipt details:", results.first().receiptdetail_set.all())  # Debug
        else:
            # Tìm kiếm theo khoảng thời gian nếu không có số hóa đơn
            search_type_detail = request.GET.get('search_type')
            
            if search_type_detail == 'all':
                results = WarehouseReceipt.objects.all().select_related('supplier').prefetch_related(
                    'receiptdetail_set',
                    'receiptdetail_set__product'
                )
                
            elif search_type_detail == 'date_range':
                date_from = request.GET.get('date_from')
                date_to = request.GET.get('date_to')
                
                if date_from and date_to:
                    results = WarehouseReceipt.objects.filter(
                        receipt_date__range=[date_from, date_to]
                    ).select_related('supplier').prefetch_related(
                        'receiptdetail_set',
                        'receiptdetail_set__product'
                    )
                    
            elif search_type_detail == 'month':
                month = request.GET.get('month')
                
                if month:
                    try:
                        date = datetime.strptime(month, '%Y-%m')
                        next_month = date + relativedelta(months=1)
                        results = WarehouseReceipt.objects.filter(
                            receipt_date__range=[date, next_month - relativedelta(days=1)]
                        ).select_related('supplier').prefetch_related(
                            'receiptdetail_set',
                            'receiptdetail_set__product'
                        )
                    except ValueError:
                        pass

    context = {
        'results': results,
        'search_type': search_type
    }
    
    return render(request, 'search.html', context)

def report(request):
    reports = None
    report_type = request.GET.get('report_type')
    category_data = []
    supplier_data = []
    total_products = 0
    total_suppliers = 0
    other_categories_count = 0
    other_suppliers_count = 0

    if report_type == 'date_range':
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if date_from and date_to:
            reports = WarehouseReceipt.objects.filter(receipt_date__range=[date_from, date_to]).order_by('-receipt_date')
    
    elif report_type == 'month':
        month = request.GET.get('month')
        if month:
            try:
                date = datetime.strptime(month, '%Y-%m')
                reports = WarehouseReceipt.objects.filter(
                    receipt_date__year=date.year,
                    receipt_date__month=date.month
                ).order_by('-receipt_date')
            except ValueError:
                pass

    if reports:
        # Tính tổng số sản phẩm và nhà cung cấp
        receipt_details = ReceiptDetail.objects.filter(receipt_id__in=reports.values_list('receipt_id', flat=True))
        total_products = receipt_details.aggregate(Sum('quantity'))['quantity__sum'] or 0
        
        # Danh sách nhà cung cấp đã nhập hàng
        supplier_ids = reports.values_list('supplier_id', flat=True).distinct()
        total_suppliers = len(supplier_ids)
        
        # Tính tỉ lệ sản phẩm theo danh mục
        category_stats = receipt_details.values(
            'product__category__category_name'
        ).annotate(
            product_count=Sum('quantity')
        ).order_by('-product_count')
        
        # Lấy top 7 danh mục
        top_categories = list(category_stats[:7])
        
        # Tính số lượng sản phẩm còn lại của các danh mục khác
        if len(category_stats) > 7:
            other_categories_count = sum(item['product_count'] for item in category_stats[7:])
        
        # Xử lý các danh mục None (không có danh mục) và tính phần trăm
        for item in top_categories:
            if item['product__category__category_name'] is None:
                item['product__category__category_name'] = 'Chưa phân loại'
            percent = round((item['product_count'] / total_products) * 100) if total_products > 0 else 0
            category_data.append({
                'category_name': item['product__category__category_name'],
                'product_count': percent
            })
        
        # Tính phần trăm cho nhóm "Khác"
        if len(category_stats) > 7 and total_products > 0:
            other_categories_percent = round((other_categories_count / total_products) * 100)
            other_categories_count = other_categories_percent
        
        # Tính tỉ lệ sản phẩm theo nhà cung cấp
        supplier_stats = receipt_details.values(
            'receipt__supplier__supplier_name'
        ).annotate(
            product_count=Sum('quantity')
        ).order_by('-product_count')
        
        # Lấy top 7 nhà cung cấp
        top_suppliers = list(supplier_stats[:7])
        
        # Tính số lượng sản phẩm còn lại của các nhà cung cấp khác
        if len(supplier_stats) > 7:
            other_suppliers_count = sum(item['product_count'] for item in supplier_stats[7:])
        
        # Tính phần trăm cho từng nhà cung cấp
        for item in top_suppliers:
            percent = round((item['product_count'] / total_products) * 100) if total_products > 0 else 0
            supplier_data.append({
                'supplier_name': item['receipt__supplier__supplier_name'],
                'product_count': percent
            })
            
        # Tính phần trăm cho nhóm "Khác"
        if len(supplier_stats) > 7 and total_products > 0:
            other_suppliers_percent = round((other_suppliers_count / total_products) * 100)
            other_suppliers_count = other_suppliers_percent

    context = {
        'reports': reports,
        'category_data': category_data,
        'supplier_data': supplier_data,
        'total_products': total_products,
        'total_suppliers': total_suppliers,
        'other_categories_count': other_categories_count,
        'other_suppliers_count': other_suppliers_count
    }
    return render(request, 'report.html', context)