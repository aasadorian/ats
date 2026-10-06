from django import forms


class OverrideForm(forms.Form):
    home_line = forms.DecimalField(max_digits=4, decimal_places=1)
    reason = forms.CharField(max_length=200)
