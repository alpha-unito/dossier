import os

from jupyterhub.app import JupyterHub
from tornado.web import StaticFileHandler
from traitlets import Unicode, default

from dossier import handlers


class DossierFaviconHandler(StaticFileHandler):
    """A singular handler for serving the logo."""

    def get(self):
        return super().get('')

    @classmethod
    def get_absolute_path(cls, root, path):
        """We only serve one file, ignore relative path"""
        return os.path.abspath(root)


class Dossier(JupyterHub):
    favicon_file = Unicode(
        '',
        help="Specify path to a favicon image to override the Jupyter favicon in the browser tab.",
    ).tag(config=True)

    @default('favicon_file')
    def _favicon_file_default(self):
        return os.path.join(self.data_files_path, 'dossier', 'static', 'favicon.ico')

    def _logo_file_default(self):
        return os.path.join(self.data_files_path, 'dossier', 'static', 'images', 'dossier.png')

    def init_handlers(self):
        super().init_handlers()
        dossier_handlers = {h[0]: h for h in self.add_url_prefix(
            self.hub_prefix,
            handlers.default_handlers + [
                (r'/favicon', DossierFaviconHandler, {'path': self.favicon_file})
            ])}
        for i, handler_tuple in enumerate(self.handlers):
            regex = handler_tuple[0]
            if regex in dossier_handlers:
                self.handlers[i] = dossier_handlers[regex]
                del dossier_handlers[regex]
        h = list(dossier_handlers.values())
        h.extend(self.handlers)
        self.handlers = h

    def init_tornado_settings(self):
        dossier_template_paths = os.path.join(self.data_files_path, 'dossier', 'templates')
        if dossier_template_paths not in self.template_paths:
            self.template_paths.append(dossier_template_paths)
        super().init_tornado_settings()


main = Dossier.launch_instance

if __name__ == "__main__":
    main()
