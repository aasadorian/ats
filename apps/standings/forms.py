from django import forms


class ScoreCorrectionForm(forms.Form):
    home_score = forms.IntegerField(min_value=0, max_value=200)
    away_score = forms.IntegerField(min_value=0, max_value=200)
    reason = forms.CharField(max_length=200)
