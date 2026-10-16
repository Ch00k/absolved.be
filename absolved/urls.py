from django.urls import path

from absolved import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("last-confession/", views.last_confession, name="last_confession"),
    path("prepare/", views.prepare, name="prepare"),
    path("examination/", views.save_examination, name="save_examination"),
    path("confession/", views.confession, name="confession"),
    path("confession/record/", views.record_confession, name="record_confession"),
    path("history/", views.history, name="history"),
    path("history/add/", views.add_confession, name="add_confession"),
    path("history/<int:confession_id>/delete/", views.delete_confession, name="delete_confession"),
    path("account/", views.account, name="account"),
    path("account/password/", views.change_password, name="change_password"),
    path("account/delete/", views.delete_account, name="delete_account"),
    path("health/", views.health, name="health"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
