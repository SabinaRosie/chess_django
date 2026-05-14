"""
URL configuration for sabina_chess project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

def home(request):
    return JsonResponse({"message": "Sabina Chess Backend is running!"})

from accounts.views import signup, login, forgot_password, verify_otp, reset_password

# Filter only the authentication endpoints for Swagger
auth_patterns = [
    path('api/signup', signup),
    path('api/login', login),
    path('api/forgot-password', forgot_password),
    path('api/verify-otp', verify_otp),
    path('api/reset-password', reset_password),
]

schema_view = get_schema_view(
    openapi.Info(
        title="Sabina Chess Authentication API",
        default_version='v1',
        description="Documentation for Authentication flow (Signup, Login, OTP, etc.)",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    patterns=auth_patterns,
)

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('accounts.urls')),
    
    # Swagger Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/schema/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]
