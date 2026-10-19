from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from django.views.i18n import set_language

urlpatterns = [
    path("", include("absolved.urls")),
    # Exempt, since a forged request can change no more than the language, while the token a page was rendered with
    # is out of date once a login in another tab, or a kept copy of the page, outlives it.
    path("i18n/setlang/", csrf_exempt(set_language), name="set_language"),
]
