from django import forms

from .models import Project, Issue, IssueRemarkLog
from .choices import IssueEnvironmentChoices, IssuePriorityChoices, IssueStatusChoices, IssueTypeChoices, TeamMemberRoleChoices, UserModelChoiceField
from .models import Tag
from django.contrib.auth import get_user_model
User = get_user_model()

# Create custom field classes to override the displayed option label
class UserFullChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # Fallback to username if first and last name are empty
        return obj.get_full_name() or obj.username

class UserFullMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        # Fallback to username if first and last name are empty
        return obj.get_full_name() or obj.username

class ProjectForm(forms.ModelForm):
    owner = UserModelChoiceField(
        queryset=User.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
    )

    class Meta:
        model = Project
        fields = [
            'name',
            'code',
            'description',
            'owner',
            'team',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'team': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class IssueForm(forms.ModelForm):
    priority = forms.ChoiceField(
        choices=IssuePriorityChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    environment = forms.ChoiceField(
        choices=IssueEnvironmentChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    status = forms.ChoiceField(
        choices=IssueStatusChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    issue_type = forms.ChoiceField(
        choices=IssueTypeChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    assignee = UserFullChoiceField(
        queryset=User.objects.filter(is_superuser=False, is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
    )
    co_assignees = UserFullMultipleChoiceField(
        queryset=User.objects.filter(is_superuser=False, is_active=True),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-multi', 'multiple': 'multiple'}),
        required=False,
        help_text="Hold down Ctrl (or Cmd on Mac) to select multiple, or search above if enabled."
    )

    class Meta:
        model = Issue
        fields = [
            'project',
            'title',
            'description',
            'drive_url',
            'issue_type',
            'reporter',
            'assignee',
            'co_assignees',
            'priority',
            'environment',
            'status',
            'time_estimate_hours',
            'related_issue',
            'tags',
            'remarks',
            'qa_note',
            'image_1',
            'image_2',
            'image_3',
            'image_4',
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'drive_url': forms.TextInput(attrs={'class': 'form-control'}),
            'reporter': forms.Select(attrs={'class': 'form-select'}),
            'time_estimate_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            'related_issue': forms.Select(attrs={'class': 'form-select'}),
            'tags': forms.SelectMultiple(attrs={"class": "form-select select2-multi"}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'qa_note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'image_1': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'image_2': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'image_3': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'image_4': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        # Extract the user object cleanly before instantiating the form fields
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # 1. Filter the related tasks queryset
        if 'related_issue' in self.fields:
            self.fields['related_issue'].queryset = Issue.objects.filter(
                issue_type=IssueTypeChoices.TASK
            )

        # 2. Dynamic Status filtering based on team member roles
        if user and hasattr(user, 'team_member'):
            role = user.team_member.role
            all_status_choices = list(IssueStatusChoices.choices)

            if role == TeamMemberRoleChoices.DEVELOPER:
                allowed_statuses = ['open', 'dev_in_progress', 'hold', 'scope_review', 'rejected',  'reopen']
            elif role == TeamMemberRoleChoices.QA:
                allowed_statuses = ['open', 'ready_for_qa', 'qa_in_progress',  'done', 'closed' ,  'reopen']
            else:
                # If staff/admin or fallback role, preserve all options
                allowed_statuses = [choice[0] for choice in all_status_choices]

            # Re-assign filtered options to the active choice field
            self.fields['status'].choices = [
                (value, label) for value, label in all_status_choices if value in allowed_statuses
            ]


class IssueRemarkLogForm(forms.ModelForm):
    class Meta:
        model = IssueRemarkLog
        fields = [
            'issue',
            'from_status',
            'to_status',
            'remark',
            'qa_note',
        ]
        widgets = {
            'issue': forms.HiddenInput(),
            'from_status': forms.Select(choices=IssueStatusChoices.choices, attrs={'class': 'form-control'}),
            'to_status': forms.Select(choices=IssueStatusChoices.choices, attrs={'class': 'form-control'}),
            'remark': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'qa_note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "slug", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }