from django.urls import path
from .views import (
    IssueStatusUpdateAjaxView, MyIssueListView, ProjectListView, ProjectDetailView, ProjectCreateView, ProjectUpdateView,
    IssueListView, IssueDetailView, IssueCreateView, IssueUpdateView, IssueAddRemarkView, TagCreateView, TagDeleteView, TagListView, TagUpdateView,
)

app_name = 'issues'

urlpatterns = [
    path('projects/', ProjectListView.as_view(), name='project_list'),
    path('projects/new/', ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_update'),
    path('issues/', IssueListView.as_view(), name='issue_list'),
    path('issues/<int:pk>/', IssueDetailView.as_view(), name='issue_detail'),
    path('projects/<int:project_pk>/issues/new/', IssueCreateView.as_view(), name='issue_create'),
    path('issues/<int:pk>/edit/', IssueUpdateView.as_view(), name='issue_update'),
    path('issues/<int:pk>/remarks/add/', IssueAddRemarkView.as_view(), name='issue_add_remark'),
    path('my-tasks/', MyIssueListView.as_view(), name='my_issue_list'),

    path('tags/', TagListView.as_view(), name='tag_list'),
    path('tags/create/', TagCreateView.as_view(), name='tag_create'),
    path('tags/<int:pk>/edit/', TagUpdateView.as_view(), name='tag_edit'),
    path('tags/<int:pk>/delete/', TagDeleteView.as_view(), name='tag_delete'),
    path('issues/<int:pk>/update-status-ajax/', IssueStatusUpdateAjaxView.as_view(), name='issue_update_status_ajax'),

]