from .models import AuditLog


def record(actor, action, obj, before=None, after=None, ip=None):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        before=before,
        after=after,
        ip=ip,
    )
