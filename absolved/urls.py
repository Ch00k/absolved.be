from django.urls import path

from absolved import views

urlpatterns = [
    path("", views.home, name="home"),  # ty: ignore[no-matching-overload]
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),  # ty: ignore[no-matching-overload]
    path("last-confession/", views.last_confession, name="last_confession"),  # ty: ignore[no-matching-overload]
    path("prepare/", views.prepare, name="prepare"),  # ty: ignore[no-matching-overload]
    path("examination/", views.save_examination, name="save_examination"),  # ty: ignore[no-matching-overload]
    path("confession/", views.confession, name="confession"),  # ty: ignore[no-matching-overload]
    path("confession/record/", views.record_confession, name="record_confession"),  # ty: ignore[no-matching-overload]
    path("history/", views.history, name="history"),  # ty: ignore[no-matching-overload]
    path("history/add/", views.add_confession, name="add_confession"),  # ty: ignore[no-matching-overload]
    path("history/<int:confession_id>/delete/", views.delete_confession, name="delete_confession"),  # ty: ignore[no-matching-overload]
    path("account/", views.account, name="account"),
    path("account/password/", views.change_password, name="change_password"),  # ty: ignore[no-matching-overload]
    path("account/delete/", views.delete_account, name="delete_account"),  # ty: ignore[no-matching-overload]
    path("sw.js", views.service_worker, name="service_worker"),  # ty: ignore[no-matching-overload]
    path("manifest.webmanifest", views.manifest, name="manifest"),  # ty: ignore[no-matching-overload]
]
