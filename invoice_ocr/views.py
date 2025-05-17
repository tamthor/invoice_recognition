from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import logout_then_login
from django.db.models import Q, Count, Sum
import os
from datetime import datetime
import json
from django.conf import settings
from .services.detect import detect_text, process_image, set_detect_img_path
from .services.image_processing import alignImages
from .models import Product, Supplier, WarehouseReceipt, Inventory, process_invoice_data, ReceiptDetail, InvoiceTemplate
from dateutil.relativedelta import relativedelta
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO

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
    # Lấy danh sách mẫu hóa đơn để hiển thị trong selectbox
    invoice_templates = InvoiceTemplate.objects.all()
    return render(request, 'index.html', {'invoice_templates': invoice_templates})

@login_required(login_url='login')
@csrf_exempt
def save_image(request):
    if request.method == 'POST':
        try:
            # Lấy file ảnh từ request
            image_file = request.FILES['image']
            
            # Lấy ID mẫu hóa đơn
            template_id = request.POST.get('template_id')
            
            # Nếu có template_id, lấy thông tin mẫu hóa đơn
            template = None
            if template_id:
                try:
                    template = InvoiceTemplate.objects.get(id=template_id)
                except InvoiceTemplate.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Không tìm thấy mẫu hóa đơn'
                    })
            
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
            process_image(captured_path, aligned_path, template_id=template_id)
            
            # Set đường dẫn ảnh đã căn chỉnh cho detect_text
            set_detect_img_path(aligned_path, template_id=template_id)
            
            # Nhận dạng văn bản với thông tin từ mẫu hóa đơn
            result = None
            if template:
                # Gọi detect_text với thông tin từ mẫu hóa đơn
                result = detect_text(
                    supplier_keywords=template.get_supplier_code_keywords_list(),
                    invoice_keywords=template.get_invoice_number_keywords_list(),
                    product_code_keywords=template.get_product_code_keywords_list(),
                    quantity_keywords=template.get_quantity_keywords_list(),
                    num_columns=template.num_columns
                )
            else:
                # Gọi detect_text không có tham số
                result = detect_text()
            
            if result:
                # Kiểm tra nếu có lỗi cột không khớp
                if isinstance(result, dict) and 'error' in result and result['error'] == 'column_mismatch':
                    # Trả về lỗi trực tiếp cho frontend xử lý
                    return JsonResponse({
                        'success': True,
                        'extracted_data': result
                    })
                
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
                        product_data_list=[[row[0], row[1]] for row in result.get('data_matrix') if row[0] and row[1]],
                        created_by=request.user
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
            template_id = data.get('template_id')
            set_detect_img_path(image_path, template_id=template_id)
            
            # Nhận dạng văn bản với thông tin từ mẫu hóa đơn
            result = None
            if template_id:
                try:
                    template = InvoiceTemplate.objects.get(id=template_id)
                    # Gọi detect_text với thông tin từ mẫu hóa đơn
                    result = detect_text(
                        supplier_keywords=template.get_supplier_code_keywords_list(),
                        invoice_keywords=template.get_invoice_number_keywords_list(),
                        product_code_keywords=template.get_product_code_keywords_list(),
                        quantity_keywords=template.get_quantity_keywords_list(),
                        num_columns=template.num_columns
                    )
                except InvoiceTemplate.DoesNotExist:
                    # Nếu không tìm thấy mẫu, sử dụng detect_text không tham số
                    result = detect_text()
            else:
                # Gọi detect_text không có tham số
                result = detect_text()
            
            if result:
                # Kiểm tra nếu có lỗi cột không khớp
                if isinstance(result, dict) and 'error' in result and result['error'] == 'column_mismatch':
                    # Trả về lỗi trực tiếp cho frontend xử lý
                    return JsonResponse({
                        'success': True,
                        'extracted_data': result
                    })
                
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

@login_required(login_url='login')
def export_pdf(request):
    # Get parameters from the request
    report_type = request.GET.get('report_type')
    reports = None
    date_from = None
    date_to = None
    month_str = None
    
    # Fetch data based on report type (similar to report view)
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
                month_str = date.strftime('%m/%Y')
                date_from = date.replace(day=1).strftime('%d/%m/%Y')
                last_day = (date.replace(day=1) + relativedelta(months=1, days=-1)).day
                date_to = date.replace(day=last_day).strftime('%d/%m/%Y')
                
                reports = WarehouseReceipt.objects.filter(
                    receipt_date__year=date.year,
                    receipt_date__month=date.month
                ).order_by('-receipt_date')
            except ValueError:
                pass
    
    if not reports:
        return HttpResponse("Không có dữ liệu để xuất")
    
    # Format date strings for display
    if date_from and not month_str:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        date_from = date_from_obj.strftime('%d/%m/%Y')
    
    if date_to and not month_str:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        date_to = date_to_obj.strftime('%d/%m/%Y')
    
    # Aggregate product data from all reports
    receipt_details = ReceiptDetail.objects.filter(
        receipt_id__in=reports.values_list('receipt_id', flat=True)
    ).select_related('product', 'receipt__supplier')
    
    # Create dictionary to aggregate products by ID
    product_summary = {}
    for detail in receipt_details:
        product_id = detail.product.product_id
        if product_id not in product_summary:
            product_summary[product_id] = {
                'product_id': product_id,
                'product_name': detail.product.product_name,
                'quantity': 0,
                'supplier': detail.receipt.supplier.supplier_name
            }
        product_summary[product_id]['quantity'] += detail.quantity
    
    # Convert to list and sort by product ID
    product_data = list(product_summary.values())
    product_data.sort(key=lambda x: x['product_id'])
    
    # Create PDF document
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    elements = []
    
    # Đường dẫn đến font DejaVu Sans
    font_path = os.path.join(settings.BASE_DIR, 'invoice_ocr', 'static', 'fonts', 'DejaVuSans.ttf')
    bold_font_path = os.path.join(settings.BASE_DIR, 'invoice_ocr', 'static', 'fonts', 'DejaVuSans-Bold.ttf')

    # Đăng ký font với ReportLab
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    pdfmetrics.registerFont(TTFont('DejaVu-Bold', bold_font_path))

    # Sử dụng font trong style
    styles = getSampleStyleSheet()
    styles['Title'].fontName = 'DejaVu'
    styles['Title'].fontSize = 16
    styles['Title'].alignment = TA_CENTER
    styles['Title'].spaceAfter = 10
    
    # Style cho tổng số hóa đơn/sản phẩm căn phải
    styles.add(ParagraphStyle(name='Normal_Right_Bold', fontName='DejaVu-Bold', fontSize=12, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_C', fontName='DejaVu', fontSize=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='Normal_R', fontName='DejaVu', fontSize=10, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_L', fontName='DejaVu', fontSize=10, alignment=TA_LEFT))
    
    # Title
    title = Paragraph("PHIẾU THỐNG KÊ NHẬP KHO", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 10))
    
    # Date range
    date_text = f"Từ ngày: {date_from}  Đến ngày: {date_to}"
    date_paragraph = Paragraph(date_text, styles['Normal_C'])
    elements.append(date_paragraph)
    elements.append(Spacer(1, 20))
    
    # Table header
    table_data = [
        ['STT', 'Mã hàng', 'Tên hàng', 'Số lượng', 'Nhà cung cấp']
    ]
    
    # Hàm xử lý unicode an toàn
    def safe_unicode(val):
        if val is None:
            return ""
        if isinstance(val, bytes):
            return val.decode('utf-8', errors='replace')
        return str(val)

    # Table rows
    for idx, product in enumerate(product_data, 1):
        table_data.append([
            str(idx),
            safe_unicode(product['product_id']),
            safe_unicode(product['product_name']),
            str(product['quantity']),
            safe_unicode(product['supplier'])
        ])
    
    # Thêm dòng tổng, căn phải số
    table_data.append([
        'Tổng số phiếu nhập:',
        '', '', '',  # các cột trống
        Paragraph(f"<b>{reports.count()}</b>", styles['Normal_Right_Bold'])
    ])
    table_data.append([
        'Tổng số sản phẩm:',
        '', '', '',  # các cột trống
        Paragraph(f"<b>{sum(p['quantity'] for p in product_data)}</b>", styles['Normal_Right_Bold'])
    ])
    
    # Tạo bảng
    table = Table(table_data, colWidths=[30, 70, 200, 70, 150])
    
    # Style bảng
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -3), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (0, -3), 'CENTER'),
        ('ALIGN', (3, 1), (3, -3), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVu-Bold'),
        # Dòng tổng: căn phải số, bôi đậm
        ('FONTNAME', (0, -2), (0, -1), 'DejaVu-Bold'),
        ('ALIGN', (4, -2), (4, -1), 'RIGHT'),
        ('SPAN', (0, -2), (3, -2)),  # Gộp các cột dòng tổng số phiếu nhập
        ('SPAN', (0, -1), (3, -1)),  # Gộp các cột dòng tổng số sản phẩm
        ('LINEABOVE', (0, -2), (-1, -2), 1, colors.black),
    ])
    table.setStyle(table_style)
    elements.append(table)
    
    # Add creation date
    elements.append(Spacer(1, 20))
    creation_date = datetime.now().strftime("%d/%m/%Y")
    date_paragraph = Paragraph(f"Ngày lập: {creation_date}", styles['Normal_R'])
    elements.append(date_paragraph)
    
    # Build PDF
    doc.build(elements)
    
    # Return PDF as response
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=\"thong_ke_nhap_kho.pdf\"'
    
    return response

@login_required(login_url='login')
def invoice_templates(request):
    """Hiển thị danh sách các mẫu hóa đơn"""
    templates = InvoiceTemplate.objects.all().order_by('-created_at')
    return render(request, 'invoice_templates.html', {
        'templates': templates
    })

@login_required(login_url='login')
def invoice_add_template(request):
    """Thêm mẫu hóa đơn mới"""
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            name = request.POST.get('name')
            template_image = request.FILES.get('template_image')
            supplier_code_keywords = request.POST.get('supplier_code_keywords')
            invoice_number_keywords = request.POST.get('invoice_number_keywords')
            product_code_keywords = request.POST.get('product_code_keywords')
            quantity_keywords = request.POST.get('quantity_keywords')
            num_columns = request.POST.get('num_columns')
            
            # Tạo mẫu hóa đơn mới
            template = InvoiceTemplate(
                name=name,
                template_image=template_image,
                supplier_code_keywords=supplier_code_keywords,
                invoice_number_keywords=invoice_number_keywords,
                product_code_keywords=product_code_keywords,
                quantity_keywords=quantity_keywords,
                num_columns=num_columns
            )
            template.save()
            
            # Chuyển hướng về trang danh sách mẫu hóa đơn
            return redirect('invoice_templates')
        except Exception as e:
            return render(request, 'invoice_add_template.html', {
                'error': f'Lỗi khi thêm mẫu hóa đơn: {str(e)}'
            })
    
    return render(request, 'invoice_add_template.html')

@login_required(login_url='login')
def invoice_edit_template(request, template_id):
    """Chỉnh sửa mẫu hóa đơn"""
    try:
        template = InvoiceTemplate.objects.get(id=template_id)
    except InvoiceTemplate.DoesNotExist:
        return redirect('invoice_templates')
    
    if request.method == 'POST':
        try:
            # Cập nhật thông tin
            template.name = request.POST.get('name')
            if 'template_image' in request.FILES:
                template.template_image = request.FILES['template_image']
            template.supplier_code_keywords = request.POST.get('supplier_code_keywords')
            template.invoice_number_keywords = request.POST.get('invoice_number_keywords')
            template.product_code_keywords = request.POST.get('product_code_keywords')
            template.quantity_keywords = request.POST.get('quantity_keywords')
            template.num_columns = request.POST.get('num_columns')
            template.save()
            
            return redirect('invoice_templates')
        except Exception as e:
            return render(request, 'invoice_edit_template.html', {
                'template': template,
                'error': f'Lỗi khi cập nhật mẫu hóa đơn: {str(e)}'
            })
    
    return render(request, 'invoice_edit_template.html', {
        'template': template
    })

@login_required(login_url='login')
def invoice_delete_template(request, template_id):
    """Xóa mẫu hóa đơn"""
    if request.method == 'POST':
        try:
            template = InvoiceTemplate.objects.get(id=template_id)
            template.delete()
        except InvoiceTemplate.DoesNotExist:
            pass
    
    return redirect('invoice_templates')