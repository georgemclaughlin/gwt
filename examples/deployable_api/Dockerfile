FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY gwtlang ./gwtlang
COPY docs/schemas ./docs/schemas
COPY examples/deployable_api/rules.gwt ./examples/deployable_api/rules.gwt

RUN python -m pip install --no-cache-dir '.[serve]'

RUN useradd --create-home --uid 10001 gwt
USER gwt

ENV GWT_RULES=/app/examples/deployable_api/rules.gwt
ENV GWT_HOST=0.0.0.0
ENV GWT_PORT=8080
ENV GWT_ENGINE=asgi
ENV GWT_SERVE_ARGS=""

EXPOSE 8080

HEALTHCHECK --interval=2s --timeout=2s --start-period=2s --retries=15 \
  CMD python -c "import os, urllib.request; port = os.environ.get('GWT_PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/ready', timeout=1).read()"

CMD ["sh", "-c", "exec python -m gwtlang serve \"$GWT_RULES\" --engine \"$GWT_ENGINE\" --host \"$GWT_HOST\" --port \"$GWT_PORT\" ${GWT_SERVE_ARGS:-}"]
