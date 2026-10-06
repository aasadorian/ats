from django import forms

from apps.leagues.models import Role


class InviteForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Role.choices, initial=Role.MEMBER)


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices)
