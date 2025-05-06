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

# ------------------------------- #
#         SUPPORT FUNCTION        #
# ------------------------------- #

def add_warehouse_receipt(supplier_id, order_number, receipt_date):
    try:
        supplier = Supplier.objects.filter(supplier_id=supplier_id).first()
        if not supplier:
            return "Lỗi: Nhà cung cấp không tồn tại."

        if WarehouseReceipt.objects.filter(order_number=order_number).exists():
            return "Lỗi: Hóa đơn đã tồn tại."

        WarehouseReceipt.objects.create(
            supplier=supplier,
            order_number=order_number,
            receipt_date=receipt_date
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

def process_invoice_data(supplier_id, order_number, receipt_date, product_data_list):
    """
    Xử lý dữ liệu sau khi nhận dạng từ hóa đơn
    
    Args:
        supplier_id (str): Mã nhà cung cấp
        order_number (str): Số hóa đơn
        receipt_date (date): Ngày hóa đơn
        product_data_list (list): Danh sách sản phẩm với cấu trúc [ma_hang, so_luong]
    
    Returns:
        dict: Kết quả xử lý với các thông tin:
            - success: True/False
            - message: Thông báo kết quả
            - details: Chi tiết các sản phẩm đã xử lý
    """
    try:
        # Kiểm tra nhà cung cấp có tồn tại không
        supplier = Supplier.objects.filter(supplier_id=supplier_id).first()
        if not supplier:
            return {
                'success': False,
                'message': 'Nhà cung cấp không tồn tại',
                'details': []
            }
            
        # Kiểm tra số hóa đơn đã tồn tại chưa
        if WarehouseReceipt.objects.filter(order_number=order_number).exists():
            return {
                'success': False,
                'message': 'Số hóa đơn đã tồn tại',
                'details': []
            }
            
        # Tạo phiếu nhập kho mới
        warehouse_receipt = WarehouseReceipt.objects.create(
            supplier=supplier,
            order_number=order_number,
            receipt_date=receipt_date
        )
        
        processed_products = []
        skipped_products = []
        
        # Xử lý từng sản phẩm
        for product_data in product_data_list:
            ma_hang = product_data[0]
            so_luong = int(product_data[1])
            
            # Kiểm tra sản phẩm có tồn tại không
            product = Product.objects.filter(product_id=ma_hang).first()
            if not product:
                skipped_products.append({
                    'ma_hang': ma_hang,
                    'reason': 'Sản phẩm không tồn tại'
                })
                continue
                
            # Cập nhật tồn kho
            inventory, created = Inventory.objects.get_or_create(product=product)
            inventory.quantity_in_stock += so_luong
            inventory.save()
            
            # Thêm chi tiết phiếu nhập
            ReceiptDetail.objects.create(
                receipt=warehouse_receipt,
                product=product,
                quantity=so_luong
            )
            
            processed_products.append({
                'ma_hang': ma_hang,
                'ten_hang': product.product_name,
                'so_luong': so_luong
            })
            
        return {
            'success': True,
            'message': 'Xử lý hóa đơn thành công',
            'details': {
                'processed_products': processed_products,
                'skipped_products': skipped_products
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Lỗi khi xử lý hóa đơn: {str(e)}',
            'details': []
        }
