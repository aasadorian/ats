from django import forms
from django.http import HttpRequest

from apps.accounts.models import User


class SignupDetailsForm(forms.Form):
    display_name = forms.CharField(
        max_length=40, help_text="Shown on standings and picks."
    )

    def clean_display_name(self) -> str:
        name: str = self.cleaned_data["display_name"].strip()
        if User.objects.filter(display_name__iexact=name).exists():
            raise forms.ValidationError("That display name is taken.")
        return name

    def signup(self, request: HttpRequest, user: User) -> None:
        user.display_name = self.cleaned_data["display_name"]
        user.save(update_fields=["display_name"])
