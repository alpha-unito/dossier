from . import pages, login

default_handlers = []
for mod in (pages, login):
    default_handlers.extend(mod.default_handlers)
