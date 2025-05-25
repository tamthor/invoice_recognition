from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group, Permission

# Manage user accounts table
class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Người dùng phải có email")
        if not username:
            raise ValueError("Người dùng phải có username")
            
        email = self.normalize_email(email)
        user = self.model(
            username=username,
            email=email,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)

# User accounts table
class UserAccount(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    groups = models.ManyToManyField(Group, related_name="useraccount_groups", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="useraccount_permissions", blank=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

# Suppliers table
class Supplier(models.Model):
    supplier_id = models.AutoField(primary_key=True)
    supplier_name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.supplier_name

    def save(self, *args, **kwargs):
        if not self.pk:  # Only check when creating new
            if Supplier.objects.filter(supplier_name=self.supplier_name).exists():
                raise ValidationError(f"Tên nhà cung cấp {self.supplier_name} đã tồn tại.")
        super().save(*args, **kwargs)

# Categories table
class Category(models.Model):
    category_name = models.CharField(max_length=200, unique=True)
    category_code = models.CharField(
        max_length=2,
        unique=True,
        help_text="Mã danh mục (2 ký tự, ví dụ: CA)"
    )

    def __str__(self):
        return self.category_name

    def save(self, *args, **kwargs):
        if not self.pk:  # Only check when creating new
            if Category.objects.filter(category_name=self.category_name).exists():
                raise ValidationError(f"Tên danh mục {self.category_name} đã tồn tại.")
            if Category.objects.filter(category_code=self.category_code).exists():
                raise ValidationError(f"Mã danh mục {self.category_code} đã tồn tại.")
        super().save(*args, **kwargs)

# Products table
class Product(models.Model):
    product_id = models.CharField(
        max_length=10,
        primary_key=True,
        unique=True,
        editable=True
    )
    product_name = models.CharField(max_length=200)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    unit = models.CharField(max_length=50)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.product_name

# Receipts table
class WarehouseReceipt(models.Model):
    receipt_id = models.AutoField(primary_key=True)
    order_number = models.CharField(max_length=100, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    receipt_date = models.DateField()
    created_by = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, null=True, related_name="created_receipts")

    def __str__(self):
        return f"Receipt {self.order_number}"

    def save(self, *args, **kwargs):
        if not self.pk:  # Only check when creating new
            if WarehouseReceipt.objects.filter(order_number=self.order_number).exists():
                raise ValidationError(f"Số hóa đơn {self.order_number} đã tồn tại.")
        super().save(*args, **kwargs)

# Receipt details table
class ReceiptDetail(models.Model):
    detail_id = models.AutoField(primary_key=True)
    receipt = models.ForeignKey(WarehouseReceipt, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    note = models.TextField(blank=True, null=True)
    class Meta:
        unique_together = ('receipt', 'product')


# Inventory Table
class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, primary_key=True)
    quantity_in_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.product.product_name}: {self.quantity_in_stock}"

# Invoice Template model
class InvoiceTemplate(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name="Tên mẫu hóa đơn")
    template_image = models.ImageField(upload_to='invoice_templates/', verbose_name="Ảnh mẫu hóa đơn")
    
    # Từ khóa nhận dạng
    supplier_code_keywords = models.TextField(
        verbose_name="Từ khóa nhận dạng mã nhà cung cấp",
        help_text="Các từ khóa cách nhau bằng dấu phẩy (,)"
    )
    invoice_number_keywords = models.TextField(
        verbose_name="Từ khóa nhận dạng số hóa đơn/đơn hàng", 
        help_text="Các từ khóa cách nhau bằng dấu phẩy (,)"
    )
    product_code_keywords = models.TextField(
        verbose_name="Từ khóa nhận dạng cột mã hàng", 
        help_text="Các từ khóa cách nhau bằng dấu phẩy (,)"
    )
    quantity_keywords = models.TextField(
        verbose_name="Từ khóa nhận dạng cột số lượng", 
        help_text="Các từ khóa cách nhau bằng dấu phẩy (,)"
    )
    
    # Thông tin cấu trúc bảng
    num_columns = models.PositiveIntegerField(
        default=0, 
        verbose_name="Số cột trong bảng"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    def get_supplier_code_keywords_list(self):
        """Trả về danh sách các từ khóa nhận dạng mã nhà cung cấp"""
        return [kw.strip() for kw in self.supplier_code_keywords.split(',') if kw.strip()]
    
    def get_invoice_number_keywords_list(self):
        """Trả về danh sách các từ khóa nhận dạng số hóa đơn"""
        return [kw.strip() for kw in self.invoice_number_keywords.split(',') if kw.strip()]
    
    def get_product_code_keywords_list(self):
        """Trả về danh sách các từ khóa nhận dạng cột mã hàng"""
        return [kw.strip() for kw in self.product_code_keywords.split(',') if kw.strip()]
    
    def get_quantity_keywords_list(self):
        """Trả về danh sách các từ khóa nhận dạng cột số lượng"""
        return [kw.strip() for kw in self.quantity_keywords.split(',') if kw.strip()]

# ------------------------------- #
#         SUPPORT FUNCTION        #
# ------------------------------- #

def add_warehouse_receipt(supplier_id, order_number, receipt_date, created_by=None):
    try:
        supplier = Supplier.objects.filter(supplier_id=supplier_id).first()
        if not supplier:
            return "Lỗi: Nhà cung cấp không tồn tại."

        if WarehouseReceipt.objects.filter(order_number=order_number).exists():
            return "Lỗi: Hóa đơn đã tồn tại."

        WarehouseReceipt.objects.create(
            supplier=supplier,
            order_number=order_number,
            receipt_date=receipt_date,
            created_by=created_by
        )
        return "Thêm phiếu nhập kho thành công."

    except Exception as e:
        return f"Lỗi: {str(e)}"

def add_receipt_detail(order_number, product_id, quantity, note=None):
    try:
        receipt = WarehouseReceipt.objects.filter(order_number=order_number).first()
        if not receipt:
            return "Lỗi: Hóa đơn không tồn tại."

        product = Product.objects.filter(product_id=product_id).first()
        if not product:
            return "Lỗi: Sản phẩm không tồn tại."

        ReceiptDetail.objects.create(
            receipt=receipt,
            product=product,
            quantity=quantity,
            note=note
        )
        return f"Thêm sản phẩm {product.product_name} vào phiếu nhập thành công."

    except Exception as e:
        return f"Lỗi: {str(e)}"

def update_inventory(product_id, quantity):
    try:
        product = Product.objects.filter(product_id=product_id).first()
        if not product:
            return "Lỗi: Sản phẩm không tồn tại."

        inventory, created = Inventory.objects.get_or_create(product=product)
        inventory.quantity_in_stock = quantity
        inventory.save()

        return f"Cập nhật tồn kho của {product.product_name} thành {quantity} thành công."

    except Exception as e:
        return f"Lỗi: {str(e)}"

def process_invoice_data(supplier_id, order_number, receipt_date, product_data_list, created_by=None):
    """
    Xử lý dữ liệu sau khi nhận dạng từ hóa đơn
    """
    try:
        print(f"\n=== DEBUG PROCESS_INVOICE_DATA ===")
        print(f"Supplier ID: {supplier_id}")
        print(f"Order Number: {order_number}")
        print(f"Receipt Date: {receipt_date}")
        print(f"Product Data List: {product_data_list}")
        
        # Kiểm tra nhà cung cấp có tồn tại không
        supplier = Supplier.objects.filter(supplier_id=supplier_id).first()
        if not supplier:
            print("Supplier not found")
            return {
                'success': False,
                'message': 'Nhà cung cấp không tồn tại',
                'details': []
            }
            
        # Kiểm tra số hóa đơn đã tồn tại chưa
        if WarehouseReceipt.objects.filter(order_number=order_number).exists():
            print("Order number already exists")
            return {
                'success': False,
                'message': 'Số hóa đơn đã tồn tại',
                'details': []
            }
            
        # Tạo phiếu nhập kho mới
        warehouse_receipt = WarehouseReceipt.objects.create(
            supplier=supplier,
            order_number=order_number,
            receipt_date=receipt_date,
            created_by=created_by
        )
        print(f"Created warehouse receipt: {warehouse_receipt.receipt_id}")
        
        processed_products = []
        skipped_products = []
        
        # Xử lý từng sản phẩm
        for product_data in product_data_list:
            ma_hang = product_data[0]
            try:
                so_luong = int(product_data[1])
                print(f"\nProcessing product: {ma_hang}, quantity: {so_luong}")
            except ValueError as e:
                print(f"Error converting quantity for {ma_hang}: {e}")
                skipped_products.append({
                    'ma_hang': ma_hang,
                    'reason': f'Lỗi chuyển đổi số lượng: {str(e)}'
                })
                continue
            
            # Kiểm tra sản phẩm có tồn tại không
            product = Product.objects.filter(product_id=ma_hang).first()
            if not product:
                print(f"Product not found: {ma_hang}")
                skipped_products.append({
                    'ma_hang': ma_hang,
                    'reason': 'Sản phẩm không tồn tại'
                })
                continue
                
            # Kiểm tra nhà cung cấp của sản phẩm có khớp không
            if int(product.supplier.supplier_id) != int(supplier_id):
                print(f"Product supplier mismatch: {ma_hang}")
                skipped_products.append({
                    'ma_hang': ma_hang,
                    'reason': f'Sản phẩm không thuộc nhà cung cấp {supplier.supplier_name}'
                })
                continue
                
            try:
                # Cập nhật tồn kho
                inventory, created = Inventory.objects.get_or_create(product=product)
                inventory.quantity_in_stock += so_luong
                inventory.save()
                print(f"Updated inventory for {ma_hang}")
                
                # Thêm chi tiết phiếu nhập
                ReceiptDetail.objects.create(
                    receipt=warehouse_receipt,
                    product=product,
                    quantity=so_luong
                )
                print(f"Created receipt detail for {ma_hang}")
                
                processed_products.append({
                    'ma_hang': ma_hang,
                    'ten_hang': product.product_name,
                    'so_luong': so_luong
                })
            except Exception as e:
                print(f"Error processing product {ma_hang}: {str(e)}")
                skipped_products.append({
                    'ma_hang': ma_hang,
                    'reason': f'Lỗi xử lý: {str(e)}'
                })
            
        print("\n=== PROCESSING RESULTS ===")
        print(f"Processed products: {processed_products}")
        print(f"Skipped products: {skipped_products}")
        
        return {
            'success': True,
            'message': 'Xử lý hóa đơn thành công',
            'details': {
                'processed_products': processed_products,
                'skipped_products': skipped_products
            }
        }
        
    except Exception as e:
        print(f"Error in process_invoice_data: {str(e)}")
        return {
            'success': False,
            'message': f'Lỗi khi xử lý hóa đơn: {str(e)}',
            'details': []
        }
