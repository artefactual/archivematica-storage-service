from django.utils.six.moves.urllib.parse import urlparse


class URLMixin:
    def parse_and_fix_url(self, remote_name, scheme="http"):
        """Returns a ParseResult object based on the remote_name field.

        We've always made the assumption that the value of the remote_name
        field contained just the network location part of the pipeline URL.
        The final URL was manually using the HTTP scheme. This was a problem
        when the pipeline was behind a HTTPS front-end.
        """
        res = urlparse(remote_name)
        if res.scheme == "" and res.netloc == "" and res.path != "":
            res = res._replace(scheme=scheme)
            res = res._replace(netloc=res.path)
            res = res._replace(path="")
        return res
