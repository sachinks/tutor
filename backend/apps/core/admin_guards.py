"""Admin helpers that keep the back office inside the same rules as the API (quality backlog Q4)."""

from django import forms

LOCKED_STATUSES = ("published", "archived")


class VersionStatusForm(forms.ModelForm):
    """Status can move through draft → review → approved in the admin, but publishing (and the archiving it
    causes) happens only through the Publish action, which checks who may publish and records it."""

    def clean_status(self):
        new = self.cleaned_data.get("status")
        old = self.initial.get("status") if self.instance.pk else None
        if new != old and (new in LOCKED_STATUSES or old in LOCKED_STATUSES):
            raise forms.ValidationError(
                "Published and archived are set only by the 'Publish selected approved versions' action."
            )
        return new
