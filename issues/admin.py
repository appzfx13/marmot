from django.contrib import admin
from .models import Issue
from .forms import IssueForm


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    form = IssueForm
    autocomplete_fields = ["related_issue"]
    search_fields = ["title", "description"]