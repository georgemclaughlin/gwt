"""ASGI interoperability fixture loaded by external server subprocesses."""

from gwtlang.asgi import create_asgi_application
from gwtlang.http_server import GwtHttpService


application = create_asgi_application(
    GwtHttpService.from_file("examples/deployable_api/rules.gwt")
)
