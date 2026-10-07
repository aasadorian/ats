from django import forms


class CommissionerPickForm(forms.Form):
    team = forms.IntegerField(required=False)
    best_bet = forms.BooleanField(required=False)
    reason = forms.CharField(max_length=200)
