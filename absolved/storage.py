from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Hashed, compressed static files whose JavaScript modules import each other by hashed name.

    Without the rewriting, a page's hashed module would import its siblings by their plain names,
    which browsers cache for a while, and could run against an older copy of them after a deploy.
    """

    support_js_module_import_aggregation = True
