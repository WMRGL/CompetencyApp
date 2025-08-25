from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.user_login, name='login'),
    path('portfolio/', views.competency, name='portfolio'),
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/<int:task_id>/review/', views.review_task, name='review_task'),
    path('download/evidence/<int:task_id>/', views.download_evidence, name='download_evidence'),
    path("view-feedback/<int:task_id>/", views.view_feedback, name="view_feedback"),
    path('submissions/', views.create_submission, name='submissions'),
    path('messages/', views.messages, name='messages'),
    path('create_submission/', views.create_submission, name='create_submission'),
    path('competency/', views.competency, name='competency'),
    path('team_dashboard/', views.team_dashboard, name='team_dashboard'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('resubmissions/<int:task_id>/', views.resubmit_task, name='resubmit_task'),
    path('assign-competency/', views.assign_competency, name='assign_competency'),
    path('team_dashboard/', views.team_dashboard, name='team_dashboard'),
    path('ajax/get-objectives/', views.get_template_objectives, name='get_template_objectives'),
]

