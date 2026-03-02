from django.shortcuts import render
from django.http import JsonResponse
import datetime


def home_view(request):
    """
    Home page view - returns a basic HTML welcome page.
    """
    return render(request, "home.html")


def api_root_view(request):
    """
    API root view - returns JSON with API information and available endpoints.
    """
    data = {
        "name": "Authentication Service with OTP",
        "version": "v1",
        "description": "Email-based OTP authentication service with rate limiting and audit logging",
        "endpoints": {
            "auth": {
                "otp_request": "/api/v1/auth/otp/request",
                "otp_verify": "/api/v1/auth/otp/verify",
            },
            "audit": {"logs": "/api/v1/audit/logs"},
            "system": {
                "health": "/api/v1/health",
                "documentation": "Swagger UI will be available at /api/docs/ (coming soon)",
            },
        },
        "status": "operational",
        "timestamp": datetime.datetime.now().isoformat(),
    }
    return JsonResponse(data, status=200, json_dumps_params={"indent": 2})


def health_check_view(request):
    """
    Health check endpoint - returns 200 OK with a battery emoji when service is running.
    """
    data = {
        "status": "healthy",
        "message": "🔋 Service is up and running!",
        "service": "auth-service-otp",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "v1",
    }
    return JsonResponse(data, status=200, json_dumps_params={"indent": 2})
