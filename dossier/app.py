import os

from jupyterhub.app import JupyterHub

from dossier import handlers


class Dossier(JupyterHub):

    def _logo_file_default(self):
        return os.path.join(self.data_files_path, 'static', 'images', 'dossier.png')

    def init_handlers(self):
        super().init_handlers()
        dossier_handlers = {h[0]: h for h in self.add_url_prefix(self.hub_prefix, handlers.default_handlers)}
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
