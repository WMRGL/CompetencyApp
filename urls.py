from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.user_login, name='login'),
    path('portfolio/', views.competency, name='portfolio'),
    path('tasks/', views.tasks, name='tasks'),
    path('submissions/', views.create_submission, name='submissions'),
    path('messages/', views.messages, name='messages'),
    path('create_submission/', views.create_submission, name='create_submission'),
    path('competency/', views.competency, name='competency'),
    path('team_dashboard/', views.team_dashboard, name='team_dashboard'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]

