from django.conf import settings


def client_ip(request):
    """The client's IP address, trusting X-Forwarded-For only as far as our own proxies.

    Each proxy appends the address it received the request from, so with N trusted proxies the real
    client is the Nth entry from the right. Anything further left was written by the client and can be
    forged, so it is never used.
    """
    remote_addr = request.META.get("REMOTE_ADDR")
    proxies = settings.TUTOR_TRUSTED_PROXIES
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if proxies <= 0 or not forwarded:
        return remote_addr
    addresses = [a.strip() for a in forwarded.split(",") if a.strip()]
    if not addresses:
        return remote_addr
    return addresses[-min(proxies, len(addresses))]
