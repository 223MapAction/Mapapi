"""Miscellaneous endpoints (deep-link redirects, etc.)."""
from django.http import HttpResponse
from django.views import View


class RedirectToAppView(View):
    def get(self, request, token):
        deep_link_url = f"com.uwaish.MapActionApp://verify-email/{token}"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Redirection...</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <script type="text/javascript">
                window.location = "{deep_link_url}";
                setTimeout(function() {{
                    window.location = "https://map-action.com/"; // fallback si l'app n'est pas installée
                }}, 3000);
            </script>
        </head>
        <body>
            <p>Redirection vers l'application en cours...</p>
        </body>
        </html>
        """
        return HttpResponse(html)
