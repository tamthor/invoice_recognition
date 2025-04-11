from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.index, name = "index"),
    path('camera/', views.camera, name='camera'),
    path('save-image/', views.save_image, name='save_image'),
    path('extract-data/', views.extract_data, name='extract_data'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)   