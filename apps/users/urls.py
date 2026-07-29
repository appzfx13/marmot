from django.urls import path
from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from .views import (
    # DashboardView,
    # DownloadDBView,
    MarmotDashboardView,
    MarmotLoginView,
    # TeamListView,
    # TeamCreateView,
    # TeamUpdateView,
    # TeamDeleteView,
    # TeamMemberListView,
    # TeamMemberCreateView,
    # TeamMemberUpdateView,
    # TeamMemberDeleteView,
)

app_name = 'users'

urlpatterns = [
    # path('', auth_views.LoginView.as_view(
    #     template_name='registration/login.html',
    #     redirect_authenticated_user=True,
    #     next_page='/dashboard/'
    # ), name='login'),
    # path('dashboard/', DashboardView.as_view(), name='dashboard'),
    # path('teams/', TeamListView.as_view(), name='team_list'),
    # path('teams/create/', TeamCreateView.as_view(), name='team_create'),
    # path('teams/<int:pk>/edit/', TeamUpdateView.as_view(), name='team_edit'),
    # path('teams/<int:pk>/delete/', TeamDeleteView.as_view(), name='team_delete'),

    # path('teams/members/', TeamMemberListView.as_view(), name='teammember_list'),
    # path('teams/members/create/', TeamMemberCreateView.as_view(), name='teammember_create'),
    # path('teams/members/<int:pk>/edit/', TeamMemberUpdateView.as_view(), name='teammember_edit'),
    # path('teams/members/<int:pk>/delete/', TeamMemberDeleteView.as_view(), name='teammember_delete'),
    # path('download-db/', DownloadDBView.as_view(), name='download_db'),

    # path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('users:login')), name='logout'),

    # MARMOT
    path('', MarmotLoginView.as_view(), name='marmot-login'),
    path('marmot/dashboard/', MarmotDashboardView.as_view(), name='marmot-dashboard'),
]