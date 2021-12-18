import os

from jupyterhub.app import JupyterHub
from traitlets import Unicode

from dossier import handlers


class Dossier(JupyterHub):

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


main = Dossier.launch_instance

if __name__ == "__main__":
    main()
