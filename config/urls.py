from django.urls import include, path

urlpatterns = [
    path("", include("absolved.urls")),
    path("i18n/", include("django.conf.urls.i18n")),
]
