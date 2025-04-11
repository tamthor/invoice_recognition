from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group, Permission

# Quản lý tài khoản người dùng
class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Người dùng phải có email")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra_fields)

# Bảng Tài Khoản Người Dùng
class UserAccount(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    groups = models.ManyToManyField(Group, related_name="useraccount_groups", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="useraccount_permissions", blank=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username

# Bảng Nhà Cung Cấp
class Supplier(models.Model):
    supplier_id = models.AutoField(primary_key=True)
    supplier_name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.supplier_name

    def save(self, *args, **kwargs):
        if not self.pk:  # Chỉ kiểm tra khi tạo mới
            if Supplier.objects.filter(supplier_name=self.supplier_name).exists():
                raise ValidationError(f"Tên nhà cung cấp {self.supplier_name} đã tồn tại.")
        super().save(*args, **kwargs)

# Bảng Danh Mục Sản Phẩm
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
        if not self.pk:  # Chỉ kiểm tra khi tạo mới
            if Category.objects.filter(category_name=self.category_name).exists():
                raise ValidationError(f"Tên danh mục {self.category_name} đã tồn tại.")
            if Category.objects.filter(category_code=self.category_code).exists():
                raise ValidationError(f"Mã danh mục {self.category_code} đã tồn tại.")
        super().save(*args, **kwargs)

# Bảng Sản Phẩm
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

# Bảng Phiếu Nhập Kho
class WarehouseReceipt(models.Model):
    receipt_id = models.AutoField(primary_key=True)
    order_number = models.CharField(max_length=100, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    receipt_date = models.DateField()

    def __str__(self):
        return f"Receipt {self.order_number}"

    def save(self, *args, **kwargs):
        if not self.pk:  # Chỉ kiểm tra khi tạo mới
            if WarehouseReceipt.objects.filter(order_number=self.order_number).exists():
                raise ValidationError(f"Số hóa đơn {self.order_number} đã tồn tại.")
        super().save(*args, **kwargs)

# Bảng Chi Tiết Phiếu Nhập
class ReceiptDetail(models.Model):
    detail_id = models.AutoField(primary_key=True)
    receipt = models.ForeignKey(WarehouseReceipt, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    note = models.TextField(blank=True, null=True)
    class Meta:
        unique_together = ('receipt', 'product')


# Bảng Tồn Kho
class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, primary_key=True)
    quantity_in_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.product.product_name}: {self.quantity_in_stock}"

# ------------------------------- #
#            HÀM HỖ TRỢ           #
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
