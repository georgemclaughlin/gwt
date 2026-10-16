"""Tool-free Responses API transport; no implicit retries or model substitution."""
import http.client
import json
import os
import time

from .scorer import strict_json


RESPONSE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['action', 'source', 'clarifications'],
    'properties': {'action': {'type': 'string', 'enum': ['code', 'clarify']},
                   'source': {'type': 'string'},
                   'clarifications': {'type': 'array', 'items': {'type': 'string'}}},
}


def request_body(prompt, *, model, reasoning_effort, maximum_output_tokens):
    return {'model': model, 'input': prompt, 'tools': [], 'tool_choice': 'none',
            'store': False, 'reasoning': {'effort': reasoning_effort},
            'max_output_tokens': maximum_output_tokens,
            'text': {'format': {'type': 'json_schema', 'name': 'maintenance_response',
                                'strict': True, 'schema': RESPONSE_SCHEMA}}}


def decode_response(body):
    """Accept exactly one complete assistant JSON message; never dispatch tools."""
    if not isinstance(body, dict) or body.get('status') != 'completed':
        raise ValueError('provider response did not complete')
    outputs = body.get('output')
    if not isinstance(outputs, list):
        raise ValueError('provider output is not a list')
    texts = []
    for item in outputs:
        if not isinstance(item, dict):
            raise ValueError('invalid provider output item')
        if item.get('type') == 'reasoning':
            continue
        if item.get('type') != 'message' or item.get('role') != 'assistant':
            raise ValueError('unexpected provider output type')
        if item.get('status') != 'completed' or not isinstance(item.get('content'), list):
            raise ValueError('assistant message did not complete')
        for content in item['content']:
            if not isinstance(content, dict) or content.get('type') != 'output_text' or not isinstance(content.get('text'), str):
                raise ValueError('refused or non-text provider output')
            texts.append(content['text'])
    if len(texts) != 1:
        raise ValueError('expected one structured response')
    response = strict_json(texts[0])
    if not isinstance(response, dict) or set(response) != {'action', 'source', 'clarifications'}:
        raise ValueError('invalid structured response fields')
    if response['action'] not in ('code', 'clarify') or not isinstance(response['source'], str):
        raise ValueError('invalid action/source')
    questions = response['clarifications']
    if not isinstance(questions, list) or any(not isinstance(value, str) or not value.strip() for value in questions):
        raise ValueError('invalid clarifications')
    if response['action'] == 'code' and (not response['source'].strip() or questions):
        raise ValueError('code requires source and no clarifications')
    if response['action'] == 'clarify' and (response['source'] or not questions):
        raise ValueError('clarify requires questions and no source')
    return response


class ResponsesProvider:
    """One HTTPS POST per call; credentials never enter artifacts or candidates."""
    metadata = {'provider': 'openai-responses', 'endpoint': 'https://api.openai.com/v1/responses',
                'synthetic': False, 'automaticRetries': 0}

    def __init__(self, *, socket_timeout=300):
        self._key = os.environ.get('OPENAI_API_KEY')
        if not self._key:
            raise ValueError('OPENAI_API_KEY is required for live calls')
        self.socket_timeout = socket_timeout

    def __call__(self, body):
        connection = http.client.HTTPSConnection('api.openai.com', timeout=self.socket_timeout)
        started = time.monotonic()
        try:
            connection.request('POST', '/v1/responses', json.dumps(body, ensure_ascii=False).encode(),
                               {'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(20 * 1024 * 1024 + 1)
            if len(raw) > 20 * 1024 * 1024:
                raise ValueError('provider response exceeds twenty MiB')
            return {'httpStatus': response.status, 'requestId': response.getheader('x-request-id'),
                    'rawBody': raw.decode('utf-8'), 'durationSeconds': time.monotonic() - started}
        finally:
            connection.close()
