from django import forms
from django.contrib.auth import get_user_model


from issues.choices import TeamMemberRoleChoices 


from .models import Team, TeamMember


User = get_user_model()  # ADDED



class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Team name',
                }
            ),
            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Describe the team',
                    'rows': 3,
                }
            ),
        }



class TeamMemberForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'First name',
            }
        ),
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Last name',
            }
        ),
    )
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Username',
            }
        ),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Email address',
            }
        ),
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Password',
            }
        ),
    )
    confirm_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Confirm Password',
            }
        ),
    )


    class Meta:
        model = TeamMember
        fields = [
            'team',
            'phone',
            'employee_id',
            'date_joined_company',
            'is_active_developer',
            'role',
        ]
        widgets = {
            'team': forms.Select(
                attrs={
                    'class': 'form-select',
                }
            ),
            'phone': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Phone number',
                }
            ),
            'employee_id': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Employee ID',
                }
            ),
            'date_joined_company': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),
            'is_active_developer': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input',
                }
            ),
            'role': forms.Select(
                choices=TeamMemberRoleChoices.choices,
                attrs={
                    'class': 'form-select',
                }
            ),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['username'].initial = self.instance.user.username
            self.fields['email'].initial = self.instance.user.email


    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password or confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned_data


    def clean_username(self):
        username = self.cleaned_data['username']
        if not self.instance.pk:
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError('A user with this username already exists.')
        else:
            if User.objects.filter(username=username).exclude(pk=self.instance.user_id).exists():
                raise forms.ValidationError('A user with this username already exists.')
        return username


    def clean_employee_id(self):
        employee_id = self.cleaned_data.get('employee_id')
        if not employee_id:
            return employee_id
        if not self.instance.pk:
            if TeamMember.objects.filter(employee_id=employee_id).exists():
                raise forms.ValidationError('A team member with this employee ID already exists.')
        else:
            if TeamMember.objects.filter(employee_id=employee_id).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('A team member with this employee ID already exists.')
        return employee_id


    def save(self, commit=True):
        team_member = super().save(commit=False)


        user = getattr(team_member, 'user', None)
        if user is None or not user.pk:
            user = User()


        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)


        if commit:
            user.save()
            team_member.user = user
            team_member.save()
        else:
            team_member.user = user


        return team_member