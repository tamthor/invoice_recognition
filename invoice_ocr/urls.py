from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

# Redirect root to login
def redirect_to_login(request):
    return redirect('login')

urlpatterns = [
    path('', redirect_to_login, name='root'),
    path('index/', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('save-image/', views.save_image, name='save_image'),
    path('extract-data/', views.extract_data, name='extract_data'),
    path('search/', views.search, name='search'),
    path('report/', views.report, name='report'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)   