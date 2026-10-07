from zoneinfo import available_timezones

from django import forms
from django.http import HttpRequest, QueryDict

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


class ProfileForm(forms.ModelForm[User]):
    class Meta:
        model = User
        fields = ("display_name", "timezone")

    def clean_display_name(self) -> str:
        name: str = self.cleaned_data["display_name"].strip()
        if (
            User.objects.filter(display_name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("That display name is taken.")
        return name

    def clean_timezone(self) -> str:
        name: str = self.cleaned_data["timezone"]
        if name not in available_timezones():
            raise forms.ValidationError(
                "Choose a valid timezone, like America/Los_Angeles."
            )
        return name


class DeleteAccountForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    confirm = forms.CharField(help_text="Type DELETE to confirm.")

    def __init__(self, user: User, data: QueryDict | None = None) -> None:
        super().__init__(data)
        self.user = user
        if not user.has_usable_password():
            del self.fields["password"]

    def clean_password(self) -> str:
        password: str = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("That password is incorrect.")
        return password

    def clean_confirm(self) -> str:
        value: str = self.cleaned_data["confirm"]
        if value != "DELETE":
            raise forms.ValidationError("Type DELETE to confirm.")
        return value
