FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY gwtlang ./gwtlang
COPY examples/deployable_api/rules.gwt ./examples/deployable_api/rules.gwt

RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 gwt
USER gwt

ENV GWT_RULES=/app/examples/deployable_api/rules.gwt
ENV GWT_HOST=0.0.0.0
ENV GWT_PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "python -m gwtlang serve \"$GWT_RULES\" --host \"$GWT_HOST\" --port \"$GWT_PORT\" ${GWT_SERVE_ARGS:-}"]
